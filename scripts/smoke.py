"""Exercise the running HTTP service and create a local demo project.

Run: python scripts/smoke.py [http://127.0.0.1:8000]
"""
import json
import re
import sys
from urllib.request import Request, urlopen

base = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8000'


def request(path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    with urlopen(Request(base + path, data=data, headers={'Content-Type': 'application/json'}), timeout=20) as response:
        return response.read()


def post(path, body):
    return json.loads(request(path, body))


html = request('/').decode()
assert 'Poster Studio AI' in html
for asset in re.findall(r'(?:src|href)="(/assets/[^"]+)"', html):
    assert request(asset), asset
project = post('/api/projects', {'name': 'After Hours · demo', 'provider': 'mock'})


def action(name, **kwargs):
    global project
    project = post(f"/api/projects/{project['id']}/actions", {'action': name, 'expected_version': project['version'], **kwargs})


action('message', message='A bold, welcoming evening of design talks for local creatives. 24 November at 18:00, Studio 04. Encourage people to save a seat.')
action('approve_brief')
action('approve_copy', copy={'headline': 'Ideas after hours.', 'supporting': 'Design talks. New perspectives. Good company. 24 November · 18:00 · Studio 04', 'cta': 'Save your seat'})
action('design')
assert project['state'] == 'complete'
assert b'<svg' in request(f"/api/projects/{project['id']}/poster.svg")
assert json.loads(request(f"/api/projects/{project['id']}"))['copy'] == project['copy']
for agent in ('director', 'copywriter', 'designer', 'critic'):
    assert 'output' in post(f'/api/agents/{agent}/run', {'provider': 'mock', 'context': {}})
print(f"HTTP smoke test passed. Demo project: {project['id']} ({len(project['logs'])} log entries).")
