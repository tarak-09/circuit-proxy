import re

with open('breaker_proxy/config.py', 'r') as f:
    content = f.read()

# Add RateLimitConfig dataclass
rate_limit_class = """
@dataclass
class RateLimitConfig:
    enabled: bool = False
    rate: float = 10.0
    burst: int = 10
"""
content = content.replace('@dataclass\nclass BreakerConfig:', rate_limit_class + '\n@dataclass\nclass BreakerConfig:')

# Add to ProxyConfig
proxy_config_fields = """
    upstream_timeout_seconds: float = 5.0
    breaker: BreakerConfig = field(default_factory=BreakerConfig)
    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)
"""
content = re.sub(r'    upstream_timeout_seconds: float = 5\.0\n    breaker: BreakerConfig = field\(default_factory=BreakerConfig\)', proxy_config_fields.strip('\n'), content)

# Modify load_config
load_config_patch = """
    rate_limit_data = data.get('rate_limit', {})
    rate_limit_config = RateLimitConfig(
        enabled=bool(rate_limit_data.get('enabled', False)),
        rate=float(rate_limit_data.get('rate', 10.0)),
        burst=int(rate_limit_data.get('burst', 10))
    )

    upstream_urls = data.get('upstream_urls', [])
"""
content = content.replace("    upstream_urls = data.get('upstream_urls', [])", load_config_patch.strip('\n'))

return_proxy_config = """
        upstream_timeout_seconds=float(data.get('upstream_timeout_seconds', 5.0)),
        breaker=breaker_config,
        rate_limit=rate_limit_config
    )
"""
content = re.sub(r"        upstream_timeout_seconds=float\(data\.get\('upstream_timeout_seconds', 5\.0\)\),\n        breaker=breaker_config\n    \)", return_proxy_config.strip('\n'), content)

with open('breaker_proxy/config.py', 'w') as f:
    f.write(content)
