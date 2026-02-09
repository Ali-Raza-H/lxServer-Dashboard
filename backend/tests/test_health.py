from fastapi.testclient import TestClient


def _make_app(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("AUTH_DB", str(tmp_path / "auth.db"))
    monkeypatch.setenv("DASHBOARD_LOGS", str(tmp_path / "logs"))
    monkeypatch.setenv("DEV_ROOT", str(tmp_path / "devs"))

    from app import config

    config.get_settings.cache_clear()

    from app.main import create_app

    return create_app()


def test_health_ok(tmp_path, monkeypatch):
    app = _make_app(tmp_path, monkeypatch)
    with TestClient(app) as client:
        res = client.get("/api/health")
        assert res.status_code == 200
        assert res.json() == {"ok": True}

