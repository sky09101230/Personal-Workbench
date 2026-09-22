from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import io
import os
import sqlite3

import httpx
import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter

from app.main import app
from app.core.config import Settings
from app.modules.literature.application.errors import MigrationRequiredError, WorkflowConflictError
from app.modules.literature.application.ingestion import LiteratureIngestionService
from app.modules.literature.application.upload import UploadWorkflowService
from app.modules.literature.application.review import MetadataReviewService
from app.modules.literature.application.materialization import PdfMaterializationService
from app.modules.literature.application.zotero_import import ZoteroImportService
from app.modules.literature.application.service import LiteratureService
from app.modules.literature.domain.canonical import Ingestion, IdentityConflictError
from app.modules.literature.domain.models import Paper, Attachment, ExternalReference, ProviderFile, LibraryChanges, ChangedPaper, Collection, Note
from app.modules.literature.infrastructure.cache.workflows import SQLiteLiteratureWorkflowRepository
from app.modules.literature.infrastructure.cache.sqlite import SQLiteLiteratureRepository
from app.modules.literature.infrastructure.files import LocalLiteratureFiles
from app.modules.literature.infrastructure.extraction import extract_metadata
from app.modules.literature.infrastructure.providers.zotero.provider import ZoteroWebProvider
from .test_canonical_api import NoZotero, pdf_bytes


@pytest.fixture
def workflow(tmp_path, override_service):
    repository = SQLiteLiteratureWorkflowRepository(f"sqlite:///{tmp_path/'workflow.db'}")
    files = LocalLiteratureFiles(str(tmp_path/'files'))
    upload = UploadWorkflowService(repository,files,extract_metadata)
    review = MetadataReviewService(repository)
    override_service('upload_workflow_service', upload)
    override_service('metadata_review_service', review)
    override_service('literature_service', LiteratureService(NoZotero(),repository,files))
    override_service('literature_ingestion_service', LiteratureIngestionService(repository,files,lambda _: None))
    return repository, files, upload, review, TestClient(app)


def legacy(path):
    repository = SQLiteLiteratureRepository(f"sqlite:///{path}")
    repository.replace_library(provider='zotero',library_id='1',collections=(),papers=(Paper('old','Existing legacy paper'),),collection_papers={},notes=(),attachments=(),library_version='1')


def test_explicit_migration_guards_and_dry_run(tmp_path, override_service):
    path = tmp_path/'legacy.db'
    legacy(path)
    repository = SQLiteLiteratureWorkflowRepository(f"sqlite:///{path}")
    before = path.read_bytes()
    assert repository.migration_required
    with pytest.raises(MigrationRequiredError): repository.get_paper('old')
    with pytest.raises(MigrationRequiredError): repository.ingest(Ingestion(Paper('','Unsafe write'),'manual','x'))
    override_service('literature_service', LiteratureService(NoZotero(),repository))
    assert TestClient(app).get('/api/literature/papers').json()['detail']['code'] == 'migration_required'
    assert TestClient(app).get('/api/literature/status').status_code == 409
    assert TestClient(app).post('/api/literature/sync').status_code == 409
    dry = repository.run_migration(dry_run=True)
    assert dry['dry_run'] and dry['report']['canonical_documents'] == 1
    assert path.read_bytes() == before
    repository.ensure_schema()
    assert SQLiteLiteratureWorkflowRepository(f"sqlite:///{path}").migration_required
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: SQLiteLiteratureWorkflowRepository(f"sqlite:///{path}").run_migration(), range(2)))
    assert sum(r['status']=='migrated' for r in results) == 1
    assert repository.get_paper('old').paper.reading_status == 'saved'
    assert repository.run_migration()['status'] == 'already_migrated'


