"""Regression tests for shared user projects and profile-private system projects."""
import json
import threading

import pytest


def _project_storage(monkeypatch, tmp_path):
    import api.config as config
    import api.models as models

    projects_file = tmp_path / "projects.json"
    monkeypatch.setattr(config, "PROJECTS_FILE", projects_file)
    monkeypatch.setattr(models, "PROJECTS_FILE", projects_file)
    monkeypatch.setattr(models, "_projects_migrated", True)
    monkeypatch.setattr(models, "_CRON_PROJECT_LOCK", threading.Lock())
    return projects_file


def test_ensure_cron_project_creates_per_profile(tmp_path, monkeypatch):
    import api.models as models
    import api.profiles as profiles

    projects_file = _project_storage(monkeypatch, tmp_path)
    profiles._invalidate_root_profile_cache()
    monkeypatch.setattr(profiles, "list_profiles_api", lambda: [])
    monkeypatch.setattr(profiles, "_active_profile", "architect")
    architect = models.ensure_cron_project()
    monkeypatch.setattr(profiles, "_active_profile", "researcher")
    researcher = models.ensure_cron_project()

    assert architect != researcher
    rows = json.loads(projects_file.read_text(encoding="utf-8"))
    assert {row["profile"] for row in rows} == {"architect", "researcher"}
    assert all(not row.get("shared") for row in rows)


def test_shared_user_projects_are_visible_across_profiles():
    import api.models as models

    project = {"project_id": "work", "name": "work", "shared": True}
    assert models.project_is_available_to_profile(project, "default")
    assert models.project_is_available_to_profile(project, "architect")


def test_system_projects_remain_private():
    import api.models as models

    cron = {"project_id": "cron", "name": "Cron Jobs", "profile": "architect"}
    assert models.project_is_available_to_profile(cron, "architect")
    assert not models.project_is_available_to_profile(cron, "default")


def test_project_routes_use_shared_availability_contract():
    from pathlib import Path

    source = (Path(__file__).parents[1] / "api" / "routes.py").read_text(encoding="utf-8")
    assert source.count("project_is_available_to_profile(") >= 5
    create = source[source.find('"/api/projects/create"'):source.find('"/api/projects/rename"')]
    assert '"shared": True' in create


@pytest.fixture(autouse=True)
def _reset_project_migration():
    import api.models as models

    models._projects_migrated = False
    yield
    models._projects_migrated = False
