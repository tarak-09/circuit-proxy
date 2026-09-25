import argparse
import logging
import asyncio
from aiohttp import web
from .config import load_config, ProxyConfig
from .proxy import init_app
from .management import create_management_app

async def start_servers(config: ProxyConfig):
    proxy_app, proxy_handler = await init_app(config)
    management_app = create_management_app(proxy_handler.breaker)
    
    proxy_runner = web.AppRunner(proxy_app)
    await proxy_runner.setup()
    proxy_site = web.TCPSite(proxy_runner, config.host, config.port)
    await proxy_site.start()
    logging.info(f"Started proxy on {config.host}:{config.port} routing to {config.upstream_url}")

    mgmt_runner = web.AppRunner(management_app)
    await mgmt_runner.setup()
    mgmt_site = web.TCPSite(mgmt_runner, config.host, config.management_port)
    await mgmt_site.start()
    logging.info(f"Started management API on {config.host}:{config.management_port}")

    # Run forever
    await asyncio.Event().wait()

def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    
    parser = argparse.ArgumentParser(description="Async HTTP Proxy with Circuit Breaker")
    parser.add_argument("-c", "--config", help="Path to config file", default=None)
    args = parser.parse_args()

    if args.config:
        config = load_config(args.config)
    else:
        # Default config
        config = ProxyConfig(host="127.0.0.1", port=8080, management_port=9090, upstream_url="http://127.0.0.1:9000")

    try:
        asyncio.run(start_servers(config))
    except KeyboardInterrupt:
        logging.info("Shutting down.")

if __name__ == "__main__":
    main()
