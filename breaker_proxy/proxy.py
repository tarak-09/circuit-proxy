import asyncio
import logging
from aiohttp import web, ClientSession, ClientTimeout, ClientError
from .circuit_breaker import CircuitBreaker
from .config import ProxyConfig
import yarl

logger = logging.getLogger(__name__)

class ProxyHandler:
    def __init__(self, config: ProxyConfig):
        self.config = config
        self.breaker = CircuitBreaker(
            failure_threshold_ratio=config.breaker.failure_threshold_ratio,
            min_requests=config.breaker.min_requests,
            window_size_seconds=config.breaker.window_size_seconds,
            reset_timeout_seconds=config.breaker.reset_timeout_seconds,
            half_open_max_probes=config.breaker.half_open_max_probes
        )
        self.session = None

    async def start(self):
        timeout = ClientTimeout(total=self.config.upstream_timeout_seconds)
        self.session = ClientSession(timeout=timeout)

    async def close(self):
        if self.session:
            await self.session.close()

    async def handle_request(self, request: web.Request) -> web.Response:
        if not self.breaker.can_request():
            logger.warning("Rejecting request, circuit breaker is OPEN/HALF_OPEN (max probes reached).")
            return web.Response(status=503, text="Service Unavailable (Circuit Breaker Open)")

        upstream_url = yarl.URL(self.config.upstream_url)
        target_url = upstream_url.with_path(request.path).with_query(request.query)

        # Prepare headers to forward
        headers = dict(request.headers)
        # Remove hop-by-hop headers
        headers.pop('Host', None)

        try:
            # We must read the payload if present
            data = await request.read()
            
            async with self.session.request(
                method=request.method,
                url=target_url,
                headers=headers,
                data=data,
                allow_redirects=False
            ) as upstream_response:
                
                status = upstream_response.status
                if status >= 500:
                    self.breaker.record_failure()
                else:
                    self.breaker.record_success()

                # Read body and headers to return
                body = await upstream_response.read()
                response_headers = dict(upstream_response.headers)
                
                return web.Response(
                    body=body,
                    status=status,
                    headers=response_headers
                )

        except (ClientError, asyncio.TimeoutError) as e:
            logger.error(f"Upstream request failed: {e}")
            self.breaker.record_failure()
            return web.Response(status=502, text="Bad Gateway (Upstream Failure)")

async def init_app(config: ProxyConfig) -> web.Application:
    app = web.Application()
    handler = ProxyHandler(config)
    
    app.on_startup.append(lambda app: handler.start())
    app.on_cleanup.append(lambda app: handler.close())
    
    # Catch-all route
    app.router.add_route('*', '/{tail:.*}', handler.handle_request)
    return app
