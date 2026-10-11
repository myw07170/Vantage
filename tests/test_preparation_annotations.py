"""AI-assisted scope, non-destructive v3 migration and version-safe reader notes."""
import asyncio
import copy
import json
import sqlite3
import pytest
import httpx
from app import main
from app.core import db, preparation, annotations, versions, llm
from app.core.models import ReportContent, ReportItem

@pytest.fixture
async def client(offline):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test") as c:
        yield c
    await main.preparer.close()
    await main.runner.close()

async def prepared(client, query="Compare Notion + Obsidian for offline research"):
    t = (await client.post("/api/tasks",json={"query":query})).json()
    response = await client.post(f"/api/tasks/{t['task_id']}/prepare",json={})
    assert response.status_code == 202, response.text
    await main.preparer.jobs[t["task_id"]]
    return db.get_task(t["task_id"])

async def test_ai_prefills_scope_but_never_starts_research(client, offline):
    t = await prepared(client)
    p = t["payload"]["preparation"]
    assert t["status"] == "awaiting_confirmation" and p["status"] == "ready"
    assert [v["name"] for v in p["proposal"]["products"]] == ["Notion","Obsidian"]
    assert all(v["website"] and v["website_status"] == "verified" and not v["confirmed"] for v in p["proposal"]["products"])
    assert p["proposal"]["summary"] and len(p["proposal"]["topics"]) == 3
    assert not main.runner.jobs and not db.list_reports()
    calls = len(offline.operations)
    for _ in range(2):
        await client.get(f"/api/tasks/{t['task_id']}")
        response = await client.post(f"/api/tasks/{t['task_id']}/prepare",json={})
        assert response.status_code == 202
    assert len(offline.operations) == calls

async def test_missing_product_is_a_question_not_an_added_competitor(client):
    t = await prepared(client, "Compare Notion for a small team")
    p = t["payload"]["preparation"]
    assert len(p["proposal"]["products"]) == 1 and p["proposal"]["questions"]
    response = await client.post(f"/api/tasks/{t['task_id']}/prepare",json={"base_revision":p["revision"],"answers":{"products":"Obsidian"}})
    await main.preparer.jobs[t["task_id"]]
    p2 = db.get_task(t["task_id"])["payload"]["preparation"]
    assert p2["answers"]["products"] == "Obsidian"
    assert len(p2["proposal"]["products"]) == 2
    assert (await client.post(f"/api/tasks/{t['task_id']}/prepare",json={"base_revision":0,"answers":{"products":"Figma"}})).status_code == 409

async def test_unverified_site_remains_a_proposal(client, monkeypatch):
    monkeypatch.setattr(preparation,"fetch_page",lambda *a,**kw: {"text":"Different software", "blocked":False})
    t = await prepared(client)
    assert all(p["website_status"] == "unverified" and not p["confirmed"] for p in t["payload"]["preparation"]["proposal"]["products"])

async def test_namesake_options_only_include_user_named_products(client, monkeypatch):
    def proposal(*a,**kw):
        return {'summary':'Confirm which Notion you mean.', 'products':[
            {'id':'notion','name':'Notion','mentioned_as':'Notion','website':'https://www.notion.com'},
            {'id':'invented','name':'Invented rival','mentioned_as':'Invented rival','website':'https://rival.test'}],
            'questions':[{'id':'identity','question':'Which Notion product?','type':'single','options':['Notion workspace software','Notion music notation'],'required':True}]}
    monkeypatch.setattr(llm,'chat_json',proposal)
    t = await prepared(client,'Compare Notion software')
    p = t['payload']['preparation']['proposal']
    assert len(p['products']) == 1 and len(p['questions'][0]['options']) == 2
    assert not p['products'][0]['confirmed']

