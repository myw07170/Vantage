"""Unified product comparison: collect, analyze, review, at most two targeted reworks."""
from __future__ import annotations
import asyncio
import copy
import datetime as dt
import json
from urllib.parse import urlparse
from pydantic import ValidationError
from app.core import budget, db, trace
from app.core.config import get_settings
from app.core.fetcher import fetch_page
from app.core.llm import chat_json
from app.core.models import Evidence, ReportContent, ReportItem, ResearchScope, all_items, now
from app.core.review import apply_reviews, contains_quote, dependent_ids, invalidate, summarize
from app.core.roles import PROMPTS
from app.core.search import SearchUnavailable, search
from app.core.versions import require_version

def call_role(role: str, context: dict, max_tokens: int = 4500) -> dict:
    result = chat_json(
        [{"role": "system", "content": PROMPTS[role]},
         {"role": "user", "content": json.dumps(context, ensure_ascii=False)}],
        model=get_settings().llm_model_core, max_tokens=max_tokens, temperature=0.15,
        purpose=role + " evidence-based handoff", task_kind=role, mock_context=context,
    )
    if not isinstance(result, dict):
        raise ValueError(role.title() + " returned no usable structured output.")
    return result

async def worker(func, *args, **kwargs):
    current = budget.CURRENT.get()
    remaining = current.check() if current else 1200
    # Threads only compute/fetch. Persistence happens on the event loop after this check.
    result = await asyncio.wait_for(asyncio.to_thread(func, *args, **kwargs), timeout=remaining)
    budget.check()
    return result

def official_source(url: str, product: dict) -> bool:
    host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    confirmed_host = (urlparse(product["website"]).hostname or "").lower().removeprefix("www.")
    if any(part in host.split(".") for part in ("forum", "community", "discuss")) or "/community/" in urlparse(url).path:
        return False  # A vendor-hosted community post is not a vendor commitment.
    return host == confirmed_host or host.endswith("." + confirmed_host)

def collect_source(result: dict, product: dict, topic: dict, *, refresh: bool = False) -> dict | None:
    page = fetch_page(result["url"], fallback_snippet=result.get("snippet", ""),
                      prefetched_text=result.get("content", ""), refresh=refresh)
    if page.get("blocked") or not page.get("text", "").strip():
        return None
    context = page["text"]
    url = page.get("url", result["url"])
    official = official_source(url, product)
    # External matches must identify the product, rather than sharing a generic category.
    if not official and product["name"].casefold() not in (result.get("title", "") + " " + context).casefold():
        return None
    return Evidence(
        evidence_id=db.uid("ev"), product_id=product["id"], topic_id=topic["id"],
        source_url=url, source_type="official" if official else "external",
        attribution=("Vendor website relationship explicitly confirmed in the research scope."
                     if official else "External publication; not a vendor commitment."),
        title=result.get("title", ""), excerpt=context[:1800], context=context,
        captured_at=page.get("captured_at", now()), published_at=page.get("published_at") or result.get("published_at"),
        published_date_basis=(page.get("published_date_basis", "") if page.get("published_at") else
                              "search provider publication metadata" if result.get("published_at") else ""),
        degraded=bool(page.get("degraded", False)),
        limitation="Only a search excerpt was available; the full page could not be fetched." if page.get("degraded") else "",
    ).model_dump()

