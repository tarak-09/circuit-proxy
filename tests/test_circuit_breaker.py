import pytest
import asyncio
from breaker_proxy.circuit_breaker import CircuitBreaker, CircuitState

@pytest.mark.asyncio
async def test_circuit_breaker_initial_state():
    cb = CircuitBreaker()
    assert cb.state == CircuitState.CLOSED
    assert cb.can_request() is True

@pytest.mark.asyncio
async def test_circuit_breaker_trips_open():
    cb = CircuitBreaker(failure_threshold_ratio=0.5, min_requests=4, window_size_seconds=10.0)
    
    # Send 2 success, 2 failures
    cb.record_success()
    cb.record_success()
    cb.record_failure()
    
    # Before the 4th request, it's still closed (min_requests=4)
    assert cb.state == CircuitState.CLOSED
    
    cb.record_failure()
    # Now failure rate is 2/4 = 0.5, which is >= 0.5. Should trip OPEN.
    assert cb.state == CircuitState.OPEN
    assert cb.can_request() is False

@pytest.mark.asyncio
async def test_circuit_breaker_half_open_recovery():
    cb = CircuitBreaker(
        failure_threshold_ratio=0.5,
        min_requests=2,
        window_size_seconds=10.0,
        reset_timeout_seconds=0.1,
        half_open_max_probes=2
    )
    
    cb.record_failure()
    cb.record_failure()
    
    assert cb.state == CircuitState.OPEN
    
    # Wait for reset timeout
    await asyncio.sleep(0.15)
    
    assert cb.state == CircuitState.HALF_OPEN
    assert cb.can_request() is True
    
    # 2 successful probes should close it
    cb.record_success()
    assert cb.state == CircuitState.HALF_OPEN
    
    cb.record_success()
    assert cb.state == CircuitState.CLOSED
    assert cb.can_request() is True

@pytest.mark.asyncio
async def test_circuit_breaker_half_open_failure():
    cb = CircuitBreaker(
        failure_threshold_ratio=0.5,
        min_requests=2,
        window_size_seconds=10.0,
        reset_timeout_seconds=0.1,
        half_open_max_probes=2
    )
    
    cb.record_failure()
    cb.record_failure()
    
    assert cb.state == CircuitState.OPEN
    
    await asyncio.sleep(0.15)
    assert cb.state == CircuitState.HALF_OPEN
    
    # 1 failed probe should trip it back to OPEN immediately
    cb.record_failure()
    
    assert cb.state == CircuitState.OPEN
    assert cb.can_request() is False
