from datetime import datetime, timedelta

from flask import g

from app import create_app
from extensions import mongo
from routes import metrics_series, metrics_detail, metrics_detail_by_date


# Creamos instancia de la app para los tests
app = create_app()

TEST_SUB = "test-user-metrics-123"


def _clear_all_for_user():
    """Deja limpia la conjunto de colecciones relacionadas con métricas para el usuario de pruebas."""
    with app.app_context():
        mongo.db.measurements.delete_many({"sub": TEST_SUB})
        mongo.db.sleep_raw.delete_many({"sub": TEST_SUB})
        mongo.db.stress_raw.delete_many({"sub": TEST_SUB})
        mongo.db.activity_raw.delete_many({"sub": TEST_SUB})
        mongo.db.spo2_raw.delete_many({"sub": TEST_SUB})


def _normalize_resp(resp):
    """
    Las vistas a veces devuelven:
      - Response
      - (Response, status_code)
    Esta función lo normaliza a (Response, status_code).
    """
    if isinstance(resp, tuple):
        r, code = resp
        return r, code
    return resp, resp.status_code


# -------------------------------------------------------------------
# tests para /metrics/series
# -------------------------------------------------------------------


def test_metrics_series_empty():
    """
    Si no hay mediciones para ese usuario y tipo, /metrics/series debe devolver
    ok=True y lista de puntos vacía.
    """
    _clear_all_for_user()

    with app.test_request_context("/api/metrics/series?type=sleep&minutes=60"):
        g.current_user = {"sub": TEST_SUB}

        resp = metrics_series.__wrapped__()  # saltamos @requires_auth
        resp, status = _normalize_resp(resp)
        assert status == 200

        data = resp.get_json()
        assert data["ok"] is True
        assert isinstance(data["points"], list)
        assert data["points"] == []


def test_metrics_series_with_data():
    """
    Si hay mediciones, deben devolverse ordenadas en points[].
    """
    _clear_all_for_user()
    now = datetime.utcnow()

    with app.app_context():
        mongo.db.measurements.insert_many(
            [
                {
                    "sub": TEST_SUB,
                    "type": "sleep",
                    "ts": now - timedelta(minutes=30),
                    "value": 4,
                    "source": "test",
                },
                {
                    "sub": TEST_SUB,
                    "type": "sleep",
                    "ts": now - timedelta(minutes=10),
                    "value": 2,
                    "source": "test",
                },
            ]
        )

    with app.test_request_context("/api/metrics/series?type=sleep&minutes=60"):
        g.current_user = {"sub": TEST_SUB}

        resp = metrics_series.__wrapped__()
        resp, status = _normalize_resp(resp)
        assert status == 200

        data = resp.get_json()
        assert data["ok"] is True
        points = data["points"]

        assert len(points) == 2
        # Orden por tiempo
        t0 = points[0]["t"]
        t1 = points[1]["t"]
        assert t0 < t1
        assert [p["v"] for p in points] == [4, 2]


def test_metrics_series_missing_type():
    """
    Si falta el parámetro type, debe devolver 400 y ok=False.
    """
    _clear_all_for_user()

    with app.test_request_context("/api/metrics/series"):
        g.current_user = {"sub": TEST_SUB}

        resp = metrics_series.__wrapped__()
        resp, status = _normalize_resp(resp)
        assert status == 400

        data = resp.get_json()
        assert data["ok"] is False
        assert "Falta type" in data["error"]


def test_metrics_series_invalid_range():
    """
    Si from/to son inválidos o from >= to, debe devolver 400.
    """
    _clear_all_for_user()

    # from == to
    url = "/api/metrics/series?type=sleep&from=2025-01-01T00:00:00&to=2025-01-01T00:00:00"
    with app.test_request_context(url):
        g.current_user = {"sub": TEST_SUB}

        resp = metrics_series.__wrapped__()
        resp, status = _normalize_resp(resp)
        assert status == 400
        data = resp.get_json()
        assert data["ok"] is False

    # from después de to
    url2 = "/api/metrics/series?type=sleep&from=2025-01-02T00:00:00&to=2025-01-01T00:00:00"
    with app.test_request_context(url2):
        g.current_user = {"sub": TEST_SUB}

        resp2 = metrics_series.__wrapped__()
        resp2, status2 = _normalize_resp(resp2)
        assert status2 == 400
        data2 = resp2.get_json()
        assert data2["ok"] is False


# -------------------------------------------------------------------
# tests para /metrics/detail
# -------------------------------------------------------------------


