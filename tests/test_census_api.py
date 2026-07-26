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


async def test_subcategories_index_pairs_every_name_with_its_category(client):
    resp = await client.get("/api/datasets/census/subcategories")
    assert resp.status_code == 200

    pairs = {(r["category"], r["subcategory"]) for r in resp.json()}
    assert pairs == {
        ("population", "total"),
        ("dwelling_structure", "separate house"),
        ("dwelling_structure", "flat or apartment"),
    }


async def test_subcategories_index_carries_no_values(client):
    """Names only — this is what keeps a single up-front request defensible."""
    rows = (await client.get("/api/datasets/census/subcategories")).json()
    assert all(set(r) == {"category", "subcategory"} for r in rows)


# --- SPA serving ----------------------------------------------------------


async def test_unknown_api_path_is_a_json_404_not_the_html_shell(client):
    """The catch-all must not swallow API typos.

    Falling through to index.html would return 200 with a web page, leaving the
    client parsing HTML as JSON — a missing route would look like a data bug.
    """
    resp = await client.get("/api/datasets/census/nope")
    assert resp.status_code == 404
    assert resp.json()["kind"] == "bad_request"


async def test_unbuilt_frontend_explains_itself(client, monkeypatch, tmp_path):
    # Explicitly point at a missing bundle — otherwise this passes or fails
    # depending on whether the developer happens to have run a build.
    monkeypatch.setattr(config, "WEB_DIST", tmp_path / "never-built")

    resp = await client.get("/")
    assert resp.status_code == 503
    assert "npm --prefix web run build" in resp.json()["detail"]


async def test_spa_serves_index_for_client_routes(client, monkeypatch, tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><title>app</title>")
    monkeypatch.setattr(config, "WEB_DIST", dist)

    for path in ("/", "/some/client/route"):
        resp = await client.get(path)
        assert resp.status_code == 200, path
        assert "<title>app</title>" in resp.text


async def test_spa_serves_real_files_from_dist(client, monkeypatch, tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("shell")
    (dist / "favicon.svg").write_text("<svg/>")
    monkeypatch.setattr(config, "WEB_DIST", dist)

    resp = await client.get("/favicon.svg")
    assert resp.status_code == 200
    assert resp.text == "<svg/>"


async def test_spa_refuses_to_escape_the_bundle(client, monkeypatch, tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("shell")
    secret = tmp_path / "secret.txt"
    secret.write_text("do not serve me")
    monkeypatch.setattr(config, "WEB_DIST", dist)

    # full_path is attacker-controlled; traversal must fall back to the shell
    # rather than reading a file outside dist.
    resp = await client.get("/../secret.txt")
    assert resp.status_code == 200
    assert "do not serve me" not in resp.text
