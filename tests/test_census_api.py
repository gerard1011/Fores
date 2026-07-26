import pytest

from api import config


async def test_categories_lists_subcategory_counts(client):
    resp = await client.get("/api/datasets/census/categories")
    assert resp.status_code == 200

    by_name = {c["category"]: c["subcategory_count"] for c in resp.json()}
    assert by_name == {"dwelling_structure": 2, "population": 1}


async def test_series_returns_sorted_years_and_all_points(client):
    resp = await client.get(
        "/api/datasets/census/series", params={"category": "dwelling_structure"}
    )
    assert resp.status_code == 200

    body = resp.json()
    assert body["years"] == [2011, 2016, 2021]
    assert len(body["points"]) == 6
    assert {p["subcategory"] for p in body["points"]} == {
        "separate house",
        "flat or apartment",
    }


async def test_unknown_category_is_404_not_an_empty_chart(client):
    resp = await client.get("/api/datasets/census/series", params={"category": "nope"})
    assert resp.status_code == 404
    assert resp.json()["kind"] == "bad_request"


async def test_missing_category_param_is_rejected(client):
    resp = await client.get("/api/datasets/census/series")
    assert resp.status_code == 422


async def test_census_endpoints_are_rate_limited(client, monkeypatch):
    monkeypatch.setattr(config, "CENSUS_PER_MINUTE", 3)

    for _ in range(3):
        assert (await client.get("/api/datasets/census/categories")).status_code == 200

    resp = await client.get("/api/datasets/census/categories")
    assert resp.status_code == 429
    assert resp.json()["kind"] == "rate"
    assert int(resp.headers["Retry-After"]) >= 1


async def test_health_reports_database_and_key_state(client):
    body = (await client.get("/api/health")).json()
    assert body["database"] is True
    assert "inflight" in body["limits"]


async def test_missing_database_is_503_not_a_traceback(client, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gone.db")

    resp = await client.get("/api/datasets/census/categories")
    assert resp.status_code == 503
    assert resp.json()["kind"] == "unavailable"


@pytest.mark.parametrize("category", ["dwelling_structure", "population"])
async def test_series_values_match_the_database(client, category):
    body = (
        await client.get("/api/datasets/census/series", params={"category": category})
    ).json()
    for point in body["points"]:
        assert isinstance(point["value"], int)
        assert point["year"] in (2011, 2016, 2021)


async def test_error_response_reaches_the_openapi_schema(client):
    """The frontend's error type is generated, not hand-written.

    If ErrorResponse drops out of the schema, `make types` silently stops
    emitting it and web/ has to define its own copy — which is exactly the
    drift the generated types exist to prevent.
    """
    schema = (await client.get("/openapi.json")).json()
    assert "ErrorResponse" in schema["components"]["schemas"]

    ref = "#/components/schemas/ErrorResponse"
    for path in ("/api/chat", "/api/datasets/census/categories"):
        content = schema["paths"][path].popitem()[1]["responses"]["429"]["content"]
        assert content["application/json"]["schema"]["$ref"] == ref
