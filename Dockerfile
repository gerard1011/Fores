FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY api/ ./api/
COPY pipeline/ ./pipeline/

# data/ is deliberately NOT copied. The database is gitignored, so COPY data/
# fails outright on a fresh clone, and baking it in means a full rebuild for
# every data refresh. It is bind-mounted read-only instead — see
# docker-compose.yml.

# Lets `api.agent` resolve when Streamlit runs api/app.py as a script.
ENV PYTHONPATH=/app

RUN useradd --create-home appuser
USER appuser

EXPOSE 8000 8501

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
