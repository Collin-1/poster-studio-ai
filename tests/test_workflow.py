import json
from xml.etree import ElementTree
import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.providers import MockProvider, ReplayProvider, run_agent, OpenAIProvider
from backend.svg import render_svg


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('DATABASE_PATH', str(tmp_path / 'test.db'))
    monkeypatch.delenv('RECORD_PATH', raising=False)
    return TestClient(app)


def new(client, provider='mock'):
    response = client.post('/api/projects', json={'name': 'After Hours', 'provider': provider})
    assert response.status_code == 201
    return response.json()


def action(client, p, name, **kwargs):
    return client.post(f"/api/projects/{p['id']}/actions", json={'action': name, 'expected_version': p['version'], **kwargs})


def ready(client, provider='mock'):
    p = new(client, provider)
    p = action(client, p, 'message', message='Design evening for local creatives, 24 November at Studio 04').json()
    assert p['state'] == 'brief_review'
    p = action(client, p, 'approve_brief').json()
    assert p['state'] == 'copy_review'
    p = action(client, p, 'approve_copy', copy={'headline':'Ideas & <possibilities>', 'supporting':'24 November · Studio 04', 'cta':'Book now'}).json()
    assert p['state'] == 'ready_to_design'
    return p


@pytest.mark.parametrize('provider', ['mock', 'replay'])
def test_full_workflow_persistence_and_export(client, provider):
    p = ready(client, provider)
    p = action(client, p, 'design').json()
    assert p['state'] == 'complete'
    assert p['revisions'] == 0
    assert p['copy']['headline'] == 'Ideas & <possibilities>'
    assert '&amp;' in p['svg'] and '&lt;possibilities&gt;' in p['svg']
    root = ElementTree.fromstring(p['svg'])
    assert 'Ideas & <possibilities>' in ' '.join(root.itertext())
    assert client.get(f"/api/projects/{p['id']}").json() == p
    assert p in client.get('/api/projects').json()
    response = client.get(f"/api/projects/{p['id']}/poster.svg")
    assert response.status_code == 200
    assert 'attachment' in response.headers['content-disposition']
    assert {l['agent'] for l in p['logs']} >= {'director','copywriter','designer','critic','human'}


def test_approval_gates_and_stale_write(client):
    p = new(client)
    assert action(client,p,'design').status_code == 409
    assert action(client,p,'approve_copy').status_code == 409
    q = action(client,p,'message',message='A poster').json()
    assert action(client,p,'approve_brief').status_code == 409
    assert action(client,q,'message',message='').status_code == 422


def test_one_revision_limit_and_manual_edits(client, monkeypatch):
    original = MockProvider.generate
    def generate(self, agent, context):
        if agent == 'critic': return {'passed':False,'score':50,'issues':['Needs visual attention'],'recommendation':'Use more contrast'}
        return original(self,agent,context)
    monkeypatch.setattr(MockProvider,'generate',generate)
    p = action(client,ready(client),'design').json()
    assert p['state'] == 'needs_attention'
    assert p['revisions'] == 1
    assert len(p['design_history']) == 2
    assert len([l for l in p['logs'] if l['agent']=='critic' and l['event']=='completed']) == 2
    assert action(client,p,'design').status_code == 409
    p = action(client,p,'edit_design',design=p['design']).json()
    assert p['revisions'] == 1


def test_failure_atomicity(client, monkeypatch):
    p = ready(client)
    monkeypatch.setattr(MockProvider,'generate',lambda *args: {'bad':'output'})
    assert action(client,p,'design').status_code == 502
    saved = client.get(f"/api/projects/{p['id']}").json()
    assert saved['state'] == 'ready_to_design' and saved['version'] == p['version']
    assert saved['logs'][-1]['event'] == 'error'


def test_contrast_is_enforced(client, monkeypatch):
    original = MockProvider.generate
    def generate(self, agent, context):
        output = original(self,agent,context)
        if agent=='designer': output.update(background='#ffffff', foreground='#ffffff')
        return output
    monkeypatch.setattr(MockProvider,'generate',generate)
    p = action(client,ready(client),'design').json()
    assert p['revisions']==1 and p['state']=='needs_attention'
    assert any('contrast' in x for x in p['critique']['issues'])


def test_record_and_exact_replay(tmp_path, monkeypatch):
    path=tmp_path/'calls.jsonl'
    monkeypatch.setenv('RECORD_PATH',str(path))
    context={'brief':{'title':'Hello','details':'An event'}}
    output=run_agent(MockProvider(),'copywriter',context)
    replay=ReplayProvider(path)
    assert replay.generate('copywriter',context)==output
    with pytest.raises(ValueError): replay.generate('copywriter',{})


@pytest.mark.parametrize('agent',['director','copywriter','designer','critic'])
def test_individual_agents(client,agent):
    response=client.post(f'/api/agents/{agent}/run',json={'provider':'mock','context':{}})
    assert response.status_code==200
    assert response.json()['agent']==agent
    assert client.get('/api/projects').json()==[]


def test_openai_adapter(monkeypatch):
    from types import SimpleNamespace
    import openai
    calls=[]
    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(output_text=json.dumps({'headline':'Hello','supporting':'World','cta':'Join'}))
    monkeypatch.setenv('OPENAI_API_KEY','test-key')
    monkeypatch.setattr(openai,'OpenAI',lambda **kwargs:SimpleNamespace(responses=SimpleNamespace(create=create)))
    assert run_agent(OpenAIProvider(),'copywriter',{'brief':{}})['headline']=='Hello'
    assert calls[0]['store'] is False
    assert calls[0]['text']['format']['strict'] is True


def test_invalid_inputs_and_missing_project(client):
    assert client.post('/api/projects',json={'name':'x','provider':'chatgpt'}).status_code==422
    assert client.get('/api/projects/missing').status_code==404
    p=new(client)
    assert client.get(f"/api/projects/{p['id']}/poster.svg").status_code==409
    assert client.post('/api/agents/unknown/run',json={}).status_code==404