def test_existing_schema_upgrade_and_reconcile_once(tmp_path):
    path = tmp_path/'v1.db'
    legacy(path)
    repository = SQLiteLiteratureWorkflowRepository(f"sqlite:///{path}")
    repository.run_migration()
    canonical = repository.get_paper('old').paper.id
    with closing(sqlite3.connect(path)) as c, c:
        for table in ('literature_upload_items','literature_upload_batches','literature_metadata_proposals','literature_workflow_schema','literature_state_edits','literature_maintenance_actions'):
            c.execute(f'DROP TABLE {table}')
        c.execute("UPDATE literature_documents SET reading_status='inbox'")
    upgraded = SQLiteLiteratureWorkflowRepository(f"sqlite:///{path}")
    assert not upgraded.migration_required
    assert upgraded.create_upload_batch().status == 'staging'
    assert upgraded.reconcile_reading_status()['corrected'] == 1
    upgraded.set_state(canonical,reading_status='inbox')
    assert upgraded.reconcile_reading_status()['corrected'] == 0
    assert upgraded.get_paper(canonical).paper.reading_status == 'inbox'


def test_sources_and_origins_are_separate(workflow):
    repository,_,_,_,client = workflow
    paper = Paper('external','A distinct imported paper',external_ref=ExternalReference('zotero','1','A'))
    result = repository.ingest(Ingestion(paper,'radar','run-1'))
    data = client.get('/api/literature/papers/'+result.paper_id).json()['paper']
    assert data['sources']==['zotero'] and data['origins']==['radar']


def test_staging_paths_hash_retry_and_legacy_open(workflow,tmp_path):
    _,files,_,_,_ = workflow
    data=pdf_bytes()
    key,digest=files.stage_pdf(data,'../bad.pdf')
    with pytest.raises(ValueError): files.finalize_pdf('../outside.pending',digest)
    with pytest.raises(ValueError): files.finalize_pdf(key,'../bad')
    with pytest.raises(ValueError): files.finalize_pdf(key,'0'*64)
    assert (files.staging/key).exists()
    stored=files.finalize_pdf(key,digest,keep_staging=True)
    assert files.finalize_pdf(key,digest)==stored
    assert not (files.staging/key).exists()
    old=LocalLiteratureFiles(str(tmp_path/'old-files'))
    old.root.mkdir()
    (old.root/stored).write_bytes(data)
    opened=old.open(Attachment('asset','paper','old.pdf','application/pdf',True,storage_kind='local',storage_key=stored),range_header='bytes=0-9')
    assert b''.join(opened.chunks)==data[:10]


def test_upload_review_confirm_cancel_and_duplicate(workflow):
    repository,files,upload,_,client=workflow
    batch=client.post('/api/literature/uploads/batches').json()
    response=client.post(f"/api/literature/uploads/batches/{batch['id']}/files?filename=paper.pdf",content=pdf_bytes())
    assert response.status_code==201,response.text
    item=response.json()
    assert item['status']=='needs_review' and repository.list_papers().total==0
    failed=client.post(f"/api/literature/uploads/batches/{batch['id']}/confirm").json()
    assert failed['results'][0]['status']=='needs_review'
    assert (files.staging/item['staging_key']).exists()
    edited=client.patch(f"/api/literature/uploads/batches/{batch['id']}/items/{item['id']}",json={'title':'Reviewed staged PDF','authors':['Alice'],'year':2026,'doi':'https://doi.org/10.1234/Review'})
    assert edited.status_code==200
    first=client.post(f"/api/literature/uploads/batches/{batch['id']}/confirm").json()['results'][0]
    assert first['status']=='confirmed'
    second=client.post(f"/api/literature/uploads/batches/{batch['id']}/confirm").json()['results'][0]
    assert second['paper_id']==first['paper_id'] and second['status']=='already_confirmed'
    assert repository.get_paper(first['paper_id']).paper.doi=='10.1234/review'
    assert repository.get_paper(first['paper_id']).paper.reading_status=='saved'
    assert client.get(f"/api/literature/papers/{first['paper_id']}/pdf").content==pdf_bytes()
    batch2=upload.create_batch()
    item2=upload.stage_file(batch2.id,'again.pdf',pdf_bytes())
    upload.update_item_metadata(batch2.id,item2.id,{'title':'Reviewed staged PDF'})
    assert upload.confirm_batch(batch2.id)[0]['paper_id']==first['paper_id']
    third=upload.create_batch()
    item3=upload.stage_file(third.id,'cancel.pdf',pdf_bytes(200))
    upload.cancel_batch(third.id)
    assert not (files.staging/item3.staging_key).exists()
    assert (files.originals/(item['sha256']+'.pdf')).exists()
    assert client.post(f'/api/literature/uploads/batches/{third.id}/confirm').status_code==409


