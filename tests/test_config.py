"""Tests for config/settings.py."""

from config.settings import load_config


def test_load_config_defaults():
    cfg = load_config()
    assert cfg.project_name == "StoryShorts AI"
    assert cfg.story.min_seconds < cfg.story.max_seconds
    assert cfg.video.resolution == (1080, 1920)
    assert "gemini" in cfg.ai_providers.fallback_order


def test_ai_provider_fallback_order_has_known_providers():
    cfg = load_config()
    known = {"gemini", "openrouter", "groq"}
    assert set(cfg.ai_providers.fallback_order).issubset(known)
