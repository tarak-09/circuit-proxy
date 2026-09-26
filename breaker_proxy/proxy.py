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
        self.breakers = [
            CircuitBreaker(
                url=url,
                failure_threshold_ratio=config.breaker.failure_threshold_ratio,
                min_requests=config.breaker.min_requests,
                window_size_seconds=config.breaker.window_size_seconds,
                reset_timeout_seconds=config.breaker.reset_timeout_seconds,
                half_open_max_probes=config.breaker.half_open_max_probes
            )
            for url in config.upstream_urls
        ]
        self.current_index = 0
        self.session = None

    async def start(self):
        timeout = ClientTimeout(total=self.config.upstream_timeout_seconds)
        self.session = ClientSession(timeout=timeout)

    async def close(self):
        if self.session:
            await self.session.close()

    async def handle_request(self, request: web.Request) -> web.Response:
        urls_count = len(self.breakers)
        selected_breaker = None
        selected_url = None
        
        for _ in range(urls_count):
            idx = self.current_index
            self.current_index = (self.current_index + 1) % urls_count
            
            breaker = self.breakers[idx]
            if breaker.can_request():
                selected_breaker = breaker
                selected_url = self.config.upstream_urls[idx]
                break

        if not selected_breaker:
            logger.warning("Rejecting request, all circuit breakers are OPEN/HALF_OPEN.")
            return web.Response(status=503, text="Service Unavailable (All Circuit Breakers Open)")

        upstream_url = yarl.URL(selected_url)
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
                    selected_breaker.record_failure()
                else:
                    selected_breaker.record_success()

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
            selected_breaker.record_failure()
            return web.Response(status=502, text="Bad Gateway (Upstream Failure)")

async def init_app(config: ProxyConfig) -> tuple[web.Application, ProxyHandler]:
    app = web.Application()
    handler = ProxyHandler(config)
    
    app.on_startup.append(lambda app: handler.start())
    app.on_cleanup.append(lambda app: handler.close())
    
    # Catch-all route
    app.router.add_route('*', '/{tail:.*}', handler.handle_request)
    return app, handler