def test_upload_retry_cleanup_and_concurrent_confirm(workflow):
    repository,files,upload,_,_=workflow
    existing=repository.ingest(Ingestion(Paper('','Shared title for identity conflict',('Alice',),year=2026,doi='10.1234/one'),'manual','one'))
    batch=upload.create_batch()
    item=upload.stage_file(batch.id,'conflict.pdf',pdf_bytes())
    upload.update_item_metadata(batch.id,item.id,{'title':'Shared title for identity conflict','authors':['Alice'],'year':2026,'doi':'10.1234/two'})
    assert upload.confirm_batch(batch.id)[0]['status']=='conflict'
    os.utime(files.staging/item.staging_key,(1,1))
    orphan,_=files.stage_pdf(pdf_bytes(150),'orphan.pdf')
    os.utime(files.staging/orphan,(1,1))
    assert upload.cleanup(3600)['removed']==1
    assert (files.staging/item.staging_key).exists()
    upload.update_item_metadata(batch.id,item.id,{'doi':'10.1234/one'})
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:upload.confirm_batch(batch.id),range(2)))
    assert {r[0]['paper_id'] for r in results}=={existing.paper_id}
    assert len(repository.list_attachments(existing.paper_id))==1


def test_proposal_alias_conflicts_stale_and_audit(workflow):
    repository,_,_,review,client=workflow
    canonical=repository.ingest(Ingestion(Paper('legacy','Paper for metadata review'),'manual','one')).paper_id
    first=review.create_proposal('legacy','pdf_extraction',{'doi':'https://doi.org/10.1234/ABC','title':'Reviewed title'})
    stale=review.create_proposal(canonical,'manual',{'journal':'Journal'})
    assert first.paper_id==canonical
    assert review.accept_proposal(first.id).status=='accepted'
    assert repository.get_paper(canonical).paper.doi=='10.1234/abc'
    assert repository.ingest(Ingestion(Paper('','Another title',doi='10.1234/abc'),'manual','two')).paper_id==canonical
    with pytest.raises(WorkflowConflictError): review.accept_proposal(stale.id)
    assert review.reject_proposal(stale.id).status=='rejected'
    proposal=review.create_proposal(canonical,'manual',{'abstract':'Original proposed abstract'})
    response=client.post(f'/api/literature/metadata/proposals/{proposal.id}/edit-accept',json={'edits':{'doi':'10.1234/other'}})
    assert response.status_code==409,response.text
    assert review.get_proposal(proposal.id).status=='pending'
    with pytest.raises(IdentityConflictError):
        review.edit_and_accept(proposal.id,{'doi':'10.48550/arxiv.2609.12345'})
    assert client.post(f'/api/literature/metadata/proposals/{proposal.id}/edit-accept',json={'edits':{'id':'hijack'}}).status_code==422
    assert review.edit_and_accept(proposal.id,{'abstract':'User edited abstract'}).proposed_metadata['abstract']=='User edited abstract'
    assert review.get_proposal(proposal.id).proposed_metadata['abstract']=='User edited abstract'
    assert repository.provenance(canonical)['metadata_evidence'][-1]['evidence']['after']['abstract']=='User edited abstract'


def test_proposal_other_identity_and_concurrent_decision(workflow):
    repository,_,_,review,_=workflow
    a=repository.ingest(Ingestion(Paper('','First metadata record'),'manual','a')).paper_id
    repository.ingest(Ingestion(Paper('','Second metadata record',doi='10.1234/owned'),'manual','b'))
    conflict = review.create_proposal(a,'manual',{'doi':'10.1234/owned'})
    assert conflict.identity_conflict
    with pytest.raises(IdentityConflictError): review.accept_proposal(conflict.id)
    assert review.reject_proposal(conflict.id).status == 'rejected'
    proposal=review.create_proposal(a,'manual',{'abstract':'Reviewed evidence'})
    def accept():
        try: return review.accept_proposal(proposal.id).status
        except WorkflowConflictError: return 'conflict'
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _:accept(),range(2)))==['accepted','conflict']


