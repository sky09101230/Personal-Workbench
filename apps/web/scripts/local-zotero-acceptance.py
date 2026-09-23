"""Isolated real HTTP browser acceptance. No production data or credentials."""
import importlib.util
import io
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading

ROOT = Path(__file__).resolve().parents[3]
TEMP = Path(tempfile.mkdtemp(prefix='local-agent-acceptance-', dir=ROOT / '.venv/tmp'))
os.environ['DATABASE_URL'] = f'sqlite:///{TEMP / "workbench.db"}'
os.environ['LITERATURE_VAULT_ROOT'] = str(TEMP / 'vault')
for key in ('ZOTERO_DATA_DIR', 'ZOTERO_USER_ID', 'ZOTERO_API_KEY', 'OPENALEX_API_KEY', 'DEEPSEEK_API_KEY', 'WORKBENCH_AGENT_TOKEN'):
    os.environ[key] = ''
sys.path.insert(0, str(ROOT / 'apps/api'))
from pypdf import PdfWriter
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from app.main import app
from app.modules.literature.domain.models import Paper, ExternalReference, Attachment
from app.modules.literature.domain.canonical import Ingestion

spec = importlib.util.spec_from_file_location('agent', ROOT / 'apps/zotero-agent/agent.py')
agent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agent)
zotero = TEMP / 'zotero'
zotero.mkdir()
with sqlite3.connect(zotero / 'zotero.sqlite') as db:
    db.executescript("CREATE TABLE settings(setting,key,value); CREATE TABLE libraries(libraryID,type); CREATE TABLE items(itemID,libraryID,key,version); CREATE TABLE itemAttachments(itemID,parentItemID,path,contentType,linkMode); INSERT INTO settings VALUES('account','userID','123'); INSERT INTO libraries VALUES(1,'user'); INSERT INTO items VALUES(1,1,'PARENT01',1),(2,1,'FILE0001',2),(3,1,'FILE0002',1); INSERT INTO itemAttachments VALUES(2,1,'storage:paper.pdf','application/pdf',1),(3,1,'storage:supplement.pdf','application/pdf',1);")
writer = PdfWriter()
writer.add_blank_page(300, 300)
output = io.BytesIO()
writer.write(output)
directory = zotero / 'storage/FILE0001'
directory.mkdir(parents=True)
(directory / 'paper.pdf').write_bytes(output.getvalue())
repo = app.state.local_transfer_service.repository
paper = Paper('fixture-parent', 'Local Zotero recovery acceptance', external_ref=ExternalReference('zotero', '123', 'PARENT01'))
pid = repo.ingest(Ingestion(paper, 'zotero_import', paper.id)).paper_id
assets = []
for key, name, role in [('FILE0001', 'paper.pdf', 'primary'), ('FILE0002', 'supplement.pdf', 'supplementary')]:
    source = repo.add_asset(Attachment('fixture-' + key, paper.id, name, 'application/pdf', True, external_ref=ExternalReference('zotero', '123', key), role=role))
    repo.record_asset_failure(source, 'source_unavailable')
    assets.append(source)
helper = agent.AgentServer(zotero, 'http://127.0.0.1:8014', 23120)
threading.Thread(target=helper.serve_forever, daemon=True).start()
print('Fixture pairing code: ' + helper.code, flush=True)
print('Fixture directory: ' + str(TEMP), flush=True)

@app.get('/probe', response_class=HTMLResponse)
def probe():
    return '''<!doctype html><html><meta charset="utf-8"><h1>Local Zotero transport probe</h1><label>Pairing code <input id="code"></label><button id="pair">Pair</button><button id="relay">Relay PDF</button><pre id="result"></pre><script>
let token=''; const result=document.querySelector('#result');
document.querySelector('#pair').onclick=async()=>{try {const r=await fetch('http://127.0.0.1:23120/v1/pair',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code:document.querySelector('#code').value})});const v=await r.json();token=v.token;result.textContent=JSON.stringify({status:r.status,...v,token:undefined});}catch(e){result.textContent='Agent blocked or unavailable: '+e.message;}};
document.querySelector('#relay').onclick=async()=>{try {const b='/api/literature/papers/PAPER/assets/ASSET';const i=await(await fetch(b+'/local-intent',{method:'POST'})).json();const r=await fetch('http://127.0.0.1:23120/v1/export',{method:'POST',headers:{'Content-Type':'application/json','Authorization':'Bearer '+token},body:JSON.stringify(i.source)});if(!r.ok) throw Error(await r.text());const obs=r.headers.get('X-Zotero-Observation');const pdf=await r.blob();const saved=await fetch(b+'/local-transfer',{method:'POST',headers:{'Content-Type':'application/pdf','X-Transfer-Intent':i.intent,'X-Zotero-Observation':obs},body:pdf});result.textContent=JSON.stringify(await saved.json());}catch(e){result.textContent=e.message;}};
</script></html>'''.replace('PAPER', pid).replace('ASSET', assets[0].id)

app.mount('/assets', StaticFiles(directory=ROOT / 'apps/web/dist/assets'), name='assets')

@app.get('/{path:path}')
def frontend(path: str):
    return FileResponse(ROOT / 'apps/web/dist/index.html')

if __name__ == '__main__':
    import uvicorn
    try:
        uvicorn.run(app, host='127.0.0.1', port=8014)
    finally:
        helper.shutdown()
        helper.server_close()
