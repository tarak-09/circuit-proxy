import re

with open('breaker_proxy/proxy.py', 'r') as f:
    content = f.read()

# Add import
import_patch = """
from .config import ProxyConfig
from .rate_limiter import create_rate_limit_middleware
"""
content = content.replace('from .config import ProxyConfig', import_patch.strip('\n'))

# Add middleware
init_app_patch = """
async def init_app(config: ProxyConfig) -> tuple[web.Application, ProxyHandler]:
    app = web.Application(middlewares=[create_rate_limit_middleware(config.rate_limit)])
"""
content = re.sub(r'async def init_app\(config: ProxyConfig\) -> tuple\[web.Application, ProxyHandler\]:\n    app = web.Application\(\)', init_app_patch.strip('\n'), content)

with open('breaker_proxy/proxy.py', 'w') as f:
    f.write(content)
