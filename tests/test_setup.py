"""
Basic tests to verify project setup.
"""

import pytest


def test_import_barkem():
    """Test that the main package can be imported."""
    import barkem

    assert barkem.__version__ == "0.1.0"


def test_import_vision():
    """Test that vision module can be imported."""
    from barkem.vision import ScreenCapture, TemplateMatcher, TextReader

    assert ScreenCapture is not None
    assert TemplateMatcher is not None
    assert TextReader is not None


def test_import_input():
    """Test that input module can be imported."""
    from barkem.input import InputController, WindowManager

    assert InputController is not None
    assert WindowManager is not None


def test_import_bot():
    """Test that bot module can be imported."""
    from barkem.bot import OrchestratorBot, ChildBot

    assert OrchestratorBot is not None
    assert ChildBot is not None


def test_import_config():
    """Test that config module can be imported."""
    from barkem.config import Settings, get_settings

    assert Settings is not None
    settings = get_settings()
    assert settings.game.resolution == "1920x1080"


def test_settings_defaults():
    """Test that settings have expected defaults."""
    from barkem.config import Settings

    settings = Settings()
    assert settings.game.window_title == "THE FINALS"
    assert settings.api.port == 8080
    assert settings.redis.channel_prefix == "barkem"
