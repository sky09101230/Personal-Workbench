import importlib.util
import json
from pathlib import Path
import sqlite3
import threading
from urllib.request import Request, build_opener, ProxyHandler
from urllib.error import HTTPError

import pytest

spec = importlib.util.spec_from_file_location('zotero_agent', Path(__file__).parents[1] / 'agent.py')
agent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agent)
REQUEST = {'library_id': '123', 'item_key': 'FILE0001', 'parent_key': 'PARENT01'}


def fixture(root, data=b'%PDF-1.4\nfixture'):
    root.mkdir(exist_ok=True)
    with sqlite3.connect(root / 'zotero.sqlite') as db:
        db.executescript("CREATE TABLE settings(setting,key,value); CREATE TABLE libraries(libraryID,type); CREATE TABLE items(itemID,libraryID,key,version); CREATE TABLE itemAttachments(itemID,parentItemID,path,contentType,linkMode); CREATE TABLE deletedItems(itemID); INSERT INTO settings VALUES('account','userID','123'); INSERT INTO libraries VALUES(1,'user'); INSERT INTO items VALUES(1,1,'PARENT01',1),(2,1,'FILE0001',2); INSERT INTO itemAttachments VALUES(2,1,'storage:paper.pdf','application/pdf',1);")
    directory = root / 'storage' / 'FILE0001'
    directory.mkdir(parents=True)
    (directory / 'paper.pdf').write_bytes(data)
    return root


def test_snapshot_export_and_reject_missing_linked_wrong_account(tmp_path):
    fixture(tmp_path)
    reader = agent.ZoteroFiles(tmp_path)
    original = (tmp_path / 'zotero.sqlite').read_bytes()
    data, observed = reader.export(REQUEST)
    assert data.startswith(b'%PDF-') and observed['before'] == observed['after']
    assert (tmp_path / 'zotero.sqlite').read_bytes() == original
    with pytest.raises(agent.AgentError, match='account_mismatch'):
        reader.export({**REQUEST, 'library_id': '999'})
    with pytest.raises(agent.AgentError, match='parent_mismatch'):
        reader.export({**REQUEST, 'parent_key': 'PARENT02'})
    with sqlite3.connect(tmp_path / 'zotero.sqlite') as db:
        db.execute('UPDATE itemAttachments SET linkMode=2')
    with pytest.raises(agent.AgentError, match='linked_file'):
        reader.export(REQUEST)


@pytest.mark.parametrize('path', ['storage:../escape.pdf', 'storage:C:\\escape.pdf', 'storage:sub/escape.pdf'])
def test_paths_rejected(tmp_path, path):
    fixture(tmp_path)
    with sqlite3.connect(tmp_path / 'zotero.sqlite') as db:
        db.execute('UPDATE itemAttachments SET path=?', (path,))
    with pytest.raises(agent.AgentError, match='unsafe_path'):
        agent.ZoteroFiles(tmp_path).export(REQUEST)


def test_source_mutation_and_size(tmp_path, monkeypatch):
    fixture(tmp_path)
    reader = agent.ZoteroFiles(tmp_path)
    locate = reader.locate
    count = 0
    def changed(request):
        nonlocal count
        count += 1
        path, version = locate(request)
        if count == 2:
            path.write_bytes(b'%PDF-changed')
        return path, version
    monkeypatch.setattr(reader, 'locate', changed)
    with pytest.raises(agent.AgentError, match='source_changed'):
        reader.export(REQUEST)
    monkeypatch.setattr(agent, 'MAX_BYTES', 3)
    with pytest.raises(agent.AgentError, match='size_limit'):
        agent.ZoteroFiles(tmp_path).export(REQUEST)


def test_locked_database_snapshot(tmp_path):
    fixture(tmp_path)
    db = sqlite3.connect(tmp_path / 'zotero.sqlite')
    try:
        db.execute('BEGIN EXCLUSIVE')
        assert agent.ZoteroFiles(tmp_path).export(REQUEST)[0].startswith(b'%PDF-')
    finally:
        db.close()


def test_pairing_cors_expiry_and_restart(tmp_path):
    fixture(tmp_path)
    now = [100.0]
    server = agent.AgentServer(tmp_path, 'https://workbench.example', 0, clock=lambda: now[0])
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    def call(path, value, token='', origin=server.origin, host=None, method='POST'):
        headers = {'Origin': origin, 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token}
        if host:
            headers['Host'] = host
        request = Request(f'http://127.0.0.1:{server.server_port}{path}', json.dumps(value).encode(), headers, method=method)
        try:
            return build_opener(ProxyHandler({})).open(request, timeout=3)
        except HTTPError as e:
            return e
    try:
        assert call('/v1/export', REQUEST).code == 401
        denied = call('/v1/pair', {'code': server.code}, origin='https://evil.example')
        assert denied.code == 403 and 'Access-Control-Allow-Origin' not in denied.headers
        assert call('/v1/pair', {}, host='evil.example').code == 403
        assert call('/v1/export', {}, method='OPTIONS').headers['Access-Control-Allow-Origin'] == server.origin
        code = server.code
        paired = json.load(call('/v1/pair', {'code': code}))
        token = paired['token']
        assert call('/v1/pair', {'code': code}).code == 401
        response = call('/v1/export', REQUEST, token)
        assert response.code == 200 and response.read().startswith(b'%PDF-')
        assert 'X-Zotero-Observation' in response.headers
        now[0] += 1801
        assert call('/v1/export', REQUEST, token).code == 401
        for _ in range(5):
            call('/v1/pair', {'code': 'wrong'})
        assert call('/v1/pair', {'code': 'wrong'}).code == 429
        fresh = agent.AgentServer(tmp_path, server.origin, 0)
        try:
            assert fresh.session == '' and fresh.code != code
        finally:
            fresh.server_close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
