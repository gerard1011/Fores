"""FastAPI application.

Serves the census data and the agent. In this commit it runs alongside the
Streamlit app; from commit 3 it also serves the built React bundle.
"""

import json
import logging
import os
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from . import config, db, schemas
from .agent import stream_ask
from .limits import RateLimited, client_ip, limiter

log = logging.getLogger("api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Fail loudly and early on the two things that silently break at runtime.

    Neither aborts startup — a missing key still lets you browse the data, and
    a missing database still lets you see a real error page instead of a
    connection refused. Both endpoints return 503 rather than a traceback.
    """
    if not (os.environ.get("ANTHROPIC_API_KEY") or "").strip():
        log.warning(
            "ANTHROPIC_API_KEY is not set. The census endpoints will work; "
            "/api/chat will return 503. Add it to .env in the repo root."
        )
    if not config.DB_PATH.exists():
        log.warning(
            "No census database at %s. It is gitignored and bind-mounted from "
            "./data, so the build does not create it. Place "
            "boroondara_census.db there or set CENSUS_DB_PATH.",
            config.DB_PATH,
        )
    else:
        log.info("Census database: %s", config.DB_PATH)
    yield


app = FastAPI(title="Fores Census API", version="0.1.0", lifespan=lifespan)

if config.CORS_ORIGINS:
    # Dev only — Vite serves the UI on another port. In production the bundle is
    # served from this same origin and this stays off.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.CORS_ORIGINS,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )


@app.exception_handler(RateLimited)
async def rate_limited_handler(request: Request, exc: RateLimited) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content=schemas.ErrorResponse(
            detail=exc.message, kind=exc.kind, retry_after=exc.retry_after
        ).model_dump(),
        headers={"Retry-After": str(exc.retry_after)},
    )


@app.exception_handler(db.DatabaseMissing)
async def db_missing_handler(request: Request, exc: db.DatabaseMissing) -> JSONResponse:
    log.error("Database unavailable: %s", exc)
    return JSONResponse(
        status_code=503,
        content=schemas.ErrorResponse(
            detail="The census database is unavailable.", kind="unavailable"
        ).model_dump(),
    )


@app.get("/api/health")
async def health() -> dict:
    return {
        "status": "ok",
        "database": config.DB_PATH.exists(),
        "model_key_present": bool((os.environ.get("ANTHROPIC_API_KEY") or "").strip()),
        "limits": limiter.snapshot(),
    }


# --- Census data ----------------------------------------------------------
# Namespaced under /datasets/census/ so a second dataset is a new module and a
# nav entry rather than a routing change.

# Error responses are declared explicitly rather than left to the JSONResponse
# returns below. Without this, ErrorResponse never reaches the OpenAPI schema,
# `make types` never emits it, and the frontend ends up hand-writing the one
# type that generation was supposed to keep honest.
ERRORS = {
    429: {"model": schemas.ErrorResponse, "description": "Rate limited"},
    503: {"model": schemas.ErrorResponse, "description": "Dependency unavailable"},
}
NOT_FOUND = {404: {"model": schemas.ErrorResponse, "description": "Unknown category"}}


@app.get(
    "/api/datasets/census/categories",
    response_model=list[schemas.Category],
    responses=ERRORS,
)
async def categories(request: Request) -> list[dict]:
    await limiter.check_rate(client_ip(request), per_minute=config.CENSUS_PER_MINUTE)
    return db.list_categories()


@app.get(
    "/api/datasets/census/subcategories",
    response_model=list[schemas.SubcategoryRef],
    responses=ERRORS,
)
async def subcategories(request: Request) -> list[dict]:
    """Flat name index backing the explorer's search box."""
    await limiter.check_rate(client_ip(request), per_minute=config.CENSUS_PER_MINUTE)
    return db.list_subcategories()


@app.get(
    "/api/datasets/census/series",
    response_model=schemas.CategorySeries,
    responses={**ERRORS, **NOT_FOUND},
)
async def series(
    request: Request,
    category: str = Query(min_length=1),
) -> dict:
    await limiter.check_rate(client_ip(request), per_minute=config.CENSUS_PER_MINUTE)
    points = db.category_series(category)
    if not points:
        return JSONResponse(
            status_code=404,
            content=schemas.ErrorResponse(
                detail=f"No such category: {category}", kind="bad_request"
            ).model_dump(),
        )
    return {
        "category": category,
        "years": sorted({p["year"] for p in points}),
        "points": points,
    }


# --- Chat -----------------------------------------------------------------


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


@app.post(
    "/api/chat",
    responses={
        **ERRORS,
        200: {
            "content": {"text/event-stream": {}},
            "description": (
                "SSE stream. Event shapes are documented on agent.stream_ask and "
                "mirrored in web/src/api/events.ts — OpenAPI cannot describe them."
            ),
        },
    },
)
async def chat(request: Request, body: schemas.ChatRequest) -> StreamingResponse:
    """Stream an answer as Server-Sent Events.

    The client owns the history and sends it whole, so this handler holds no
    per-conversation state.
    """
    ip = client_ip(request)
    await limiter.check_rate(
        ip, per_minute=config.CHAT_PER_MINUTE, per_hour=config.CHAT_PER_HOUR
    )

    if not (os.environ.get("ANTHROPIC_API_KEY") or "").strip():
        return JSONResponse(
            status_code=503,
            content=schemas.ErrorResponse(
                detail="The assistant is not configured (no API key).", kind="unavailable"
            ).model_dump(),
        )

    # The slot is taken here, before any response begins, so exhaustion is a
    # clean 429 rather than an error event on an already-200 stream. Release
    # moves into the generator's finally, which is what runs when the client
    # disconnects mid-stream.
    stack = AsyncExitStack()
    await stack.enter_async_context(limiter.chat_slot(ip))

    messages = [m.model_dump() for m in body.messages]

    async def event_stream() -> AsyncIterator[str]:
        try:
            async for event in stream_ask(messages):
                yield _sse(event)
        except Exception:
            # A crash here is past the point of returning a status code, so the
            # only way to tell the client is in-band.
            log.exception("Unhandled error while streaming a chat response")
            yield _sse(
                {
                    "type": "error",
                    "message": "Something went wrong generating the answer.",
                    "retryable": True,
                }
            )
        finally:
            await stack.aclose()

    try:
        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                # Harmless now, load-bearing the moment nginx appears in front:
                # without it the proxy buffers the stream into one lump.
                "X-Accel-Buffering": "no",
            },
        )
    except Exception:
        # Constructing the response should not fail, but if it does the
        # generator never runs and its finally never fires.
        await stack.aclose()
        raise
