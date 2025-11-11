import csv
import io
from datetime import datetime

from routes import (
    _to_float,
    _parse_any_datetime,
    _extract_json,
    _aggregate_userexercise_daily,
    _is_userexercise_headers,
)


def test_to_float_ok():
    assert _to_float("1.5") == 1.5
    assert _to_float("1,5") == 1.5
    assert _to_float(2) == 2.0


def test_to_float_invalid():
    assert _to_float("abc") is None
    assert _to_float("") is None
    assert _to_float(None) is None


def test_parse_any_datetime_valid():
    d = _parse_any_datetime("2025-05-01T10:30:00")
    assert isinstance(d, datetime)
    assert d.year == 2025
    assert d.month == 5
    assert d.day == 1


def test_parse_any_datetime_invalid():
    assert _parse_any_datetime("no es una fecha") is None


def test_extract_json_plain():
    raw = '{"score": 4, "advice": "ok"}'
    data = _extract_json(raw)
    assert data["score"] == 4
    assert data["advice"] == "ok"


def test_extract_json_markdown_block():
    raw = """```json
    {
      "score": 5,
      "advice": "muy bien"
    }
    ```"""
    data = _extract_json(raw)
    assert data["score"] == 5
    assert "muy bien" in data["advice"]


def test_is_userexercise_headers_true():
    headers = [
        "exerciseId",
        "startTime",
        "endTime",
        "steps",
        "calories",
        "distanceKm",
    ]
    lower = [h.lower().strip() for h in headers]
    assert _is_userexercise_headers(lower) is True


def test_is_userexercise_headers_false():
    headers = ["col1", "col2", "otra_cosa"]
    lower = [h.lower().strip() for h in headers]
    assert _is_userexercise_headers(lower) is False


def test_aggregate_userexercise_daily_basic():
    csv_data = """startTime,endTime,steps,calories,distancia,avghr,maxhr
2025-05-15T10:00:00,2025-05-15T11:00:00,1000,50,2.0,120,150
2025-05-15T12:00:00,2025-05-15T12:30:00,500,20,1.0,110,140
"""
    reader = csv.DictReader(io.StringIO(csv_data))
    agg = _aggregate_userexercise_daily(reader)

    # Debe haber un solo día
    assert len(agg) == 1
    day, feats = next(iter(agg.items()))
    assert isinstance(day, datetime)

    # Sumas correctas
    assert feats["steps"] == 1500.0
    assert feats["calories_kcal"] == 70.0
    # distancia total en km (2.0 + 1.0)
    assert feats["distance_km"] == 3.0

    # Medias de FC
    assert feats["avg_hr"] == (120 + 110) / 2
    assert feats["max_hr"] == (150 + 140) / 2

    # Número de muestras
    assert feats["samples"] == 2
