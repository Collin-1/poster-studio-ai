import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from .models import Brief, Copy, Design, OUTPUTS
from .providers import provider_for, run_agent
from .svg import render_svg, layout_metrics

load_dotenv()
app = FastAPI(title='Poster Studio AI', version='1.0.0')
app.add_middleware(CORSMiddleware, allow_origins=['http://localhost:5173', 'http://127.0.0.1:5173'], allow_methods=['GET', 'POST'], allow_headers=['Content-Type'])


@contextmanager
def database():
    path = Path(os.getenv('DATABASE_PATH', 'data/poster-studio.db'))
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=30)
    connection.execute('CREATE TABLE IF NOT EXISTS projects (id TEXT PRIMARY KEY, document TEXT NOT NULL)')
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def get(connection, project_id):
    row = connection.execute('SELECT document FROM projects WHERE id=?', (project_id,)).fetchone()
    if not row: raise HTTPException(404, 'Project not found')
    return json.loads(row[0])


def save(connection, project):
    connection.execute('INSERT OR REPLACE INTO projects VALUES (?,?)', (project['id'], json.dumps(project)))


def log(project, agent, event, detail):
    project['logs'].append({'time': datetime.now(timezone.utc).isoformat(), 'agent': agent, 'event': event, 'detail': detail})


def execute(project, agent, context):
    log(project, agent, 'started', f"Provider: {project['provider']}")
    output = run_agent(provider_for(project['provider']), agent, context)
    log(project, agent, 'completed', output)
    return output


