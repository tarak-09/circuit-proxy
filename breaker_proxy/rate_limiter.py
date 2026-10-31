import time
from aiohttp import web
from .config import RateLimitConfig

class TokenBucket:
    def __init__(self, rate: float, burst: int):
        self.rate = rate
        self.burst = burst
        self.tokens = float(burst)
        self.last_update = time.monotonic()

    def consume(self, amount: int = 1) -> bool:
        now = time.monotonic()
        elapsed = now - self.last_update
        self.tokens = min(float(self.burst), self.tokens + elapsed * self.rate)
        self.last_update = now

        if self.tokens >= amount:
            self.tokens -= amount
            return True
        return False

def create_rate_limit_middleware(config: RateLimitConfig):
    buckets: dict[str, TokenBucket] = {}

    @web.middleware
    async def middleware(request: web.Request, handler):
        if not config.enabled:
            return await handler(request)

        client_ip = request.remote
        if not client_ip:
            client_ip = "unknown"

        if client_ip not in buckets:
            buckets[client_ip] = TokenBucket(rate=config.rate, burst=config.burst)

        bucket = buckets[client_ip]
        if not bucket.consume(1):
            return web.Response(status=429, text="Too Many Requests")

        return await handler(request)

    return middleware
