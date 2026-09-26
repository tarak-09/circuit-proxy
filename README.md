# Breaker Proxy

An async HTTP reverse proxy implementing the circuit breaker pattern to protect backend services from cascading failures. Built with Python and `aiohttp`.

## Features

- **Circuit Breaker Pattern**: Automatically trips to an `OPEN` state when the upstream server's failure rate exceeds a configurable threshold.
- **Rolling Window**: Tracks successes, failures (5xx HTTP status codes), and timeouts within a time-based rolling window.
- **Self-Healing (Half-Open)**: After a reset timeout, the proxy allows a limited number of requests to pass through to probe if the upstream has recovered.
- **Async I/O**: Fully non-blocking and highly concurrent powered by `aiohttp`.

## Why it exists

When a backend service is overwhelmed, continuing to send it requests can exacerbate the issue, turning a brief latency spike into a total cascading failure. A circuit breaker sits in front of the backend and detects when it is failing. By "tripping open," it fails fast, allowing the upstream service time to recover and freeing up resources in the calling clients. 

## Installation

This project uses `uv` for dependency management.

```bash
uv venv
uv pip install -e .
```

For development and testing dependencies:
```bash
uv pip install -e .[dev]
```

## Usage

Start the proxy server using the command-line interface:

```bash
breaker-proxy -c config.yaml
```

### Configuration (`config.yaml`)

```yaml
host: 127.0.0.1
port: 8080
management_port: 9090
upstream_urls:
  - http://127.0.0.1:9000
  - http://127.0.0.1:9001
upstream_timeout_seconds: 5.0

breaker:
  failure_threshold_ratio: 0.5   # Trip if 50% or more requests fail
  min_requests: 5                # Minimum requests in the window to evaluate ratio
  window_size_seconds: 10.0      # Rolling window size
  reset_timeout_seconds: 5.0     # Time to wait before entering HALF-OPEN state
  half_open_max_probes: 3        # Number of successful probes required to close the circuit
```

## Management API & Observability

The proxy also starts a management API (by default on port `9090`).

- **`GET /metrics`**: Exposes real-time Prometheus metrics including `circuit_state`, `circuit_requests_total`, and `circuit_failure_rate`, labeled by `url`.
- **`GET /api/state`**: Returns the current state of all circuit breakers in JSON format (`{"http://127.0.0.1:9000": "CLOSED"}`).
- **`POST /api/reset`**: Manually force all circuit breakers to reset to the `CLOSED` state.

## Worked Example

Start the proxy using the above `config.yaml`. Let's assume we have a flaky upstream server running on `localhost:9000`. We simulate normal requests and then a sudden burst of errors:

```text
--- Requests ---
GET /ok -> 200 Upstream OK
GET /fail -> 500 Upstream Error
GET /fail -> 500 Upstream Error
GET /fail -> 500 Upstream Error
GET /fail -> 503 Service Unavailable (Circuit Breaker Open)
GET /fail -> 503 Service Unavailable (Circuit Breaker Open)

# The circuit is now tripped open. Subsequent requests are rejected instantly.
GET /ok -> 503 Service Unavailable (Circuit Breaker Open)

Waiting for reset timeout (5 seconds)...

# The proxy transitions to HALF-OPEN. Probes are sent through.
GET /ok -> 200 Upstream OK
GET /ok -> 200 Upstream OK

# The circuit has closed again. Traffic flows normally.
```

## Running Tests

Tests are written using `pytest` and `pytest-asyncio` for simulating real aiohttp server interactions.

```bash
uv run pytest
```
