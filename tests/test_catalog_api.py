"""Active catalog contracts and preservation of historical identities."""
import httpx
import pytest

from app.core import db


@pytest.fixture
async def api(offline):
    from app import main
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test") as client:
        yield client
    await main.runner.close()


async def test_active_catalog_modules_and_archived_details(api):
    active = (await api.get("/api/experts")).json()
    catalog = (await api.get("/api/experts?include_archived=true")).json()
    modules = (await api.get("/api/industry-modules")).json()
    assert len(active) == 12 and len(catalog) == 52 and len(modules) == 28
    assert all(e["catalog_status"] == "active" for e in active)
    archived = (await api.get("/api/experts/L1-008")).json()
    assert archived["catalog_status"] == "archived" and archived["name"] == "Hannah Weiss"
    assert (await api.get("/api/experts/missing")).status_code == 404


async def test_archived_workload_is_retained_without_counting_modules(api):
    db.bump_expert_stats(["L1-008"], {"L1-008": 2}, {"L1-008": 3})
    active = (await api.get("/api/experts/workload")).json()
    history = (await api.get("/api/experts/workload?include_archived=true")).json()
    assert len(active) == 12 and "L1-008" not in {e["id"] for e in active}
    old = next(e for e in history if e["id"] == "L1-008")
    assert (old["missions"], old["claims_authored"], old["evidence_collected"]) == (1, 2, 3)
    assert (await api.get("/api/experts/L1-008")).json()["stats"]["missions"] == 1
    catalog = (await api.get("/api/experts?include_archived=true")).json()
    assert next(e for e in catalog if e["id"] == "L1-008")["stats"]["claims_authored"] == 2
