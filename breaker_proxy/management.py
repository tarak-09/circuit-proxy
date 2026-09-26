import logging
from aiohttp import web
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from .circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)

def create_management_app(breakers: list[CircuitBreaker]) -> web.Application:
    app = web.Application()

    async def metrics_handler(request: web.Request) -> web.Response:
        data = generate_latest()
        # CONTENT_TYPE_LATEST usually contains charset, aiohttp's content_type arg rejects it.
        # We can pass it directly as a header.
        return web.Response(body=data, headers={"Content-Type": CONTENT_TYPE_LATEST})

    async def get_state_handler(request: web.Request) -> web.Response:
        states = {breaker.url: breaker.state.value for breaker in breakers}
        return web.json_response(states)

    async def reset_handler(request: web.Request) -> web.Response:
        for breaker in breakers:
            breaker.manual_reset()
        states = {breaker.url: breaker.state.value for breaker in breakers}
        return web.json_response({"status": "ok", "states": states})

    app.router.add_get('/metrics', metrics_handler)
    app.router.add_get('/api/state', get_state_handler)
    app.router.add_post('/api/reset', reset_handler)

    return app
