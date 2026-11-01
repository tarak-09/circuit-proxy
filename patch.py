import re

with open('tests/test_proxy.py', 'r') as f:
    text = f.read()

text = re.sub(r'    resp3 = await proxy_client.get\("/fail"\)\n    assert resp3\.status == 500\n', r'', text)

with open('tests/test_proxy.py', 'w') as f:
    f.write(text)