def test_extraction_metadata_and_no_text_warning():
    writer=PdfWriter(); writer.add_blank_page(width=100,height=100)
    writer.add_metadata({'/Title':'A real PDF metadata title','/Author':'Alice; Bob','/CreationDate':'D:20260921093000'})
    stream=io.BytesIO(); writer.write(stream)
    result=extract_metadata(stream.getvalue())
    assert result.title.value=='A real PDF metadata title'
    assert result.authors.value==('Alice','Bob')
    assert result.year.value==2026 and result.year.confidence=='low'
    assert 'short_text' in result.warnings and 'file_date_is_not_publication_date' in result.warnings
    assert extract_metadata(b'invalid').warnings==('invalid_pdf',)


def test_selective_import_and_materialization(workflow,override_service):
    repository,files,_,_,client=workflow
    p=Paper('zotero:1:ABCDEFGH','A selected Zotero paper',external_ref=ExternalReference('zotero','1','ABCDEFGH'))
    asset=Attachment('zotero:1:FILEKEY1',p.id,'main.pdf','application/pdf',True,external_ref=ExternalReference('zotero','1','FILEKEY1'))
    class Provider(NoZotero):
        closed=0
        calls=0
        def get_import_item(self,key):
            assert key==p.id
            return LibraryChanges(collections=(Collection('collection','Source collection'),),papers=(ChangedPaper(p,('collection',)),),attachments=(asset,),notes=(Note('note',p.id,'Imported note'),))
        def open_attachment(self,asset,**kwargs):
            self.calls+=1
            return ProviderFile(asset.filename,'application/pdf',(pdf_bytes(),),close=self.close)
        def close(self): self.closed+=1
    provider=Provider()
    importer=ZoteroImportService(repository,provider)
    materializer=PdfMaterializationService(repository,files,provider)
    override_service('zotero_import_service',importer)
    override_service('materialization_service',materializer)
    first=client.post('/api/literature/imports/zotero/selective',json={'item_keys':[p.id]}).json()['results'][0]
    canonical=first['paper_id']
    assert first['status']=='imported'
    assert importer.import_selected([p.id])[0].status=='already_exists'
    assert repository.get_paper(canonical).collections and repository.list_notes(canonical)
    assert repository.get_library_state(provider='zotero',library_id='1') is None
    key,digest=files.store_pdf(pdf_bytes(200),'supplement.pdf')
    repository.add_asset(Attachment('local-supp',canonical,'supplement.pdf','application/pdf',True,role='supplementary',storage_kind='local',storage_key=key,sha256=digest))
    result=materializer.materialize_paper(p.id)
    assert result.status=='materialized' and result.paper_id==canonical and provider.closed==1
    assert materializer.materialize_paper(canonical).status=='already_local' and provider.calls==1
    assert client.get('/api/literature/papers/'+canonical+'/pdf').content==pdf_bytes()
    assert materializer.materialize_batch([canonical,'missing']).failed==1


def test_materialization_closes_oversized_stream(workflow):
    repository,files,_,_,_=workflow
    canonical=repository.ingest(Ingestion(Paper('source','Oversized file paper'),'zotero_import','source')).paper_id
    repository.add_asset(Attachment('remote',canonical,'main.pdf','application/pdf',True))
    class Large(NoZotero):
        closed=False
        def open_attachment(self,*args,**kwargs):
            return ProviderFile('main.pdf','application/pdf',(),content_length=str(51*1024*1024),close=self.close)
        def close(self): self.closed=True
    provider=Large()
    assert PdfMaterializationService(repository,files,provider).materialize_paper(canonical).status=='pdf_failed'
    assert provider.closed and not files.originals.exists()


