"""Version-scoped reader annotations, with UTF-16 anchors matching DOM ranges."""
from __future__ import annotations
import copy
import json
from typing import Literal
from pydantic import ConfigDict, Field
from app.core import db
from app.core.models import Contract, all_items, now

class Anchor(Contract):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=False)
    item_id: str
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    quote: str = Field(min_length=1, max_length=20000)
    prefix: str = Field(default="", max_length=100)
    suffix: str = Field(default="", max_length=100)

class AnnotationBody(Contract):
    version_id: str
    anchors: list[Anchor] = Field(min_length=1, max_length=100)
    color: Literal["sun", "ok", "risk", "info"] = "sun"
    comment: str = Field(default="", max_length=4000)

class AnnotationPatch(Contract):
    version_id: str
    revision: int = Field(ge=1)
    color: Literal["sun", "ok", "risk", "info"] | None = None
    comment: str | None = Field(default=None, max_length=4000)

def utf16_slice(text, start, end):
    try:
        return text.encode("utf-16-le")[start*2:end*2].decode("utf-16-le")
    except UnicodeDecodeError:
        raise ValueError("Anchor splits a UTF-16 character.")

def current(c, report_id, version_id):
    row = c.execute("SELECT current_version_id FROM reports WHERE report_id=?", (report_id,)).fetchone()
    if not row:
        raise KeyError("Report not found.")
    if row[0] != version_id:
        raise db.Conflict("The current version changed. Your annotation draft has been kept.")

def list_annotations(report_id, version_id):
    if not db.get_version(report_id, version_id):
        raise KeyError("Report version not found.")
    return [json.loads(r[0]) for r in db._connect().execute(
        "SELECT data FROM annotations WHERE report_id=? AND version_id=? ORDER BY rowid", (report_id, version_id))]

def create(report_id, body: AnnotationBody):
    with db._LOCK, db._connect() as c:
        c.execute("BEGIN IMMEDIATE")
        current(c, report_id, body.version_id)
        version = db.get_version(report_id, body.version_id)
        items = {i["id"]: i for i in all_items(version["content"])}
        anchors = []
        for a in body.anchors:
            text = items.get(a.item_id, {}).get("text")
            if text is None or a.end <= a.start or a.end > len(text.encode("utf-16-le")) // 2 or utf16_slice(text, a.start, a.end) != a.quote:
                raise ValueError("The selected passage does not match this saved version.")
            anchor = a.model_dump()
            anchor.update(prefix=utf16_slice(text, 0, a.start)[-32:],
                          suffix=utf16_slice(text, a.end, len(text.encode("utf-16-le"))//2)[:32])
            # Context should never split surrogate pairs.
            anchors.append(anchor)
        result = dict(annotation_id=db.uid("ann"), report_id=report_id, version_id=body.version_id,
                      anchors=anchors, color=body.color, comment=body.comment, revision=1,
                      created_at=now(), updated_at=now(), anchor_status="active")
        c.execute("INSERT INTO annotations VALUES(?,?,?,?)", (result["annotation_id"], report_id, body.version_id, json.dumps(result)))
    return result

def mutate(report_id, annotation_id, version_id, revision, patch=None):
    with db._LOCK, db._connect() as c:
        c.execute("BEGIN IMMEDIATE")
        current(c, report_id, version_id)
        row = c.execute("SELECT data FROM annotations WHERE annotation_id=? AND report_id=? AND version_id=?",
                        (annotation_id, report_id, version_id)).fetchone()
        if not row:
            raise KeyError("Annotation not found.")
        result = json.loads(row[0])
        if result["revision"] != revision:
            raise db.Conflict("This annotation changed. Your draft has been kept.")
        if patch is None:
            c.execute("DELETE FROM annotations WHERE annotation_id=?", (annotation_id,))
            return {"ok": True}
        result.update({k: v for k, v in patch.items() if v is not None and k in ("color", "comment")})
        result.update(revision=revision+1, updated_at=now())
        c.execute("UPDATE annotations SET data=? WHERE annotation_id=?", (json.dumps(result), annotation_id))
    return result

def inherit(c, report_id, source_id, target_id, content):
    """Called inside the version transaction. Never commits independently."""
    texts = {i["id"]: i["text"] for i in all_items(content)}
    source = c.execute('SELECT content FROM versions WHERE version_id=? AND report_id=?', (source_id, report_id)).fetchone()
    old_texts = {i['id']: i['text'] for i in all_items(json.loads(source[0]))} if source else {}
    for row in c.execute("SELECT data FROM annotations WHERE report_id=? AND version_id=?", (report_id, source_id)).fetchall():
        note = copy.deepcopy(json.loads(row[0]))
        active = True
        for a in note["anchors"]:
            text = texts.get(a["item_id"], "")
            try:
                unchanged = utf16_slice(text, a["start"], a["end"]) == a["quote"]
            except ValueError:
                unchanged = False
            if unchanged and text == old_texts.get(a['item_id']):
                continue
            positions, offset = [], 0
            while a["quote"] and (found := text.find(a["quote"], offset)) >= 0:
                end = found + len(a["quote"])
                if (not a["prefix"] or text[:found].endswith(a["prefix"])) and (not a["suffix"] or text[end:].startswith(a["suffix"])):
                    positions.append(found)
                offset = found + 1
            if len(positions) == 1:
                start = len(text[:positions[0]].encode("utf-16-le"))//2
                a.update(start=start, end=start+len(a["quote"].encode("utf-16-le"))//2)
            else:
                active = False
        note.update(annotation_id=db.uid("ann"), origin_id=note.get("origin_id", note["annotation_id"]),
                    version_id=target_id, revision=1, anchor_status="active" if active else "unanchored")
        c.execute("INSERT INTO annotations VALUES(?,?,?,?)", (note["annotation_id"], report_id, target_id, json.dumps(note)))
