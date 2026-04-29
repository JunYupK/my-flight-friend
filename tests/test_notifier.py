"""
테스트: notifier 모듈
외부 HTTP 호출은 monkeypatch로 mock.
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from flight_monitor import notifier


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for var in (
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
        "DISCORD_WEBHOOK_URL",
    ):
        monkeypatch.delenv(var, raising=False)
    yield


class _FakeResponse:
    def __init__(self, ok: bool):
        self.ok = ok


def _stub_post(call_log: list, ok: bool):
    def _post(url, **kwargs):
        call_log.append({"url": url, **kwargs})
        return _FakeResponse(ok)
    return _post


class TestSendAlertFallback:
    def test_telegram_only_when_both_configured(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "1")
        monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.example/hook")
        calls: list = []
        monkeypatch.setattr(notifier.requests, "post", _stub_post(calls, ok=True))

        result = notifier.send_alert("hi")

        assert result == "telegram"
        assert len(calls) == 1
        assert "api.telegram.org" in calls[0]["url"]

    def test_discord_fallback_when_telegram_missing(self, monkeypatch):
        monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.example/hook")
        calls: list = []
        monkeypatch.setattr(notifier.requests, "post", _stub_post(calls, ok=True))

        result = notifier.send_alert("hi")

        assert result == "discord"
        assert len(calls) == 1
        assert "discord.example" in calls[0]["url"]

    def test_discord_fallback_when_telegram_fails(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "1")
        monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.example/hook")
        calls: list = []

        def _post(url, **kwargs):
            calls.append(url)
            ok = "discord.example" in url
            return _FakeResponse(ok)

        monkeypatch.setattr(notifier.requests, "post", _post)

        result = notifier.send_alert("hi")

        assert result == "discord"
        assert len(calls) == 2

    def test_returns_none_when_both_missing(self, monkeypatch):
        calls: list = []
        monkeypatch.setattr(notifier.requests, "post", _stub_post(calls, ok=True))

        result = notifier.send_alert("hi")

        assert result is None
        assert calls == []
