"""Deterministic role responses: copy evidence, never invent commercial facts."""
from __future__ import annotations
import copy
import json

def complete(messages, kind: str, context: dict, json_mode: bool) -> str:
    if kind == "prepare":
        from app.core.models import DEFAULT_TOPICS
        text = context.get('query', '') + ' ' + json.dumps(context.get('answers', {}))
        catalog = [('Notion','https://www.notion.com'),('Obsidian','https://obsidian.md'),('Figma','https://www.figma.com'),('Sketch','https://www.sketch.com'),('Slack','https://slack.com'),('Microsoft Teams','https://www.microsoft.com/microsoft-teams')]
        products = [dict(id=name.lower().replace(' ','-'),name=name,mentioned_as=name,website=website,category='Software / SaaS') for name,website in catalog if name.casefold() in text.casefold()]
        result = dict(summary='[MOCK] Compare the products named in your request. Confirm their identities and your research focus.',products=products,topics=DEFAULT_TOPICS,
                      questions=[] if len(products)>1 else [dict(id='products',question='Which other software product would you like to compare?',type='text',options=[],required=True)],limitations='')
    elif kind == "json":
        result = copy.deepcopy(context.get("result", {}))
    elif kind == "collector":
        p, t = context["product"], context["topic"]
        if context.get("action") == "source_identity":
            result = {"sources": [{"evidence_id": e["evidence_id"], "identity_matches": False,
                                   "reason": "Mock cannot establish external product identity.", "quote": ""}
                                  for e in context.get("evidence", [])]}
        else:
            result = {"queries": [p["name"] + " " + t["name"]]}
    elif kind == "analyst":
        result = {"comparison": [], "brief": [], "changes": []}
        targeted = context.get("targets", [])
        if targeted:
            for old in targeted:
                item = copy.deepcopy(old)
                item.pop("review", None)
                relevant = [e for e in context["evidence"] if not item["product_id"] or e["product_id"] == item["product_id"]]
                if relevant:
                    ev = relevant[-1]
                    item.update(text="[MOCK] Source excerpt: " + ev["excerpt"][:350],
                                citations=[{"evidence_id": ev["evidence_id"], "quote": ev["excerpt"][:350]}])
                else:
                    item.update(text="[MOCK] No evidence found for this question.", citations=[])
                result[context.get("sections", {}).get(item["id"], "comparison")].append(item)
        else:
            for p in context["scope"]["products"]:
                for t in context["scope"]["topics"]:
                    ev = next((e for e in context["evidence"] if e["product_id"] == p["id"] and e["topic_id"] == t["id"]), None)
                    result["comparison"].append({
                        "id": p["id"] + "-" + t["id"], "kind": "fact", "product_id": p["id"], "topic_id": t["id"],
                        "text": "[MOCK] Source excerpt: " + ev["excerpt"][:350] if ev else "[MOCK] No evidence found.",
                        "citations": [{"evidence_id": ev["evidence_id"], "quote": ev["excerpt"][:350]}] if ev else [],
                        "depends_on": [], "conditions": {}, "effective_date": None,
                    })
    elif kind == "reviewer":
        result = {"reviews": []}
        for i in context["items"]:
            refs = i.get("citations", [])
            result["reviews"].append({"item_id": i["id"], "status": "unknown",
                "reason": "[MOCK] Quotes can be located, but simulated review does not establish semantic support.",
                "evidence_ids": [r["evidence_id"] for r in refs], "quotes": refs})
    else:
        result = context.get("text", "ready")
    return json.dumps(result, ensure_ascii=False) if json_mode else (result if isinstance(result, str) else json.dumps(result))