async def test_user_edits_survive_ai_followup_and_start_preserves_preparation(client, scope):
    t = await prepared(client)
    p = t['payload']['preparation']
    draft = copy.deepcopy(p['proposal'])
    draft['products'][0]['category'] = 'A user-defined workflow category'
    draft['topics'][0]['focus'] = ['A user-specific constraint']
    draft['limitations'] = 'For a three-person offline research team.'
    await client.post(f"/api/tasks/{t['task_id']}/prepare", json={'base_revision':p['revision'],'answers':{},'draft_scope':draft})
    await main.preparer.jobs[t['task_id']]
    updated = db.get_task(t['task_id'])['payload']['preparation']
    assert updated['proposal']['products'][0]['category'] == draft['products'][0]['category']
    assert updated['proposal']['topics'][0]['focus'] == ['A user-specific constraint']
    assert updated['proposal']['limitations'] == draft['limitations']
    await client.post(f"/api/tasks/{t['task_id']}/start",json=scope)
    await main.runner.jobs[t['task_id']].worker
    assert db.get_task(t['task_id'])['payload']['preparation'] == updated
    assert db.get_task(t['task_id'])['checkpoint']['visualization']['activity']

async def test_external_failure_keeps_prefilled_fields(client, monkeypatch):
    def failure(*a,**kw):
        raise RuntimeError("External lookup failed")
    monkeypatch.setattr(preparation,"search",failure)
    t = await prepared(client)
    p = t["payload"]["preparation"]
    assert p["status"] == "failed" and p["proposal"]["products"]
    assert "External lookup failed" in p["error"]
    assert t["status"] == "awaiting_confirmation" and db.list_reports() == []

async def test_prepare_deduplicates_running_request_and_interrupts_without_calls(client, monkeypatch):
    entered, finish = asyncio.Event(), asyncio.Event()
    original = preparation.worker
    async def slow(*a,**kw):
        entered.set()
        await finish.wait()
        return await original(*a,**kw)
    monkeypatch.setattr(preparation,"worker",slow)
    t = (await client.post("/api/tasks",json={"query":"Notion vs Obsidian"})).json()
    path = f"/api/tasks/{t['task_id']}/prepare"
    await client.post(path,json={})
    await entered.wait()
    job = main.preparer.jobs[t["task_id"]]
    assert (await client.post(path,json={})).status_code == 202
    assert main.preparer.jobs[t["task_id"]] is job
    assert (await client.post(path,json={"base_revision":1,"answers":{"x":"other"}})).status_code == 409
    await main.preparer.close()
    assert db.get_task(t["task_id"])["payload"]["preparation"]["status"] == "interrupted"
    assert not db.list_reports()

async def test_prepare_budget_failure_has_explicit_retry_and_no_fake_result(client, offline):
    offline.settings.scope_time_limit_seconds = .000001
    t = await prepared(client)
    assert t["payload"]["preparation"]["status"] == "failed"
    assert t["payload"]["preparation"]["usage"]["elapsed_seconds"] >= 0
    assert db.list_reports() == []

async def test_preparation_budget_is_cumulative_and_excludes_answer_waiting(client, offline):
    t = await prepared(client)
    p = t['payload']['preparation']
    # A long wall-clock gap between answers is deliberately irrelevant: only
    # persisted execution usage is subtracted from the next preparation budget.
    p['usage'].update(tokens=123, elapsed_seconds=1.25)
    p['started_at'] = '2000-01-01T00:00:00Z'
    with db._connect() as c:
        c.execute('UPDATE tasks SET payload=? WHERE task_id=?',(json.dumps({'preparation':p}),t['task_id']))
    await client.post(f"/api/tasks/{t['task_id']}/prepare",json={'base_revision':p['revision']})
    await main.preparer.jobs[t['task_id']]
    updated = db.get_task(t['task_id'])['payload']['preparation']
    assert updated['status'] == 'ready'
    assert updated['usage']['tokens'] >= 123
    assert 1.25 <= updated['usage']['elapsed_seconds'] < 10
    updated['usage']['tokens'] = offline.settings.scope_token_limit
    with db._connect() as c:
        c.execute('UPDATE tasks SET payload=? WHERE task_id=?',(json.dumps({'preparation':updated}),t['task_id']))
    await client.post(f"/api/tasks/{t['task_id']}/prepare",json={'base_revision':updated['revision']})
    await main.preparer.jobs[t['task_id']]
    assert db.get_task(t['task_id'])['payload']['preparation']['status'] == 'failed'

async def test_restart_interrupts_preparation_and_queries_do_not_resume_it(client, offline):
    task_id = db.save_task('Notion vs Obsidian')['task_id']
    with db._connect() as c:
        c.execute("UPDATE tasks SET status='preparing',payload=? WHERE task_id=?",(json.dumps({'preparation':{'revision':1,'status':'running','answers':{}}}),task_id))
    operations = len(offline.operations)
    db.interrupt_running_tasks()
    restored = (await client.get(f'/api/tasks/{task_id}')).json()
    assert restored['status'] == 'awaiting_confirmation'
    assert restored['payload']['preparation']['status'] == 'interrupted'
    assert len(offline.operations) == operations and not main.preparer.jobs

