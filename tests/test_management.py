import pytest
from aiohttp import web
from breaker_proxy.circuit_breaker import CircuitBreaker, CircuitState
from breaker_proxy.management import create_management_app

@pytest.mark.asyncio
async def test_management_api(aiohttp_client):
    breaker = CircuitBreaker(url="http://localhost:9000")
    # Set some initial state
    breaker.state = CircuitState.OPEN
    
    app = create_management_app([breaker])
    client = await aiohttp_client(app)
    
    # Test /api/state
    resp = await client.get('/api/state')
    assert resp.status == 200
    data = await resp.json()
    assert data["http://localhost:9000"] == "OPEN"
    
    # Test /api/reset
    resp = await client.post('/api/reset')
    assert resp.status == 200
    data = await resp.json()
    assert data["status"] == "ok"
    assert data["states"]["http://localhost:9000"] == "CLOSED"
    assert breaker.state == CircuitState.CLOSED
    
    # Test /metrics
    resp = await client.get('/metrics')
    assert resp.status == 200
    text = await resp.text()
    assert "circuit_state" in text

