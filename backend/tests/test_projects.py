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


def test_projects_requires_auth(tmp_path, monkeypatch):
    app = _make_app(tmp_path, monkeypatch)
    with TestClient(app) as client:
        res = client.get("/api/projects")
        assert res.status_code == 401


def test_projects_list_mocked_scan(tmp_path, monkeypatch):
    app = _make_app(tmp_path, monkeypatch)

    from app import deps, models, projects

    fake = [
        models.ProjectInfo(
            id="a" * 40,
            name="alpha",
            path="alpha",
            is_git=True,
            git_branch="main",
            git_dirty=False,
            detected_type="python",
            last_modified="2026-01-01T00:00:00+00:00",
        )
    ]

    monkeypatch.setattr(projects, "scan_projects", lambda _settings: fake)
    app.dependency_overrides[deps.require_user] = lambda: models.User(id=1, username="test")

    with TestClient(app) as client:
        res = client.get("/api/projects")
        assert res.status_code == 200
        data = res.json()
        assert data[0]["name"] == "alpha"
        assert data[0]["path"] == "alpha"

