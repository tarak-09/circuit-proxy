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
        upstream_urls=["http://127.0.0.1:9000"], # to be overridden in tests
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
    proxy_config.upstream_urls = [f"http://{upstream_server.host}:{upstream_server.port}"]
    
    # Setup Proxy
    proxy_app, proxy_handler = await init_app(proxy_config)
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
    proxy_config.upstream_urls = [f"http://{upstream_server.host}:{upstream_server.port}"]
    proxy_app, proxy_handler = await init_app(proxy_config)
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
    assert "Service Unavailable (All Circuit Breakers Open)" in text3

@pytest.mark.asyncio
async def test_proxy_upstream_timeout(aiohttp_client, aiohttp_server, proxy_config):
    # Setup Upstream
    upstream_app = web.Application()
    upstream_app.router.add_route('*', '/{tail:.*}', upstream_handler)
    upstream_server = await aiohttp_server(upstream_app)
    
    # Setup Proxy config
    proxy_config.upstream_urls = [f"http://{upstream_server.host}:{upstream_server.port}"]
    proxy_app, proxy_handler = await init_app(proxy_config)
    proxy_client = await aiohttp_client(proxy_app)
    
    # Send timeout requests
    resp1 = await proxy_client.get("/timeout")
    assert resp1.status == 502  # Proxy turns timeout into 502 Bad Gateway
    
    resp2 = await proxy_client.get("/timeout")
    assert resp2.status == 502
    
    # Circuit should be tripped now
    resp3 = await proxy_client.get("/success")
    assert resp3.status == 503

@pytest.mark.asyncio
async def test_proxy_load_balancing_and_fallback(aiohttp_client, aiohttp_server, proxy_config):
    # Setup Upstream 1
    upstream_app1 = web.Application()
    upstream_app1.router.add_route('*', '/{tail:.*}', upstream_handler)
    upstream_server1 = await aiohttp_server(upstream_app1)

    # Setup Upstream 2
    upstream_app2 = web.Application()
    upstream_app2.router.add_route('*', '/{tail:.*}', upstream_handler)
    upstream_server2 = await aiohttp_server(upstream_app2)

    proxy_config.upstream_urls = [
        f"http://{upstream_server1.host}:{upstream_server1.port}",
        f"http://{upstream_server2.host}:{upstream_server2.port}",
    ]
    proxy_app, proxy_handler = await init_app(proxy_config)
    proxy_client = await aiohttp_client(proxy_app)

    # We send 2 failures to server 1, which will trip it (min_requests=2)
    # The requests alternate between servers because of round-robin.
    # Request 1 -> Server 1 (/fail)
    resp1 = await proxy_client.get("/fail")
    assert resp1.status == 500

    # Request 2 -> Server 2 (/fail)
    resp2 = await proxy_client.get("/fail")
    assert resp2.status == 500

    # Request 3 -> Server 1 (/fail) - trips Server 1
    resp3 = await proxy_client.get("/fail")
    assert resp3.status == 500

    # Now Server 1 is OPEN.
    # Request 4 -> Should go to Server 2 (because 1 is skipped). 
    resp4 = await proxy_client.get("/success")
    assert resp4.status == 200

    # Request 5 -> Should go to Server 2 again (because 1 is skipped).
    resp5 = await proxy_client.get("/success")
    assert resp5.status == 200