def test_metrics_detail_missing_params():
    """
    Si faltan type o ts, debe devolver 400.
    """
    _clear_all_for_user()

    # Sin type ni ts
    with app.test_request_context("/api/metrics/detail"):
        g.current_user = {"sub": TEST_SUB}
        resp = metrics_detail.__wrapped__()
        resp, status = _normalize_resp(resp)
        assert status == 400
        data = resp.get_json()
        assert data["ok"] is False

    # Con type pero sin ts
    with app.test_request_context("/api/metrics/detail?type=sleep"):
        g.current_user = {"sub": TEST_SUB}
        resp2 = metrics_detail.__wrapped__()
        resp2, status2 = _normalize_resp(resp2)
        assert status2 == 400
        data2 = resp2.get_json()
        assert data2["ok"] is False


def test_metrics_detail_invalid_ts():
    """
    Si ts es inválido, debe devolver 400.
    """
    _clear_all_for_user()

    url = "/api/metrics/detail?type=sleep&ts=no-es-una-fecha"
    with app.test_request_context(url):
        g.current_user = {"sub": TEST_SUB}
        resp = metrics_detail.__wrapped__()
        resp, status = _normalize_resp(resp)
        assert status == 400
        data = resp.get_json()
        assert data["ok"] is False


def test_metrics_detail_not_found():
    """
    /metrics/detail debe devolver 404 si no hay medición para ese ts.
    """
    _clear_all_for_user()
    ts = datetime.utcnow().isoformat()

    url = f"/api/metrics/detail?type=sleep&ts={ts}"
    with app.test_request_context(url):
        g.current_user = {"sub": TEST_SUB}

        resp = metrics_detail.__wrapped__()
        resp, status = _normalize_resp(resp)
        assert status == 404

        data = resp.get_json()
        assert data["ok"] is False


def test_metrics_detail_with_features_and_spo2():
    """
    /metrics/detail (sleep) debe devolver:
      - value, ts, advice, etc. de measurements
      - features combinando sleep_raw y spo2_raw del día.
    """
    _clear_all_for_user()

    ts = datetime(2025, 5, 10, 23, 0, 0)

    with app.app_context():
        # Medición principal
        mongo.db.measurements.insert_one(
            {
                "sub": TEST_SUB,
                "type": "sleep",
                "ts": ts,
                "value": 4,
                "advice": "Duermes bastante bien.",
                "source": "test",
                "scored_at": ts + timedelta(minutes=5),
            }
        )

        # RAW de sueño
        mongo.db.sleep_raw.insert_one(
            {
                "sub": TEST_SUB,
                "ts": ts,
                "ts_str": ts.isoformat(),
                "features": {
                    "minutos_en_cama": 420,
                    "despertares": 2,
                },
            }
        )

        # RAW de SpO2 del mismo día
        day = datetime(2025, 5, 10, 12, 0, 0)
        mongo.db.spo2_raw.insert_one(
            {
                "sub": TEST_SUB,
                "ts": day,
                "ts_str": day.isoformat(),
                "features": {"spo2_avg": 97.5},
            }
        )

    url = f"/api/metrics/detail?type=sleep&ts={ts.isoformat()}"
    with app.test_request_context(url):
        g.current_user = {"sub": TEST_SUB}

        resp = metrics_detail.__wrapped__()
        resp, status = _normalize_resp(resp)
        assert status == 200

        data = resp.get_json()
        assert data["ok"] is True
        assert data["value"] == 4
        assert "Duermes bastante bien" in data["advice"]

        feats = data["features"]
        # Vienen los features de sueño y de SpO2
        assert feats["minutos_en_cama"] == 420
        assert feats["despertares"] == 2
        assert feats["spo2_avg"] == 97.5


def test_metrics_detail_stress_features_only():
    """
    /metrics/detail (stress) debe devolver features desde stress_raw (sin SpO2 si no hay).
    """
    _clear_all_for_user()
    ts = datetime(2025, 7, 1, 10, 0, 0)

    with app.app_context():
        mongo.db.measurements.insert_one(
            {
                "sub": TEST_SUB,
                "type": "stress",
                "ts": ts,
                "value": 2,
                "advice": "Estrés elevado.",
                "source": "test",
                "scored_at": ts + timedelta(minutes=5),
            }
        )
        mongo.db.stress_raw.insert_one(
            {
                "sub": TEST_SUB,
                "ts": ts,
                "ts_str": ts.isoformat(),
                "features": {"eda_level_real": 0.8},
            }
        )

    url = f"/api/metrics/detail?type=stress&ts={ts.isoformat()}"
    with app.test_request_context(url):
        g.current_user = {"sub": TEST_SUB}
        resp = metrics_detail.__wrapped__()
        resp, status = _normalize_resp(resp)
        assert status == 200

        data = resp.get_json()
        assert data["ok"] is True
        assert data["value"] == 2
        feats = data["features"]
        # Debe contener el valor de EDA agregado
        assert feats["eda_level_real"] == 0.8
        # Y no tiene por qué tener spo2_avg si no lo hemos guardado
        assert "spo2_avg" not in feats