class NewProject(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    provider: Literal['mock', 'replay', 'openai'] = Field(default_factory=lambda: os.getenv('AI_PROVIDER', 'mock'))


class Action(BaseModel):
    action: Literal['message', 'approve_brief', 'revise_copy', 'approve_copy', 'design', 'edit_design']
    expected_version: int
    message: str = Field(default='', max_length=4000)
    brief: Brief | None = None
    approved_copy: Copy | None = Field(default=None, alias='copy')
    design: Design | None = None


class Experiment(BaseModel):
    provider: Literal['mock', 'replay', 'openai'] = 'mock'
    context: dict = Field(default_factory=dict)


@app.get('/api/health')
def health(): return {'status': 'ok'}


@app.get('/api/projects')
def list_projects():
    with database() as db:
        return [json.loads(r[0]) for r in db.execute('SELECT document FROM projects ORDER BY rowid DESC')]


@app.post('/api/projects', status_code=201)
def create_project(body: NewProject):
    project = {'id': str(uuid.uuid4()), 'name': body.name, 'provider': body.provider, 'state': 'collecting', 'version': 0,
               'messages': [], 'brief': None, 'copy': None, 'design': None, 'svg': None, 'critique': None,
               'revisions': 0, 'design_history': [], 'logs': []}
    log(project, 'director', 'handoff', 'Tell me about your poster: purpose, audience, essential details and desired style.')
    with database() as db: save(db, project)
    return project


@app.get('/api/projects/{project_id}')
def read_project(project_id: str):
    with database() as db: return get(db, project_id)


def require(project, states):
    if project['state'] not in states:
        raise HTTPException(409, f"Action unavailable in state {project['state']}; expected {', '.join(states)}")


def evaluate(project):
    context = {'brief': project['brief'], 'copy': project['copy'], 'design': project['design'],
               'metrics': layout_metrics(project['copy'], project['design']), 'revision': project['revisions']}
    critique = execute(project, 'critic', context)
    for key in ('text_contrast', 'cta_contrast'):
        if context['metrics'][key] < 4.5:
            critique['passed'] = False
            critique['score'] = min(critique['score'], 60)
            critique['issues'].append(f'{key} is below 4.5:1')
    project['critique'] = critique


@app.post('/api/projects/{project_id}/actions')
def act(project_id: str, body: Action):
    # Serialize transitions across threads/processes and reject stale browser tabs.
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        project = get(db, project_id)
        if body.expected_version != project['version']:
            raise HTTPException(409, 'Project changed. Reload before retrying.')
        original = json.loads(json.dumps(project))
        try:
            if body.action == 'message':
                require(project, ['collecting', 'brief_review'])
                if not body.message.strip(): raise HTTPException(422, 'Enter a message')
                project['messages'].append({'role': 'user', 'content': body.message})
                result = execute(project, 'director', {'name': project['name'], 'messages': project['messages']})
                project['messages'].append({'role': 'assistant', 'content': result['message']})
                project['brief'] = result['brief']
                project['state'] = 'brief_review'
                log(project, 'director', 'awaiting_approval', 'Review the brief or continue the conversation.')
            elif body.action == 'approve_brief':
                require(project, ['brief_review'])
                if body.brief: project['brief'] = body.brief.model_dump()
                log(project, 'human', 'approved', {'brief': project['brief']})
                project['copy'] = execute(project, 'copywriter', {'brief': project['brief']})
                project['state'] = 'copy_review'
                log(project, 'copywriter', 'awaiting_approval', 'Review and edit the copy before approving.')
            elif body.action == 'revise_copy':
                require(project, ['copy_review'])
                if not body.message.strip(): raise HTTPException(422, 'Provide copy feedback')
                project['copy'] = execute(project, 'copywriter', {'brief': project['brief'], 'copy': project['copy'], 'feedback': body.message})
            elif body.action == 'approve_copy':
                require(project, ['copy_review'])
                if body.approved_copy: project['copy'] = body.approved_copy.model_dump()
                project['state'] = 'ready_to_design'
                log(project, 'human', 'approved', {'copy': project['copy']})
                log(project, 'designer', 'handoff', 'Approved brief and copy are ready. Generate when you choose.')
            elif body.action == 'design':
                require(project, ['ready_to_design'])
                project['design'] = execute(project, 'designer', {'brief': project['brief'], 'copy': project['copy']})
                project['design_history'].append(project['design'])
                evaluate(project)
                if not project['critique']['passed'] and project['revisions'] < 1:
                    project['revisions'] += 1
                    log(project, 'critic', 'revision_requested', project['critique'])
                    project['design'] = execute(project, 'designer', {'brief': project['brief'], 'copy': project['copy'], 'design': project['design'], 'feedback': project['critique']})
                    project['design_history'].append(project['design'])
                    evaluate(project)
                project['svg'] = render_svg(project['brief'], project['copy'], project['design'])
                project['state'] = 'complete' if project['critique']['passed'] else 'needs_attention'
                log(project, 'critic', 'handoff', 'Poster ready for human review. Automatic revision budget: at most one.')
            elif body.action == 'edit_design':
                require(project, ['complete', 'needs_attention'])
                if not body.design: raise HTTPException(422, 'Design is required')
                project['design'] = body.design.model_dump()
                project['design_history'].append(project['design'])
                evaluate(project)
                project['svg'] = render_svg(project['brief'], project['copy'], project['design'])
                project['state'] = 'complete' if project['critique']['passed'] else 'needs_attention'
                log(project, 'human', 'edited', 'Layout edited; critic rerun without automatic revision.')
            project['version'] += 1
            save(db, project)
        except HTTPException: raise
        except Exception as exc:
            # Failed transitions do not leave partially approved or generated state.
            log(original, 'system', 'error', f'{body.action} failed ({type(exc).__name__}). Check provider configuration and retry.')
            save(db, original)
            db.commit()
            raise HTTPException(502, 'Agent execution failed. Check provider credentials, response schema or replay recording; workflow state was preserved.') from exc
    return project


@app.get('/api/projects/{project_id}/poster.svg')
def download(project_id: str):
    with database() as db: project = get(db, project_id)
    if not project['svg']: raise HTTPException(409, 'Generate a poster first')
    return Response(project['svg'], media_type='image/svg+xml', headers={'Content-Disposition': 'attachment; filename="poster.svg"'})


@app.post('/api/agents/{agent}/run')
def experiment(agent: str, body: Experiment):
    if agent not in OUTPUTS: raise HTTPException(404, 'Unknown agent')
    try:
        output = run_agent(provider_for(body.provider), agent, body.context)
        result = {'agent': agent, 'output': output}
        if agent == 'designer' and body.context.get('brief') and body.context.get('copy'):
            brief = Brief.model_validate(body.context['brief']).model_dump()
            copy = Copy.model_validate(body.context['copy']).model_dump()
            result['svg'] = render_svg(brief, copy, output)
        return result
    except Exception as exc:
        raise HTTPException(422, f'Experiment failed ({type(exc).__name__}); check input and provider configuration.') from exc


dist = Path(__file__).resolve().parent.parent / 'frontend' / 'dist'
if dist.exists(): app.mount('/', StaticFiles(directory=dist, html=True), name='frontend')
