"""Tests for the youtube/uploader.py credential preflight (no network)."""

import pytest

from providers.base import ProviderError
from youtube import uploader


class _FakeRequest:
    pass


class _RejectingCreds:
    def refresh(self, request):
        raise Exception("invalid_grant: Bad Request")


class _ValidCreds:
    def refresh(self, request):
        self.refreshed_with = request


def _stub_request(monkeypatch):
    monkeypatch.setattr("google.auth.transport.requests.Request", _FakeRequest)


def test_check_youtube_credentials_ok_when_token_valid(monkeypatch):
    creds = _ValidCreds()
    monkeypatch.setattr(uploader, "get_credentials", lambda: creds)
    _stub_request(monkeypatch)

    uploader.check_youtube_credentials()

    assert creds.refreshed_with is not None


def test_check_youtube_credentials_gives_actionable_hint_on_invalid_grant(monkeypatch):
    monkeypatch.setattr(uploader, "get_credentials", lambda: _RejectingCreds())
    _stub_request(monkeypatch)

    with pytest.raises(ProviderError) as exc_info:
        uploader.check_youtube_credentials()
    assert "invalid_grant" in str(exc_info.value)
    assert "YOUTUBE_REFRESH_TOKEN" in str(exc_info.value)


def test_check_youtube_credentials_fails_cleanly_when_env_missing(monkeypatch):
    monkeypatch.delenv("YOUTUBE_CLIENT_ID", raising=False)
    monkeypatch.delenv("YOUTUBE_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("YOUTUBE_REFRESH_TOKEN", raising=False)
    _stub_request(monkeypatch)

    with pytest.raises(ProviderError, match="Missing required YouTube credentials"):
        uploader.check_youtube_credentials()