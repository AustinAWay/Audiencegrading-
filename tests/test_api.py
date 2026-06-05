"""HTTP surface via FastAPI's TestClient (mock mode, no network)."""
from fastapi.testclient import TestClient

from nichefit.app import app

client = TestClient(app)


def test_config_endpoint():
    r = client.get("/api/config")
    assert r.status_code == 200
    body = r.json()
    assert body["mock"] == {"apify": True, "anthropic": True}
    assert len(body["rubric"]) == 5
    assert body["model"]


def test_estimate_resolves_handle_and_itemizes_cost():
    r = client.post("/api/estimate", json={
        "handle": "https://x.com/naval", "niche": "tech / SaaS",
        "sample_size": 200, "force_refresh": True,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["handle"] == "naval"
    # mock mode -> both layers free
    assert body["apify_cost"] == 0.0 or body["apify_mock"] is True


def test_estimate_rejects_unparseable_handle():
    r = client.post("/api/estimate", json={"handle": "   ", "niche": "x"})
    assert r.status_code == 400


def test_index_is_served():
    r = client.get("/")
    assert r.status_code == 200
    assert "NicheFit" in r.text


def test_unknown_job_is_404():
    assert client.get("/api/progress/does-not-exist").status_code == 404


def test_person_endpoint_grades_one_person():
    r = client.post("/api/person", json={"handle": "@sama", "niche": "AI / machine learning"})
    assert r.status_code == 200
    body = r.json()
    assert body["handle"] == "sama"
    assert 0 <= body["total"] <= 100
    assert body["tier"] in ("A", "B", "C", "D")


def test_person_endpoint_rejects_empty_handle():
    assert client.post("/api/person", json={"handle": "  ", "niche": "x"}).status_code == 400
