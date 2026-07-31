"""Pydantic models — the source of truth for the generated TypeScript types.

`make types` runs openapi-typescript over FastAPI's schema, so a field renamed
here breaks the frontend build rather than production. The SSE event shapes are
the exception: OpenAPI cannot describe them, so they live in agent.stream_ask's
docstring and are mirrored by hand in web/src/api/events.ts.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field


class Level(BaseModel):
    level: str = Field(description="Geography granularity: 'LGA' or 'STE'.")
    area_count: int = Field(
        description="Areas at this level in the latest census year — the universe the picker offers."
    )


class Geography(BaseModel):
    geo_code: str = Field(description="Stable cross-year identifier; passed back in /series.")
    geo_name: str = Field(description="Canonical display name, unique within the level.")


class Category(BaseModel):
    category: str
    subcategory_count: int = Field(
        description="Distinct subcategories. 1 means a single number, not a chart."
    )


class SubcategoryRef(BaseModel):
    category: str
    subcategory: str


class SeriesPoint(BaseModel):
    geo_code: str
    geo_name: str = Field(description="Canonical name for the area, for the legend.")
    subcategory: str
    year: int
    value: int


class CategorySeries(BaseModel):
    category: str
    level: str
    geographies: list[Geography] = Field(
        description="The areas echoed back, so the client can build the legend without a second call."
    )
    years: list[int] = Field(description="Sorted, so the chart can build its axis directly.")
    points: list[SeriesPoint]


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    # Assistant turns replayed from a previous response carry structured content
    # blocks, not a plain string, so this stays permissive.
    content: Any


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1)


class ErrorResponse(BaseModel):
    detail: str
    kind: Literal["rate", "concurrency", "capacity", "bad_request", "unavailable"]
    retry_after: int | None = None
