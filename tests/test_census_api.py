import pytest

from api import config

CENSUS = "/api/datasets/census"


# --- Levels & geographies -------------------------------------------------


async def test_levels_report_latest_year_area_counts(client):
    resp = await client.get(f"{CENSUS}/levels")
    assert resp.status_code == 200

    counts = {r["level"]: r["area_count"] for r in resp.json()}
    # LGA: Boroondara, Stonnington, Campbelltown NSW, Campbelltown SA.
    # STE: NSW, Victoria, South Australia.
    assert counts == {"LGA": 4, "STE": 3}


async def test_geographies_use_canonical_names(client):
    resp = await client.get(f"{CENSUS}/geographies", params={"level": "LGA"})
    assert resp.status_code == 200

    names = [g["geo_name"] for g in resp.json()]
    # Suffix stripped where unique; state appended where two areas collide.
    assert names == [
        "Boroondara",
        "Campbelltown (New South Wales)",
        "Campbelltown (South Australia)",
        "Stonnington",
    ]


async def test_geographies_default_to_the_configured_level(client):
    resp = await client.get(f"{CENSUS}/geographies")
    assert resp.status_code == 200
    # DEFAULT_LEVEL is LGA, so no `level` param yields the LGA universe.
    assert {g["geo_code"] for g in resp.json()} == {
        "LGA21110",
        "LGA22910",
        "LGA11500",
        "LGA40910",
    }


async def test_geographies_at_state_level(client):
    resp = await client.get(f"{CENSUS}/geographies", params={"level": "STE"})
    assert resp.status_code == 200
    assert [g["geo_name"] for g in resp.json()] == [
        "New South Wales",
        "South Australia",
        "Victoria",
    ]


async def test_unknown_level_is_a_400(client):
    resp = await client.get(f"{CENSUS}/geographies", params={"level": "SA2"})
    assert resp.status_code == 400
    assert resp.json()["kind"] == "bad_request"


# --- Vocabulary -----------------------------------------------------------


async def test_categories_lists_subcategory_counts(client):
    resp = await client.get(f"{CENSUS}/categories")
    assert resp.status_code == 200

    by_name = {c["category"]: c["subcategory_count"] for c in resp.json()}
    assert by_name == {"dwelling_structure": 2, "population": 1}


async def test_subcategories_index_pairs_every_name_with_its_category(client):
    resp = await client.get(f"{CENSUS}/subcategories")
    assert resp.status_code == 200

    pairs = {(r["category"], r["subcategory"]) for r in resp.json()}
    assert pairs == {
        ("population", "total"),
        ("dwelling_structure", "separate house"),
        ("dwelling_structure", "flat or apartment"),
    }


async def test_subcategories_index_carries_no_values(client):
    """Names only — this is what keeps a single up-front request defensible."""
    rows = (await client.get(f"{CENSUS}/subcategories")).json()
    assert all(set(r) == {"category", "subcategory"} for r in rows)


# --- Series ---------------------------------------------------------------


async def test_series_returns_sorted_years_and_all_points(client):
    resp = await client.get(
        f"{CENSUS}/series",
        params={"category": "dwelling_structure", "level": "LGA", "geo": "LGA21110"},
    )
    assert resp.status_code == 200

    body = resp.json()
    assert body["level"] == "LGA"
    assert body["years"] == [2011, 2016, 2021]
    assert len(body["points"]) == 6  # 2 subcategories x 3 years
    assert {p["subcategory"] for p in body["points"]} == {
        "separate house",
        "flat or apartment",
    }


async def test_series_compares_multiple_areas(client):
    resp = await client.get(
        f"{CENSUS}/series",
        params=[("category", "population"), ("level", "STE"), ("geo", "1"), ("geo", "2")],
    )
    assert resp.status_code == 200

    body = resp.json()
    assert [g["geo_name"] for g in body["geographies"]] == ["New South Wales", "Victoria"]
    # 2 areas x 1 subcategory x 3 years, and every point is tagged by area.
    assert len(body["points"]) == 6
    assert {p["geo_code"] for p in body["points"]} == {"1", "2"}
    vic_2021 = next(
        p for p in body["points"] if p["geo_code"] == "2" and p["year"] == 2021
    )
    assert vic_2021["value"] == 6503491


