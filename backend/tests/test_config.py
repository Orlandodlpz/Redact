import logging

import pytest
from fastapi.testclient import TestClient

from app import config
from app.config import (
    HIGH_RISK_SAM_CLASSES,
    SWEEP_PHRASES,
    Settings,
    StartupError,
    assert_startup_safe,
    startup_problems,
)
from app.main import app


def make_settings(**overrides) -> Settings:
    # _env_file=None keeps a developer's local .env out of the test.
    return Settings(_env_file=None, **overrides)


def test_defaults_are_safe(monkeypatch):
    monkeypatch.delenv("OPENAI_LOG", raising=False)
    assert startup_problems(make_settings()) == []


@pytest.mark.parametrize("field", ["judge_model", "sam_model"])
@pytest.mark.parametrize("model_id", ["muse-spark-1.3-contributor", "SAM-3.1-Contributor"])
def test_contributor_model_id_refused(field, model_id):
    with pytest.raises(StartupError, match="contributor"):
        assert_startup_safe(make_settings(**{field: model_id}))


def test_request_body_logging_refused():
    with pytest.raises(StartupError, match="LOG_REQUEST_BODIES"):
        assert_startup_safe(make_settings(log_request_bodies=True))


def test_openai_debug_env_refused(monkeypatch):
    monkeypatch.setenv("OPENAI_LOG", "debug")
    with pytest.raises(StartupError, match="OPENAI_LOG"):
        assert_startup_safe(make_settings())


def test_debug_http_logger_refused():
    logger = logging.getLogger("openai")
    previous = logger.level
    logger.setLevel(logging.DEBUG)
    try:
        with pytest.raises(StartupError, match="openai"):
            assert_startup_safe(make_settings())
    finally:
        logger.setLevel(previous)


def test_premask_reads_on_off(monkeypatch):
    monkeypatch.setenv("PREMASK", "on")
    assert make_settings().premask is True
    monkeypatch.setenv("PREMASK", "off")
    assert make_settings().premask is False


def test_sweep_vocabulary():
    assert len(SWEEP_PHRASES) == 16
    assert len(set(SWEEP_PHRASES)) == 16
    assert HIGH_RISK_SAM_CLASSES == set(SWEEP_PHRASES) - {"street sign"}


@pytest.fixture
def fresh_settings(monkeypatch):
    monkeypatch.delenv("OPENAI_LOG", raising=False)
    config.get_settings.cache_clear()
    yield monkeypatch
    config.get_settings.cache_clear()


def test_health(fresh_settings):
    fresh_settings.setenv("JUDGE_MODEL", "muse-spark-1.3")
    fresh_settings.setenv("SAM_MODEL", "sam-3.1")
    fresh_settings.setenv("PREMASK", "off")
    with TestClient(app) as client:
        body = client.get("/health").json()
    assert body == {
        "status": "ok",
        "version": config.VERSION,
        "model_ids": {"judge": "muse-spark-1.3", "sam": "sam-3.1"},
        "premask": "off",
    }


def test_server_refuses_to_start_with_contributor_id(fresh_settings):
    fresh_settings.setenv("JUDGE_MODEL", "muse-spark-1.3-contributor")
    with pytest.raises(StartupError):
        with TestClient(app):
            pass
