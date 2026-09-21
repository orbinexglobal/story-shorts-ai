"""
Tests for OpenRouter provider model discovery and cooldown behaviour.

Network calls are stubbed: `requests.get` feeds a fake /models response and
`requests.post` feeds a programmable /chat/completions response, so the
tests exercise the key-management, dead-model-skip, and per-key 429 logic
without touching the real API.
"""

from __future__ import annotations

import pytest

import providers.openrouter_provider as mod
from providers.base import ProviderError


class _FakeModelsResponse:
    def __init__(self, model_ids: list[str]) -> None:
        self._model_ids = model_ids

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {"data": [{"id": m} for m in self._model_ids]}


class _FakeChatResponse:
    def __init__(self, status_code: int, content: str | None = None) -> None:
        self.status_code = status_code
        self._content = content

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            import requests

            raise requests.exceptions.HTTPError(f"{self.status_code} error")

    def json(self) -> dict:
        return {
            "choices": [{"message": {"content": self._content}}],
        }


@pytest.fixture(autouse=True)
def _isolate_provider_state():
    """Reset the module-global discovery cache and cooldowns between tests."""
    with mod._cooldown_lock:
        mod._discovery_cache = None
        mod._dead_models.clear()
        mod._per_key_ratelimited.clear()
        mod._all_keys_ratelimited.clear()
    yield


@pytest.fixture(autouse=True)
def _no_live_network(monkeypatch, tmp_path):
    """Stub the models and chat endpoints; drop any env keys."""
    for name in mod._KEY_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)

    def fake_get(url, timeout):
        assert url == mod._MODELS_URL
        return _FakeModelsResponse(["m-a:free", "m-b:free"])

    monkeypatch.setattr(mod.requests, "get", fake_get)
    monkeypatch.setattr(mod.requests, "post", _fail_post)


def _fail_post(url, **kwargs):
    raise AssertionError("requests.post should be replaced per-test")


def _make_cfg(monkeypatch, tmp_path, preferred=None):
    import yaml

    from config.settings import load_config

    cfg_path = tmp_path / "config.yaml"
    preferred = preferred or ["m-a:free", "m-b:free"]
    cfg_path.write_text(
        yaml.safe_dump({
            "schedule": {"shorts_per_day": 1, "daily_upload_target": 10},
            "story": {"min_seconds": 20, "max_seconds": 30, "language": "en",
                      "tone": "reddit_storytime", "candidates_per_run": 2,
                      "min_acceptable_score": 7.0},
            "ai_providers": {
                "fallback_order": ["openrouter"],
                "max_retries_per_provider": 2,
                "retry_backoff_seconds": 0,
                "gemini": {"preferred_models": []},
                "openrouter": {
                    "auto_discover": True,
                    "discovery_timeout_seconds": 5,
                    "preferred_models": preferred,
                    "fallback_models": [],
                },
                "groq": {"preferred_models": []},
            },
            "tts": {"primary_provider": "edge_tts", "fallback_provider": "gemini",
                    "voice": "v", "gemini_voice": "g", "speaking_rate": 0.95},
            "video": {"resolution": [1080, 1920], "fps": 30, "audio_codec": "aac",
                      "video_codec": "h264", "render_preset": "veryfast",
                      "max_duration_seconds": 60, "gameplay_dir": "d",
                      "music_dir": "d", "font_dir": "d",
                      "avoid_repeat_gameplay": True, "music_volume_db": -18,
                      "music_fade_seconds": 2},
            "subtitles": {"words_per_group": 2, "font_size": 62,
                          "font_color": "white", "outline_color": "black"},
            "youtube": {"visibility": "public", "category_id": "24",
                        "default_language": "en", "made_for_kids": False},
            "logging": {"level": "INFO"},
            "rate_limits": {"requests_per_minute": {"openrouter": 1000}},
            "retry": {"max_retries": 3, "backoff_seconds": 0},
        }),
        encoding="utf-8",
    )
    return load_config(cfg_path)


def test_resolved_models_are_live_only(monkeypatch, tmp_path):
    cfg = _make_cfg(monkeypatch, tmp_path, preferred=["m-a:free", "m-dead:free"])
    monkeypatch.setenv("OPENROUTER_API_KEY", "k1")
    provider = mod.OpenRouterTextProvider(cfg)
    assert provider._models == ["m-a:free"]