async def test_series_joins_across_years_on_geo_code_despite_name_drift(client):
    """Boroondara is 'Boroondara (C)' in 2011/2016 but 'Boroondara' in 2021 under
    the same geo_code. All three years must come back as one area with one name."""
    resp = await client.get(
        f"{CENSUS}/series",
        params={"category": "population", "level": "LGA", "geo": "LGA21110"},
    )
    body = resp.json()
    assert {p["year"] for p in body["points"]} == {2011, 2016, 2021}
    # Canonical name, not the year's raw name — no '(C)' leaks through.
    assert {p["geo_name"] for p in body["points"]} == {"Boroondara"}


async def test_series_is_empty_not_404_when_area_lacks_the_category(client):
    """Campbelltown NSW has population but no dwelling_structure rows. That is a
    real empty result, not a missing endpoint."""
    resp = await client.get(
        f"{CENSUS}/series",
        params={"category": "dwelling_structure", "level": "LGA", "geo": "LGA11500"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["points"] == []
    assert body["years"] == []
    # The legend is still echoed so the client can render "no data" for the area.
    assert body["geographies"] == [
        {"geo_code": "LGA11500", "geo_name": "Campbelltown (New South Wales)"}
    ]


async def test_unknown_category_is_404_not_an_empty_chart(client):
    resp = await client.get(
        f"{CENSUS}/series",
        params={"category": "nope", "level": "LGA", "geo": "LGA21110"},
    )
    assert resp.status_code == 404
    assert resp.json()["kind"] == "bad_request"


async def test_series_requires_at_least_one_area(client):
    resp = await client.get(
        f"{CENSUS}/series", params={"category": "population", "level": "LGA"}
    )
    assert resp.status_code == 422


async def test_series_caps_the_number_of_areas(client):
    params = [("category", "population"), ("level", "LGA")]
    params += [("geo", f"LGA{i:05d}") for i in range(config.MAX_GEO_CODES + 1)]
    resp = await client.get(f"{CENSUS}/series", params=params)
    assert resp.status_code == 422


async def test_missing_category_param_is_rejected(client):
    resp = await client.get(f"{CENSUS}/series")
    assert resp.status_code == 422


@pytest.mark.parametrize("category", ["dwelling_structure", "population"])
async def test_series_values_match_the_database(client, category):
    body = (
        await client.get(
            f"{CENSUS}/series",
            params={"category": category, "level": "LGA", "geo": "LGA21110"},
        )
    ).json()
    for point in body["points"]:
        assert isinstance(point["value"], int)
        assert point["year"] in (2011, 2016, 2021)


# --- Cross-cutting --------------------------------------------------------


async def test_census_endpoints_are_rate_limited(client, monkeypatch):
    monkeypatch.setattr(config, "CENSUS_PER_MINUTE", 3)

    for _ in range(3):
        assert (await client.get(f"{CENSUS}/categories")).status_code == 200

    resp = await client.get(f"{CENSUS}/categories")
    assert resp.status_code == 429
    assert resp.json()["kind"] == "rate"
    assert int(resp.headers["Retry-After"]) >= 1


async def test_health_reports_database_and_key_state(client):
    body = (await client.get("/api/health")).json()
    assert body["database"] is True
    assert "inflight" in body["limits"]


async def test_missing_database_is_503_not_a_traceback(client, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gone.db")

    resp = await client.get(f"{CENSUS}/categories")
    assert resp.status_code == 503
    assert resp.json()["kind"] == "unavailable"


async def test_error_response_reaches_the_openapi_schema(client):
    """The frontend's error type is generated, not hand-written.

    If ErrorResponse drops out of the schema, `make types` silently stops
    emitting it and web/ has to define its own copy — which is exactly the
    drift the generated types exist to prevent.
    """
    schema = (await client.get("/openapi.json")).json()
    assert "ErrorResponse" in schema["components"]["schemas"]

    ref = "#/components/schemas/ErrorResponse"
    for path in ("/api/chat", f"{CENSUS}/categories"):
        content = schema["paths"][path].popitem()[1]["responses"]["429"]["content"]
        assert content["application/json"]["schema"]["$ref"] == ref


# --- SPA serving ----------------------------------------------------------


async def test_unknown_api_path_is_a_json_404_not_the_html_shell(client):
    """The catch-all must not swallow API typos.

    Falling through to index.html would return 200 with a web page, leaving the
    client parsing HTML as JSON — a missing route would look like a data bug.
    """
    resp = await client.get(f"{CENSUS}/nope")
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
