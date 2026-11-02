import asyncio
import logging
from aiohttp import web, ClientSession, ClientTimeout, ClientError
from .circuit_breaker import CircuitBreaker
from .config import ProxyConfig
from .rate_limiter import create_rate_limit_middleware
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
        self.cache = {}
        self.health_check_tasks = []

    async def start(self):
        timeout = ClientTimeout(total=self.config.upstream_timeout_seconds)
        self.session = ClientSession(timeout=timeout)

        if self.config.health_check.enabled:
            for i, url in enumerate(self.config.upstream_urls):
                task = asyncio.create_task(self._health_check_loop(url, self.breakers[i]))
                self.health_check_tasks.append(task)

    async def close(self):
        for task in self.health_check_tasks:
            task.cancel()
        if self.health_check_tasks:
            await asyncio.gather(*self.health_check_tasks, return_exceptions=True)

        if self.session:
            await self.session.close()

    async def _health_check_loop(self, base_url: str, breaker: CircuitBreaker):
        endpoint = self.config.health_check.endpoint
        interval = self.config.health_check.interval_seconds
        timeout_seconds = self.config.health_check.timeout_seconds
        health_url = yarl.URL(base_url).with_path(endpoint)

        while True:
            try:
                await asyncio.sleep(interval)
                async with ClientSession(timeout=ClientTimeout(total=timeout_seconds)) as session:
                    async with session.get(health_url) as response:
                        if response.status >= 500:
                            logger.warning(f"Health check failed for {base_url} (status {response.status})")
                            breaker.force_open()
            except (ClientError, asyncio.TimeoutError) as e:
                logger.warning(f"Health check failed for {base_url}: {e}")
                breaker.force_open()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Unexpected error in health check for {base_url}: {e}")

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
            if request.method == "GET":
                cache_key = request.path_qs
                if cache_key in self.cache:
                    logger.warning(f"Returning stale cache for {cache_key}")
                    cached = self.cache[cache_key]
                    headers = dict(cached['headers'])
                    headers['X-Cache-Stale'] = 'true'
                    return web.Response(
                        body=cached['body'],
                        status=cached['status'],
                        headers=headers
                    )
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
                
                if request.method == "GET" and status == 200:
                    self.cache[request.path_qs] = {
                        'body': body,
                        'status': status,
                        'headers': response_headers
                    }
                
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
    app = web.Application(middlewares=[create_rate_limit_middleware(config.rate_limit)])
    handler = ProxyHandler(config)
    
    app.on_startup.append(lambda app: handler.start())
    app.on_cleanup.append(lambda app: handler.close())
    
    # Catch-all route
    app.router.add_route('*', '/{tail:.*}', handler.handle_request)
    return app, handler
