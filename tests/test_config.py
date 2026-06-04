"""Smoke tests for SECRET_KEY resolution behaviour."""

import importlib

import pytest


def _reload_app_module():
    import app as app_module

    return importlib.reload(app_module)


def test_secret_key_from_env(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "from-env-value")
    monkeypatch.delenv("FLASK_ENV", raising=False)

    mod = _reload_app_module()
    assert mod.app.config["SECRET_KEY"] == "from-env-value"


def test_secret_key_missing_in_production_raises(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.setenv("FLASK_ENV", "production")

    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        _reload_app_module()


def test_secret_key_dev_fallback_warns(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.delenv("FLASK_ENV", raising=False)

    with pytest.warns(RuntimeWarning, match="SECRET_KEY"):
        mod = _reload_app_module()

    assert "insecure" in mod.app.config["SECRET_KEY"]
