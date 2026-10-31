import yaml
from dataclasses import dataclass, field
from typing import Dict, Any


@dataclass
class RateLimitConfig:
    enabled: bool = False
    rate: float = 10.0
    burst: int = 10

@dataclass
class BreakerConfig:
    failure_threshold_ratio: float = 0.5
    min_requests: int = 5
    window_size_seconds: float = 10.0
    reset_timeout_seconds: float = 5.0
    half_open_max_probes: int = 3

@dataclass
class ProxyConfig:
    host: str
    port: int
    upstream_urls: list[str]
    management_port: int = 9090
    upstream_timeout_seconds: float = 5.0
    breaker: BreakerConfig = field(default_factory=BreakerConfig)
    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)

def load_config(config_path: str) -> ProxyConfig:
    with open(config_path, 'r') as f:
        data = yaml.safe_load(f) or {}

    breaker_data = data.get('breaker', {})
    breaker_config = BreakerConfig(
        failure_threshold_ratio=float(breaker_data.get('failure_threshold_ratio', 0.5)),
        min_requests=int(breaker_data.get('min_requests', 5)),
        window_size_seconds=float(breaker_data.get('window_size_seconds', 10.0)),
        reset_timeout_seconds=float(breaker_data.get('reset_timeout_seconds', 5.0)),
        half_open_max_probes=int(breaker_data.get('half_open_max_probes', 3))
    )

    rate_limit_data = data.get('rate_limit', {})
    rate_limit_config = RateLimitConfig(
        enabled=bool(rate_limit_data.get('enabled', False)),
        rate=float(rate_limit_data.get('rate', 10.0)),
        burst=int(rate_limit_data.get('burst', 10))
    )

    upstream_urls = data.get('upstream_urls', [])
    if not upstream_urls and 'upstream_url' in data:
        upstream_urls = [data['upstream_url']]

    return ProxyConfig(
        host=data.get('host', '127.0.0.1'),
        port=int(data.get('port', 8080)),
        management_port=int(data.get('management_port', 9090)),
        upstream_urls=upstream_urls or ['http://127.0.0.1:9000'],
        upstream_timeout_seconds=float(data.get('upstream_timeout_seconds', 5.0)),
        breaker=breaker_config,
        rate_limit=rate_limit_config
    )