def test_provider_selective_identifier_and_children_mapping():
    settings=Settings('sqlite:///unused.db',[],'1','test-key')
    def handler(request):
        path=request.url.path
        if path.endswith('/items/ABCDEFGH'):
            data={'key':'ABCDEFGH','data':{'itemType':'journalArticle','title':'Selected title','collections':[]}}
        elif path.endswith('/items/ABCDEFGH/children'):
            data=[{'key':'FILEKEY1','data':{'itemType':'attachment','parentItem':'ABCDEFGH','filename':'main.pdf','contentType':'application/pdf','linkMode':'imported_file'}},{'key':'NOTEKEY1','data':{'itemType':'note','parentItem':'ABCDEFGH','note':'Source note'}}]
        elif path.endswith('/items/FILEKEY1/children'):
            data=[{'key':'ANNO0001','data':{'itemType':'annotation','parentItem':'FILEKEY1','annotationText':'Selection','annotationPageLabel':'1'}}]
        else: raise AssertionError(path)
        return httpx.Response(200,json=data)
    provider=ZoteroWebProvider(settings,httpx.Client(transport=httpx.MockTransport(handler)))
    result=provider.get_import_item('zotero:1:ABCDEFGH')
    assert len(result.notes)==2 and len(result.attachments)==1 and {n.kind for n in result.notes}=={'note','annotation'}
    with pytest.raises(ValueError): provider.get_import_item('zotero:other:ABCDEFGH')


def test_api_validation_missing_and_openapi(workflow):
    _,_,_,_,client=workflow
    assert client.get('/api/literature/uploads/batches/missing').status_code==404
    assert client.post('/api/literature/uploads/batches/missing/confirm').status_code==404
    assert client.post('/api/literature/metadata/proposals/missing/accept').status_code==404
    assert client.post('/api/literature/papers/materialize-pdfs',json={'paper_ids':['x']*51}).status_code==422
    batch=client.post('/api/literature/uploads/batches').json()
    assert client.post(f"/api/literature/uploads/batches/{batch['id']}/confirm").status_code==409
    paths=client.get('/openapi.json').json()['paths']
    assert '/api/literature/uploads/batches/{batch_id}/confirm' in paths
    assert '/api/literature/metadata/proposals/{proposal_id}/edit-accept' in paths


def test_partial_batch_cancel_preserves_confirmed_original(workflow):
    repository,files,upload,_,_=workflow
    batch=upload.create_batch()
    good=upload.stage_file(batch.id,'good.pdf',pdf_bytes())
    pending=upload.stage_file(batch.id,'pending.pdf',pdf_bytes(210))
    upload.update_item_metadata(batch.id,good.id,{'title':'Confirmed item survives partial cancel'})
    results=upload.confirm_batch(batch.id)
    assert {r['status'] for r in results}=={'confirmed','needs_review'}
    assert upload.get_batch(batch.id).status=='reviewing'
    upload.cancel_batch(batch.id)
    assert (files.originals/(good.sha256+'.pdf')).exists()
    assert not (files.staging/pending.staging_key).exists()
    assert repository.list_papers().total==1


def test_stream_failure_closes_and_cannot_expose_provider_error(workflow):
    repository,files,_,_,_=workflow
    canonical=repository.ingest(Ingestion(Paper('','Interrupted stream example'),'manual','interrupted')).paper_id
    repository.add_asset(Attachment('stream',canonical,'main.pdf','application/pdf',True))
    class Broken(NoZotero):
        closed=False
        def open_attachment(self,*args,**kwargs):
            def chunks():
                yield b'%PDF-'
                raise RuntimeError('private-provider-diagnostic')
            return ProviderFile('main.pdf','application/pdf',chunks(),close=self.close)
        def close(self): self.closed=True
    provider=Broken()
    result=PdfMaterializationService(repository,files,provider).materialize_paper(canonical)
    assert result.error=='materialization_failed' and provider.closed
    assert len(repository.list_attachments(canonical))==1


def test_reconcile_does_not_change_explicit_inbox_edit(tmp_path):
    path=tmp_path/'states.db'
    legacy(path)
    repository=SQLiteLiteratureWorkflowRepository(f'sqlite:///{path}')
    repository.run_migration()
    canonical=repository.get_paper('old').paper.id
    repository.set_state(canonical,reading_status='inbox')
    assert repository.reconcile_reading_status()['corrected']==0
    assert repository.get_paper(canonical).paper.reading_status=='inbox'
