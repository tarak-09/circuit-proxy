import argparse
import logging
from aiohttp import web
from .config import load_config, ProxyConfig
from .proxy import init_app

def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    
    parser = argparse.ArgumentParser(description="Async HTTP Proxy with Circuit Breaker")
    parser.add_argument("-c", "--config", help="Path to config file", default=None)
    args = parser.parse_args()

    if args.config:
        config = load_config(args.config)
    else:
        # Default config
        config = ProxyConfig(host="127.0.0.1", port=8080, upstream_url="http://127.0.0.1:9000")

    app = init_app(config)
    logging.info(f"Starting proxy on {config.host}:{config.port} routing to {config.upstream_url}")
    web.run_app(app, host=config.host, port=config.port)

if __name__ == "__main__":
    main()
