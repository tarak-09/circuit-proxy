from prometheus_client import Counter, Enum, Gauge

CIRCUIT_STATE = Enum('circuit_state', 'Current state of the circuit breaker', ['url'], states=['CLOSED', 'OPEN', 'HALF_OPEN'])
REQUESTS_TOTAL = Counter('circuit_requests_total', 'Total number of requests processed by the circuit breaker', ['url', 'status'])
FAILURE_RATE = Gauge('circuit_failure_rate', 'Current failure rate of the circuit breaker', ['url'])