def test_metrics_detail_activity_features_only():
    """
    /metrics/detail (activity) debe devolver features desde activity_raw.
    """
    _clear_all_for_user()
    ts = datetime(2025, 7, 2, 18, 0, 0)

    with app.app_context():
        mongo.db.measurements.insert_one(
            {
                "sub": TEST_SUB,
                "type": "activity",
                "ts": ts,
                "value": 5,
                "advice": "Actividad excelente.",
                "source": "test",
                "scored_at": ts + timedelta(minutes=5),
            }
        )
        mongo.db.activity_raw.insert_one(
            {
                "sub": TEST_SUB,
                "ts": ts,
                "ts_str": ts.isoformat(),
                "features": {
                    "steps": 12000,
                    "active_minutes": 65,
                },
            }
        )

    url = f"/api/metrics/detail?type=activity&ts={ts.isoformat()}"
    with app.test_request_context(url):
        g.current_user = {"sub": TEST_SUB}
        resp = metrics_detail.__wrapped__()
        resp, status = _normalize_resp(resp)
        assert status == 200

        data = resp.get_json()
        assert data["ok"] is True
        assert data["value"] == 5
        feats = data["features"]
        assert feats["steps"] == 12000
        assert feats["active_minutes"] == 65


# -------------------------------------------------------------------
# tests para /metrics/detail/by_date
# -------------------------------------------------------------------


def test_metrics_detail_by_date_missing_params():
    """
    Si faltan type o date, debe devolver 400.
    """
    _clear_all_for_user()

    # Sin type ni date
    with app.test_request_context("/api/metrics/detail/by_date"):
        g.current_user = {"sub": TEST_SUB}
        resp = metrics_detail_by_date.__wrapped__()
        resp, status = _normalize_resp(resp)
        assert status == 400
        data = resp.get_json()
        assert data["ok"] is False

    # Con type pero sin date
    with app.test_request_context("/api/metrics/detail/by_date?type=sleep"):
        g.current_user = {"sub": TEST_SUB}
        resp2 = metrics_detail_by_date.__wrapped__()
        resp2, status2 = _normalize_resp(resp2)
        assert status2 == 400
        data2 = resp2.get_json()
        assert data2["ok"] is False


def test_metrics_detail_by_date_invalid_date():
    """
    Si date es inválido, debe devolver 400.
    """
    _clear_all_for_user()
    url = "/api/metrics/detail/by_date?type=sleep&date=no-es-fecha"
    with app.test_request_context(url):
        g.current_user = {"sub": TEST_SUB}
        resp = metrics_detail_by_date.__wrapped__()
        resp, status = _normalize_resp(resp)
        assert status == 400
        data = resp.get_json()
        assert data["ok"] is False


def test_metrics_detail_by_date_not_found():
    """
    Si no hay medición para esa fecha, debe devolver 404.
    """
    _clear_all_for_user()
    url = "/api/metrics/detail/by_date?type=sleep&date=2025-06-01"
    with app.test_request_context(url):
        g.current_user = {"sub": TEST_SUB}
        resp = metrics_detail_by_date.__wrapped__()
        resp, status = _normalize_resp(resp)
        assert status == 404
        data = resp.get_json()
        assert data["ok"] is False


def test_metrics_detail_by_date_ok():
    """
    /metrics/detail/by_date debe localizar la medición por rango diario,
    y devolver features como metrics_detail.
    """
    _clear_all_for_user()

    ts = datetime(2025, 6, 1, 22, 30, 0)

    with app.app_context():
        mongo.db.measurements.insert_one(
            {
                "sub": TEST_SUB,
                "type": "sleep",
                "ts": ts,
                "value": 3,
                "advice": "Sueño mejorable.",
                "source": "test",
                "scored_at": ts + timedelta(minutes=5),
            }
        )
        mongo.db.sleep_raw.insert_one(
            {
                "sub": TEST_SUB,
                "ts": ts,
                "ts_str": ts.isoformat(),
                "features": {"minutos_en_cama": 380},
            }
        )

    url = "/api/metrics/detail/by_date?type=sleep&date=2025-06-01"
    with app.test_request_context(url):
        g.current_user = {"sub": TEST_SUB}

        resp = metrics_detail_by_date.__wrapped__()
        resp, status = _normalize_resp(resp)
        assert status == 200

        data = resp.get_json()
        assert data["ok"] is True
        assert data["value"] == 3
        feats = data["features"]
        assert feats["minutos_en_cama"] == 380
