import pytest
from aiohttp import web
from breaker_proxy.proxy import init_app
from breaker_proxy.config import ProxyConfig, BreakerConfig
from breaker_proxy.circuit_breaker import CircuitState

async def upstream_handler(request):
    if request.path == "/success":
        return web.Response(text="Success")
    elif request.path == "/fail":
        return web.Response(status=500, text="Internal Server Error")
    elif request.path == "/timeout":
        import asyncio
        await asyncio.sleep(0.5)
        return web.Response(text="Late")
    return web.Response(status=404, text="Not Found")

@pytest.fixture
def proxy_config():
    return ProxyConfig(
        host="127.0.0.1",
        port=8080,
        upstream_url="http://127.0.0.1:9000", # to be overridden in tests
        upstream_timeout_seconds=0.2,
        breaker=BreakerConfig(
            failure_threshold_ratio=0.5,
            min_requests=2,
            window_size_seconds=10.0,
            reset_timeout_seconds=0.5,
            half_open_max_probes=1
        )
    )

@pytest.mark.asyncio
async def test_proxy_success(aiohttp_client, aiohttp_server, proxy_config):
    # Setup Upstream
    upstream_app = web.Application()
    upstream_app.router.add_route('*', '/{tail:.*}', upstream_handler)
    upstream_server = await aiohttp_server(upstream_app)
    
    # Update config with dynamic upstream url
    proxy_config.upstream_url = f"http://{upstream_server.host}:{upstream_server.port}"
    
    # Setup Proxy
    proxy_app = await init_app(proxy_config)
    proxy_client = await aiohttp_client(proxy_app)
    
    resp = await proxy_client.get("/success")
    assert resp.status == 200
    text = await resp.text()
    assert text == "Success"

@pytest.mark.asyncio
async def test_proxy_circuit_trips(aiohttp_client, aiohttp_server, proxy_config):
    # Setup Upstream
    upstream_app = web.Application()
    upstream_app.router.add_route('*', '/{tail:.*}', upstream_handler)
    upstream_server = await aiohttp_server(upstream_app)
    
    # Setup Proxy config
    proxy_config.upstream_url = f"http://{upstream_server.host}:{upstream_server.port}"
    proxy_app = await init_app(proxy_config)
    proxy_client = await aiohttp_client(proxy_app)
    
    # Send 2 failures to trip the circuit
    resp1 = await proxy_client.get("/fail")
    assert resp1.status == 500
    
    resp2 = await proxy_client.get("/fail")
    assert resp2.status == 500
    
    # The third request should be immediately rejected with 503 Service Unavailable
    resp3 = await proxy_client.get("/success")
    assert resp3.status == 503
    text3 = await resp3.text()
    assert "Circuit Breaker Open" in text3

@pytest.mark.asyncio
async def test_proxy_upstream_timeout(aiohttp_client, aiohttp_server, proxy_config):
    # Setup Upstream
    upstream_app = web.Application()
    upstream_app.router.add_route('*', '/{tail:.*}', upstream_handler)
    upstream_server = await aiohttp_server(upstream_app)
    
    # Setup Proxy config
    proxy_config.upstream_url = f"http://{upstream_server.host}:{upstream_server.port}"
    proxy_app = await init_app(proxy_config)
    proxy_client = await aiohttp_client(proxy_app)
    
    # Send timeout requests
    resp1 = await proxy_client.get("/timeout")
    assert resp1.status == 502  # Proxy turns timeout into 502 Bad Gateway
    
    resp2 = await proxy_client.get("/timeout")
    assert resp2.status == 502
    
    # Circuit should be tripped now
    resp3 = await proxy_client.get("/success")
    assert resp3.status == 503