async def test_terminal_checkpoint_stops_unfinished_role_animation(offline):
    from app.core.tasks import Job, TaskRunner
    task = db.save_task('Notion vs Obsidian')
    db.claim_task(task['task_id'])
    runner, job = TaskRunner(), Job(task_id=task['task_id'])
    await runner._publish(job, {'type':'role','data':{'role':'analyst','status':'working','detail':'Reworking affected items.'}})
    await runner._publish(job, {'type':'done','data':{'report_id':'saved','version_id':'partial'}})
    visual = db.get_task(task['task_id'])['checkpoint']['visualization']
    assert visual['percent'] == 100 and visual['roles']['analyst']['status'] == 'stopped'
    assert 'retained' in visual['roles']['analyst']['detail']

@pytest.fixture
def saved(offline, scope):
    content = ReportContent(products=scope["products"],topics=scope["topics"],checked_at="2026-10-10T12:00:00Z",changes_since="2026-07-12").model_dump()
    content["comparison"] = [ReportItem(id="first", product_id="notion", topic_id="features",text="Hello 😀 repeated text. And repeated text.").model_dump(),
                             ReportItem(id="second",product_id="obsidian",topic_id="features",text="Second paragraph.").model_dump()]
    return db.create_version(None,content,"research")

def body(saved, start=6, end=8, quote="😀"):
    return annotations.AnnotationBody(version_id=saved["version_id"], anchors=[{"item_id":"first","start":start,"end":end,"quote":quote}],color="sun",comment="Check this exact passage.")

def test_utf16_offsets_and_four_colors_preserve_review(saved):
    rid,vid = saved["report_id"],saved["version_id"]
    before = copy.deepcopy(saved["content"])
    for color in ("sun","ok","risk","info"):
        b = body(saved); b.color = color
        n = annotations.create(rid,b)
        assert n["anchors"][0]["quote"] == "😀"
    assert len(annotations.list_annotations(rid,vid)) == 4
    assert db.get_version(rid,vid)["content"] == before
    assert len(db.list_versions(rid)) == 1

@pytest.mark.parametrize("start,end,quote",[(6,7,"x"),(7,8,"x"),(6,8,"wrong"),(999,1000,"x")])
def test_bad_or_surrogate_split_anchor_rejected(saved,start,end,quote):
    with pytest.raises(ValueError):
        annotations.create(saved["report_id"],body(saved,start,end,quote))
    assert annotations.list_annotations(saved["report_id"],saved["version_id"]) == []

def test_whitespace_and_multiblock_annotation(saved):
    b = body(saved,8,9," ")
    b.anchors.append(annotations.Anchor(item_id="second",start=0,end=6,quote="Second"))
    note = annotations.create(saved["report_id"],b)
    assert note["anchors"][0]["quote"] == " "
    assert len(note["anchors"]) == 2

def test_annotation_conflicts_and_history_are_read_only(saved):
    rid,vid = saved["report_id"],saved["version_id"]
    n = annotations.create(rid,body(saved))
    changed = annotations.mutate(rid,n["annotation_id"],vid,1,{"comment":"Updated","color":"risk"})
    assert changed["revision"] == 2
    with pytest.raises(db.Conflict):
        annotations.mutate(rid,n["annotation_id"],vid,1,{"comment":"stale"})
    new = versions.edit(rid,vid,{"second":"Human edit"})
    with pytest.raises(db.Conflict):
        annotations.create(rid,body(saved))
    with pytest.raises(db.Conflict):
        annotations.mutate(rid,n["annotation_id"],vid,2)
    inherited = annotations.list_annotations(rid,new["version_id"])
    assert inherited[0]["comment"] == "Updated" and inherited[0]["anchor_status"] == "active"
    assert annotations.list_annotations(rid,vid)[0] == changed

