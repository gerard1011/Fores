"""
FastAPI wrapper around the existing agent.py logic in app/.

agent.py opens the SQLite database using the relative path
"data/boroondara_census.db", which only resolves correctly if the process's
current working directory is the project root (the same assumption the
Streamlit app relies on when run via `streamlit run app/app.py` from the
repo root). To keep agent.py completely untouched, we chdir to the project
root below before importing it, so this API can be started from anywhere.
"""
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
APP_DIR = PROJECT_ROOT / "app"

os.chdir(PROJECT_ROOT)
sys.path.insert(0, str(APP_DIR))

import sqlite3

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agent import ask, query_census  # noqa: E402  (existing agent.py logic, reused as-is)

DB_PATH = PROJECT_ROOT / "data" / "boroondara_census.db"

app = FastAPI(title="Boroondara Census API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    question: str


class ChatResponse(BaseModel):
    answer: str


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    answer = ask(request.question)
    return ChatResponse(answer=answer)


@app.get("/categories")
def get_categories() -> list[str]:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT category FROM census_data ORDER BY category")
    categories = [row[0] for row in cursor.fetchall()]
    conn.close()
    return categories


@app.get("/subcategories")
def get_subcategories(category: str) -> list[str]:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT DISTINCT subcategory FROM census_data WHERE category = ? ORDER BY subcategory",
        (category,),
    )
    subcategories = [row[0] for row in cursor.fetchall()]
    conn.close()
    if not subcategories:
        raise HTTPException(status_code=404, detail=f"No subcategories found for category '{category}'")
    return subcategories


@app.get("/lookup")
def lookup(category: str, subcategory: str) -> list[dict]:
    results = query_census(category, subcategory)
    return [{"year": year, "value": value} for year, value in results]