class _SequenceChat:
    """Feeds a scripted sequence of responses to requests.post."""

    def __init__(self, responses: list[_FakeChatResponse]):
        self._responses = list(responses)
        self.calls: list[tuple[str, str]] = []

    def __call__(self, url, **kwargs):
        assert url == mod._API_URL
        model = kwargs["json"]["model"]
        self.calls.append((kwargs["headers"]["Authorization"], model))
        return self._responses.pop(0)


def test_dead_model_skipped_on_remaining_keys_and_retries(monkeypatch, tmp_path):
    cfg = _make_cfg(monkeypatch, tmp_path)
    monkeypatch.setenv("OPENROUTER_API_KEY", "key-1111")
    monkeypatch.setenv("OPENROUTER_API_KEY_2", "key-2222")
    provider = mod.OpenRouterTextProvider(cfg)

    chat = _SequenceChat([
        _FakeChatResponse(404),                 # m-a 404 on key1
        _FakeChatResponse(200, "ok from m-b"),   # m-b succeeds on key1
        _FakeChatResponse(200, "still m-b"),     # retry: m-a already skipped
    ])
    monkeypatch.setattr(mod.requests, "post", chat)

    first = provider.generate("p")
    second = provider.generate("p")

    assert first == "ok from m-b"
    assert second == "still m-b"
    # m-a was only attempted once (key1); never re-hit on key2 or the retry.
    assert chat.calls == [
        ("Bearer key-1111", "m-a:free"),
        ("Bearer key-1111", "m-b:free"),
        ("Bearer key-1111", "m-b:free"),
    ]


def test_per_key_429_falls_through_to_the_next_key(monkeypatch, tmp_path):
    cfg = _make_cfg(monkeypatch, tmp_path)
    monkeypatch.setenv("OPENROUTER_API_KEY", "key-1111")
    monkeypatch.setenv("OPENROUTER_API_KEY_2", "key-2222")
    provider = mod.OpenRouterTextProvider(cfg)

    chat = _SequenceChat([
        _FakeChatResponse(429),                 # m-a capped on key1
        _FakeChatResponse(200, "still m-a on key2"),
        # Next call: m-a skipped on key1, tried again on key2.
        _FakeChatResponse(200, "m-a on key2 again"),
    ])
    monkeypatch.setattr(mod.requests, "post", chat)

    first = provider.generate("p")
    second = provider.generate("p")

    assert first == "still m-a on key2"
    assert second == "m-a on key2 again"
    assert chat.calls == [
        ("Bearer key-1111", "m-a:free"),
        ("Bearer key-2222", "m-a:free"),
        ("Bearer key-2222", "m-a:free"),
    ]


def test_all_keys_ratelimited_skips_model_entirely(monkeypatch, tmp_path):
    cfg = _make_cfg(monkeypatch, tmp_path)
    monkeypatch.setenv("OPENROUTER_API_KEY", "key-1111")
    monkeypatch.setenv("OPENROUTER_API_KEY_2", "key-2222")
    provider = mod.OpenRouterTextProvider(cfg)

    chat = _SequenceChat([
        _FakeChatResponse(429),                 # m-a 429 on key1
        _FakeChatResponse(429),                 # m-a 429 on key2 -> global skip
        _FakeChatResponse(200, "m-b to the rescue"),
    ])
    monkeypatch.setattr(mod.requests, "post", chat)

    result = provider.generate("p")

    assert result == "m-b to the rescue"
    assert chat.calls == [
        ("Bearer key-1111", "m-a:free"),
        ("Bearer key-2222", "m-a:free"),
        ("Bearer key-1111", "m-b:free"),
    ]


def test_empty_model_list_raises(monkeypatch, tmp_path):
    cfg = _make_cfg(monkeypatch, tmp_path, preferred=["m-dead:free"])
    monkeypatch.setenv("OPENROUTER_API_KEY", "key-1111")
    with pytest.raises(ProviderError):
        mod.OpenRouterTextProvider(cfg)