def normalize_items(raw: dict, content: dict, *, affected: set[str] | None = None) -> dict:
    products = {p["id"] for p in content["products"]}
    topics = {t["id"] for t in content["topics"]}
    existing = {i["id"] for i in all_items(content)}
    original_items = {i["id"]: i for i in all_items(content)}
    seen = set()
    rejected = []
    output = {k: [] for k in ("comparison", "brief", "changes")}
    for section in output:
        source = raw.get(section, [])
        if not isinstance(source, list):
            rejected.append("Analyst returned a malformed " + section + " array.")
            continue
        for value in source:
            try:
                item = ReportItem.model_validate(value).model_dump()
                if item["id"] in seen:
                    raise ValueError("Duplicate item ID.")
                if item["product_id"] and item["product_id"] not in products:
                    raise ValueError("Unconfirmed product.")
                if item["topic_id"] and item["topic_id"] not in topics:
                    raise ValueError("Unconfirmed topic.")
                if section == "comparison" and (not item["product_id"] or not item["topic_id"]):
                    raise ValueError("Comparison facts require product and topic IDs.")
                if section == "brief" and item["kind"] != "inference":
                    raise ValueError("Brief items must distinguish judgments as inferences.")
                if section == "changes" and item["kind"] != "change":
                    raise ValueError("Changes require kind=change.")
                if affected is not None:
                    if item["id"] in existing and item["id"] not in affected:
                        raise ValueError("Targeted work attempted to change an unaffected item.")
                    allowed = [i for i in all_items(content) if i["id"] in affected]
                    if item["id"] in original_items and any(item[k] != original_items[item["id"]][k] for k in ("kind", "product_id", "topic_id")):
                        raise ValueError("Targeted work attempted to change an item's identity.")
                    anchored_pairs = {(i["product_id"], i["topic_id"]) for i in allowed if i["product_id"] and i["topic_id"]}
                    if item["id"] not in existing and anchored_pairs:
                        if item["kind"] == "inference":
                            if not item["depends_on"] or not set(item["depends_on"]) <= affected:
                                raise ValueError("New judgment expands beyond affected facts.")
                        elif (item["product_id"], item["topic_id"]) not in anchored_pairs:
                            raise ValueError("New fact expands beyond affected product/topic pairs.")
                    if item["id"] not in existing and not any(
                        (not i["product_id"] or i["product_id"] == item["product_id"])
                        and (not i["topic_id"] or i["topic_id"] == item["topic_id"]) for i in allowed):
                        raise ValueError("Targeted work attempted to expand the scope.")
                seen.add(item["id"])
                output[section].append(item)
            except (ValidationError, ValueError, TypeError) as exc:
                rejected.append("Analyst item rejected: " + str(exc)[:350])
    if not any(output.values()):
        raise ValueError("Analyst output contained no valid report items. " + " ".join(rejected[:2]))
    if affected is None:
        content.update(output)
        for p in content["products"]:
            for t in content["topics"]:
                if not any(i["product_id"] == p["id"] and i["topic_id"] == t["id"] for i in content["comparison"]):
                    item_id = db.uid("missing")
                    content["comparison"].append(ReportItem(
                        id=item_id, product_id=p["id"], topic_id=t["id"],
                        text="No sufficiently supported information was found for this product and topic.",
                    ).model_dump())
    else:
        replaced = {i["id"] for values in output.values() for i in values}
        for section, values in output.items():
            content[section] = [i for i in content[section] if i["id"] not in replaced] + values
        invalidate(content, affected | replaced)
    content["limitations"].extend(rejected)
    return content

def evidence_context(evidence: list[dict]) -> list[dict]:
    # Stored source context remains complete; send relevant quoted material with bounded surrounding context.
    return [{**e, "excerpt": e["excerpt"][:350], "context": e["context"][:4000]} for e in evidence]

