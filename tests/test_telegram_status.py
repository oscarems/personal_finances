from fastapi.testclient import TestClient

from finance_app.app import app
from finance_app.config import reset_settings_cache


def _clear_telegram_env(monkeypatch):
    for key in (
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
        "BOT_TOKEN",
        "CHAT_ID",
        "TELEGRAM_ALLOWED_CHAT_ID",
    ):
        monkeypatch.delenv(key, raising=False)


def test_status_configured_false(monkeypatch):
    _clear_telegram_env(monkeypatch)
    reset_settings_cache()
    client = TestClient(app)
    response = client.get("/api/telegram/status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["configured"] is False
    assert "Faltan variables TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID" in payload["message"]


def test_status_configured_true(monkeypatch):
    _clear_telegram_env(monkeypatch)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:ABCDEF")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "987654321")
    reset_settings_cache()
    client = TestClient(app)
    response = client.get("/api/telegram/status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["configured"] is True
    assert payload["masked_token"].endswith("CDEF")
    assert payload["chat_id"].endswith("4321")


def test_save_settings_rejects_secrets(monkeypatch):
    _clear_telegram_env(monkeypatch)
    reset_settings_cache()
    client = TestClient(app)
    response = client.post(
        "/api/telegram/settings",
        json={"bot_token": "nope", "chat_id": "123"},
    )
    assert response.status_code == 400
