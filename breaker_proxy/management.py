import logging
from aiohttp import web
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from .circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)

def create_management_app(breaker: CircuitBreaker) -> web.Application:
    app = web.Application()

    async def metrics_handler(request: web.Request) -> web.Response:
        data = generate_latest()
        # CONTENT_TYPE_LATEST usually contains charset, aiohttp's content_type arg rejects it.
        # We can pass it directly as a header.
        return web.Response(body=data, headers={"Content-Type": CONTENT_TYPE_LATEST})

    async def get_state_handler(request: web.Request) -> web.Response:
        return web.json_response({"state": breaker.state.value})

    async def reset_handler(request: web.Request) -> web.Response:
        breaker.manual_reset()
        return web.json_response({"status": "ok", "state": breaker.state.value})

    app.router.add_get('/metrics', metrics_handler)
    app.router.add_get('/api/state', get_state_handler)
    app.router.add_post('/api/reset', reset_handler)

    return app
