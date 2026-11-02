import yaml

with open('config.yaml', 'r') as f:
    config = yaml.safe_load(f)

config['health_check'] = {
    'enabled': True,
    'endpoint': '/health',
    'interval_seconds': 10.0,
    'timeout_seconds': 2.0
}

with open('config.yaml', 'w') as f:
    yaml.dump(config, f, default_flow_style=False)