def test_apply_uses_latest_base_annotations_and_restore_uses_historical_notes(saved):
    rid,vid = saved["report_id"],saved["version_id"]
    n = annotations.create(rid,body(saved))
    candidate = db.create_version(rid,saved["content"],"followup",base_version_id=vid,candidate=True)
    annotations.mutate(rid,n["annotation_id"],vid,1,{"comment":"Added after candidate creation"})
    applied = versions.apply(rid,vid,candidate["version_id"])
    assert annotations.list_annotations(rid,applied["version_id"])[0]["comment"] == "Added after candidate creation"
    assert annotations.list_annotations(rid,candidate["version_id"])[0]["comment"] != "Added after candidate creation"
    restored = versions.restore(rid,applied["version_id"],vid)
    assert annotations.list_annotations(rid,restored["version_id"])[0]["comment"] == "Added after candidate creation"

def test_changed_passage_reanchors_uniquely_or_is_retained_unanchored(saved):
    rid,vid = saved["report_id"],saved["version_id"]
    annotations.create(rid,body(saved))
    shifted = versions.edit(rid,vid,{"first":"New prefix. "+saved["content"]["comparison"][0]["text"]})
    note = annotations.list_annotations(rid,shifted["version_id"])[0]
    assert note["anchor_status"] == "active" and note["anchors"][0]["start"] == 18
    changed = versions.edit(rid,shifted["version_id"],{"first":"Emoji removed from the source."})
    retained = annotations.list_annotations(rid,changed["version_id"])[0]
    assert retained["anchor_status"] == "unanchored" and retained["comment"]

def test_repeated_passage_keeps_exact_occurrence(saved):
    rid,vid = saved["report_id"],saved["version_id"]
    note = annotations.create(rid,body(saved,28,41,"repeated text"))
    assert note["anchors"][0]["start"] == 28
    updated = versions.edit(rid,vid,{"second":"Unrelated correction"})
    assert annotations.list_annotations(rid,updated["version_id"])[0]["anchors"][0]["start"] == 28

def test_changed_context_cannot_silently_move_a_note_to_another_occurrence(saved):
    rid,vid = saved['report_id'],saved['version_id']
    annotations.create(rid,body(saved))
    changed = versions.edit(rid,vid,{'first':'Other 😀 unrelated context.'})
    note = annotations.list_annotations(rid,changed['version_id'])[0]
    assert note['anchor_status'] == 'unanchored'

async def test_annotation_api_revision_and_delete(client,saved):
    rid = saved["report_id"]
    created = await client.post(f"/api/reports/{rid}/annotations",json=body(saved).model_dump())
    assert created.status_code == 201
    note = created.json()
    path = f"/api/reports/{rid}/annotations/{note['annotation_id']}"
    assert (await client.patch(path,json={"version_id":saved["version_id"],"revision":1,"color":"info"})).status_code == 200
    assert (await client.delete(path,params={"version_id":saved["version_id"],"revision":1})).status_code == 409
    assert (await client.delete(path,params={"version_id":saved["version_id"],"revision":2})).status_code == 200

def test_v2_to_v3_retains_versions_configuration_and_rolls_back_failure(saved):
    conn = db._connect()
    conn.execute("DROP TABLE annotations")
    conn.execute("PRAGMA user_version=2")
    conn.execute("CREATE TABLE app_config (data TEXT)")
    conn.execute("INSERT INTO app_config VALUES('keep')")
    conn.commit()
    db._init_schema(conn)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 3
    assert db.get_version(saved["report_id"],saved["version_id"])["content"] == saved["content"]
    assert conn.execute("SELECT data FROM app_config").fetchone()[0] == "keep"
    db._init_schema(conn)
    assert len(db.list_reports()) == 1

def test_v3_migration_failure_rolls_back_without_resetting_v2(saved):
    original = db._connect()
    original.execute('DROP TABLE annotations')
    original.execute('PRAGMA user_version=2')
    original.commit()
    class FailingConnection(sqlite3.Connection):
        def execute(self,sql,*a,**kw):
            if sql.startswith('CREATE TABLE annotations'):
                raise sqlite3.OperationalError('migration failed')
            return super().execute(sql,*a,**kw)
    c = sqlite3.connect(db._DB_PATH,factory=FailingConnection)
    with pytest.raises(sqlite3.OperationalError):
        db._init_schema(c)
    assert c.execute('PRAGMA user_version').fetchone()[0] == 2
    assert c.execute('SELECT report_id FROM reports').fetchone()[0] == saved['report_id']
    c.close()
