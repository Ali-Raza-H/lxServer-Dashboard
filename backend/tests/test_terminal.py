import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect


def _make_app(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("AUTH_DB", str(tmp_path / "auth.db"))
    monkeypatch.setenv("DASHBOARD_LOGS", str(tmp_path / "logs"))
    monkeypatch.setenv("DEV_ROOT", str(tmp_path / "devs"))
    monkeypatch.setenv("ENABLE_WEB_TERMINAL", "false")

    from app import config

    config.get_settings.cache_clear()

    from app.main import create_app

    return create_app()


def test_terminal_capability_default_disabled(tmp_path, monkeypatch):
    app = _make_app(tmp_path, monkeypatch)

    from app import deps, models

    app.dependency_overrides[deps.require_user] = lambda: models.User(id=1, username="test")

    with TestClient(app) as client:
        res = client.get("/api/terminal")
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data.get("supported"), bool)
        assert data.get("enabled") is False


def test_terminal_ws_disabled_closes(tmp_path, monkeypatch):
    app = _make_app(tmp_path, monkeypatch)
    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect) as exc:
            with client.websocket_connect("/ws/projects/whatever/terminal") as ws:
                ws.receive_text()
        assert exc.value.code == 4403

