import os
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from psycopg2.extras import RealDictCursor

from db import get_connection

load_dotenv()

API_SHARED_TOKEN = os.getenv("GAS_API_TOKEN")

app = FastAPI(title="Fear & Greed API")


def _json_safe(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    return value


def verify_token(authorization: str | None = Header(default=None)):
    if not API_SHARED_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="GAS_API_TOKEN is not configured",
        )

    expected = f"Bearer {API_SHARED_TOKEN}"
    if authorization != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
        )


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/api/daily-scores/latest", dependencies=[Depends(verify_token)])
def get_latest_daily_scores(limit: int = Query(default=500, ge=1, le=5000)):
    query = """
        SELECT date, ticker, raw_fgi, filtered_fgi, indicators, created_at
        FROM daily_sentiment_scores
        WHERE date = (
            SELECT MAX(date)
            FROM daily_sentiment_scores
        )
        ORDER BY ticker
        LIMIT %s;
    """

    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, (limit,))
            rows = cur.fetchall()

    return _json_safe(list(rows))