async def run_pipeline(task_id: str):
    task = db.get_task(task_id)
    settings = get_settings()
    limit = budget.Budget(settings.research_token_limit, settings.research_time_limit_seconds)
    token = budget.CURRENT.set(limit)
    payload = task["payload"]
    scope = ResearchScope.model_validate(payload["scope"]).model_dump()
    started = now()
    base = None
    if task["kind"] != "research":
        base = require_version(task["report_id"], payload["base_version_id"])
        content = copy.deepcopy(base["content"])
        content["limitations"] = list(content.get("limitations", []))
        # This is a new independently-budgeted task even when it starts from an old snapshot.
        content["is_mock"] = content.get("is_mock", False) or settings.is_mock
        content["llm_provider"] = settings.llm_provider
        content["checked_at"] = started
        content["changes_since"] = (dt.datetime.fromisoformat(started) - dt.timedelta(days=90)).date().isoformat()
    else:
        content = ReportContent(
            products=scope["products"], topics=scope["topics"], checked_at=started,
            changes_since=(dt.datetime.fromisoformat(started) - dt.timedelta(days=90)).date().isoformat(),
            is_mock=settings.is_mock, llm_provider=settings.llm_provider,
        ).model_dump()
    affected = None
    if base:
        targets = set(payload.get("target_ids", [])) or {i["id"] for i in all_items(content)}
        affected = dependent_ids(content, targets)
        invalidate(content, affected)
    fetched: set[tuple[str, str]] = set()
    rework_rounds = 0
    error = ""
    produced = False

    def save(stage: str):
        spans = trace.get_trace(task_id)
        db.save_traces(task_id, task.get("report_id") or "", spans)
        db.checkpoint(task_id, {"stage": stage, "content": content, "usage": limit.snapshot(),
                                "visualization": db.get_task(task_id)['checkpoint'].get('visualization', {'roles': {}, 'activity': [], 'percent': 0, 'rework_rounds': 0}),
                                "rework_rounds": rework_rounds, "started_at": started})

    def event(kind: str, data: dict) -> dict:
        return {"type": kind, "data": data}

    def relevant_pairs(target_ids: set[str] | None):
        items = [i for i in all_items(content) if target_ids and i["id"] in target_ids]
        anchored = {(i["product_id"], i["topic_id"]) for i in items if i["product_id"] and i["topic_id"]}
        if target_ids and not anchored:
            dependencies = {d for i in items for d in i["depends_on"]}
            anchored = {(i["product_id"], i["topic_id"]) for i in all_items(content)
                        if i["id"] in dependencies and i["product_id"] and i["topic_id"]}
        if target_ids and not anchored:
            refs = {r["evidence_id"] for i in items for r in i["citations"]}
            anchored = {(e["product_id"], e["topic_id"]) for e in content["evidence"]
                        if e["evidence_id"] in refs and e["product_id"] and e["topic_id"]}
        pairs = []
        for p in scope["products"]:
            for t in scope["topics"]:
                matching = any((not i["product_id"] or i["product_id"] == p["id"])
                               and (not i["topic_id"] or i["topic_id"] == t["id"]) for i in items)
                if target_ids is None or ((p["id"], t["id"]) in anchored if anchored else matching):
                    pairs.append((p, t))
        return pairs

    async def collect(target_ids: set[str] | None, question: str):
        pairs = relevant_pairs(target_ids)
        fetched.clear()
        for index, (product, topic) in enumerate(pairs):
            budget.check()
            trace.set_context(task_id, "collector", "collect", "Collect targeted public evidence")
            yield event("role", {"role": "collector", "status": "working", "detail": product["name"] + " · " + topic["name"]})
            context = {"product": product, "topic": topic, "question": question,
                       "research_question": task["query"],
                       "changes_since": content["changes_since"], "checked_at": content["checked_at"],
                       "scope_notes": scope["limitations"]}
            plan = await worker(call_role, "collector", context, 700)
            host = urlparse(product["website"]).hostname
            proposed = plan.get("queries", [])
            if not isinstance(proposed, list):
                proposed = []
            queries = [f'site:{host} {product["name"]} {topic["name"]}']
            queries += [f'{product["name"]} {product["category"]} {q}'[:350] for q in proposed[:2] if isinstance(q, str)]
            if target_ids is None:
                queries.append(f'{product["name"]} {product["category"]} release notes since {content["changes_since"]}')
            results = [{"url": product["website"], "title": product["name"] + " vendor website"}]
            for query in dict.fromkeys(queries):
                yield event('activity', {'role': 'collector', 'text': 'Searching: ' + query})
                try:
                    results += await worker(search, query, num=3, task_id=task_id)
                except SearchUnavailable as exc:
                    message = "Search unavailable: " + str(exc)[:300]
                    if message not in content["limitations"]:
                        content["limitations"].append(message)
                    yield event("notice", {"message": message})
            external = []
            for result in results:
                key = (product["id"], result.get("url", ""))
                if not key[1] or key in fetched:
                    continue
                fetched.add(key)
                ev = await worker(collect_source, result, product, topic, refresh=bool(base or target_ids))
                if ev and ev["source_type"] != "official":
                    external.append(ev)
                    continue
                if ev:
                    content["evidence"].append(ev)
                    db.save_evidence(task_id, ev, task.get("report_id"))
                    save("collect")
                    yield event("evidence", ev)
            if external:
                identity = await worker(call_role, "collector", {**context, "action": "source_identity",
                                                                  "evidence": evidence_context(external)}, 2000)
                accepted = {r.get("evidence_id"): r for r in identity.get("sources", []) if isinstance(r, dict)}
                for ev in external:
                    decision = accepted.get(ev["evidence_id"], {})
                    if decision.get("identity_matches") is True and decision.get("reason") and contains_quote(ev, decision.get("quote", "")):
                        ev["attribution"] += " Identity check: " + decision["reason"]
                        content["evidence"].append(ev)
                        db.save_evidence(task_id, ev, task.get("report_id"))
                        save("collect")
                        yield event("evidence", ev)
                    else:
                        content["limitations"].append("Excluded external page with unconfirmed product identity: " + ev["source_url"])
            yield event("progress", {"stage": "collect", "percent": round(35 * (index + 1) / max(1, len(pairs))),
                                     "usage": limit.snapshot(), "evidence_count": len(content["evidence"])})
        yield event("role", {"role": "collector", "status": "done", "detail": "Evidence and source limitations handed to Analyst."})

    async def analyze(target_ids: set[str] | None, question: str):
        nonlocal produced
        trace.set_context(task_id, "analyst", "analyze", "Compare and write from collected evidence")
        targets = [i for i in all_items(content) if target_ids and i["id"] in target_ids]
        relevant_products = {i["product_id"] for i in targets if i["product_id"]}
        relevant = [e for e in content["evidence"] if not relevant_products or e["product_id"] in relevant_products]
        relevant = list({(e["product_id"], e["source_url"]): e for e in relevant}.values())
        ctx = {"scope": scope, "research_question": task["query"], "checked_at": content["checked_at"], "changes_since": content["changes_since"],
               "evidence": evidence_context(relevant), "question": question, "targets": targets,
               "sections": {i["id"]: k for k in ("comparison", "brief", "changes") for i in content[k]},
               "issues": [dict(item_id=i["id"], **i["review"]) for i in targets]}
        raw = await worker(call_role, "analyst", ctx, 9000)
        if not any(raw.get(k) for k in ("comparison", "brief", "changes")):
            raise ValueError("Analyst returned no usable report items.")
        normalize_items(raw, content, affected=target_ids)
        produced = True
        save("analyze")

    async def review(target_ids: set[str] | None):
        nonlocal produced
        trace.set_context(task_id, "reviewer", "review", "Check citations and evidence support")
        items = [i for i in all_items(content) if target_ids is None or i["id"] in target_ids]
        # Batching limits prompt size; a missing batch retains Pending review rather than silently passing.
        for offset in range(0, len(items), 8):
            batch = items[offset:offset + 8]
            refs = {r["evidence_id"] for i in batch for r in i["citations"]}
            relevant = [e for e in content["evidence"] if e["evidence_id"] in refs]
            pairs = {(i["product_id"], i["topic_id"]) for i in batch if i["product_id"]}
            alternatives = [e for e in content["evidence"] if e["evidence_id"] not in refs
                            and (e["product_id"], e["topic_id"]) in pairs]
            alternatives = list({(e["product_id"], e["source_url"]): e for e in alternatives}.values())
            relevant_context = evidence_context(relevant) + [{**e, "excerpt": e["excerpt"][:200], "context": e["context"][:1200]} for e in alternatives]
            dependencies = [i for i in all_items(content) if i["id"] in {d for item in batch for d in item["depends_on"]}]
            response = await worker(call_role, "reviewer",
                                    {"items": batch, "dependencies": dependencies, "evidence": relevant_context,
                                     "products": scope["products"], "checked_at": content["checked_at"],
                                     "changes_since": content["changes_since"]}, 4500)
            apply_reviews(content, batch, response)
            produced = True
            save("review")
        return {i["id"] for i in items if i["review"]["status"] != "supported"}

    try:
        save("starting")
        if task["kind"] != "review":
            async for ev in collect(affected, payload.get("question", "")):
                yield ev
            if not content["evidence"]:
                raise ValueError("No usable public evidence was collected. No report was fabricated.")
            yield event("role", {"role": "analyst", "status": "working", "detail": "Building atomic comparisons and a short brief."})
            await analyze(affected, payload.get("question", ""))
            yield event('activity', {'role': 'analyst', 'text': 'Draft handed over: ' + str(len(all_items(content))) + ' facts and judgments, with evidence references.'})
            yield event("role", {"role": "analyst", "status": "done", "detail": "Draft handed to Reviewer."})
        yield event("role", {"role": "reviewer", "status": "working", "detail": "Checking every fact and key conclusion."})
        problems = await review(affected)
        yield event('activity', {'role': 'reviewer', 'text': 'Review found ' + str(len(problems)) + ' unresolved items. Each issue identifies affected content.'})
        while problems and rework_rounds < 2:
            # Empty/no-source rows are honest gaps; only actionable, evidenced problems trigger rework.
            repairable = {i["id"] for i in all_items(content) if i["id"] in problems and i["citations"]}
            if not repairable:
                break
            budget.check()
            rework_rounds += 1
            affected_rework = dependent_ids(content, repairable)
            yield event("handoff", {"from": "reviewer", "to": "collector", "round": rework_rounds,
                                    "item_ids": sorted(affected_rework)})
            issue_text = json.dumps([{"id": i["id"], "text": i["text"], "issue": i["review"]["reason"]}
                                    for i in all_items(content) if i["id"] in affected_rework])
            async for ev in collect(affected_rework, issue_text):
                yield ev
            yield event("role", {"role": "analyst", "status": "working", "detail": f"Addressing review issues, rework {rework_rounds}/2."})
            await analyze(affected_rework, issue_text)
            yield event('role', {'role': 'analyst', 'status': 'done', 'detail': 'Revised items and dependent conclusions handed to Reviewer.'})
            yield event("role", {"role": "reviewer", "status": "working", "detail": "Rechecking changes and dependent conclusions."})
            problems = await review(affected_rework)
        yield event("role", {"role": "reviewer", "status": "done", "detail": "Review finished; unresolved items remain visible."})
    except (budget.BudgetExceeded, asyncio.TimeoutError) as exc:
        error = str(exc) or "Task time limit reached."
        content["limitations"].append(error)
        yield event("notice", {"message": error})
    except asyncio.CancelledError:
        limit.cancelled.set()
        save("interrupted")
        raise
    except Exception as exc:
        error = str(exc)
        content["limitations"].append(error)
        save("failed")
        # Provider/auth failures must not silently turn into a mock report.
        if not produced:
            yield event("error", {"message": error})
            return
        yield event("notice", {"message": error})
    finally:
        limit.cancelled.set()
        trace.clear_context()
        budget.CURRENT.reset(token)

    if not produced or not content["evidence"] or not all_items(content):
        save("failed")
        yield event("error", {"message": error or "No usable result was produced; collected material is retained."})
        return
    summarize(content, rework_rounds=rework_rounds, usage=limit.snapshot(), run_limitation=error,
              changes_message="" if content["changes"] else "No relevant public changes found")
    save("saving")
    metadata = {"question": payload.get("question", ""), "selected_text": payload.get("selected_text", ""),
                "target_ids": payload.get("target_ids", []), "usage": limit.snapshot(),
                "base_version_id": payload.get("base_version_id"), "rework_rounds": rework_rounds}
    version = db.create_version(task.get("report_id"), content, task["kind"], task_id=task_id,
                                base_version_id=payload.get("base_version_id"), candidate=bool(base),
                                metadata=metadata, title=" vs ".join(p["name"] for p in scope["products"]))
    yield event("progress", {"stage": "done", "percent": 100, "usage": limit.snapshot(),
                             "evidence_count": len(content["evidence"])})
    yield event("done", {"report_id": version["report_id"], "version_id": version["version_id"],
                         "candidate": bool(base)})
