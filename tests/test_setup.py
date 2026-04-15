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
    from barkem.vision import ScreenCapture, TemplateMatcher, TextReader, ChatReader, CommandMonitor

    assert ScreenCapture is not None
    assert TemplateMatcher is not None
    assert TextReader is not None
    assert ChatReader is not None
    assert CommandMonitor is not None


def test_import_input():
    """Test that input module can be imported."""
    from barkem.input import InputController, WindowManager

    assert InputController is not None
    assert WindowManager is not None


def test_import_bot():
    """Test that bot module can be imported."""
    from barkem.bot import BarkEmBot, BarkEmStateMachine, MatchConfig, TeamInfo

    assert BarkEmBot is not None
    assert BarkEmStateMachine is not None
    assert MatchConfig is not None
    assert TeamInfo is not None


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


def test_team_info_captain():
    """Test that TeamInfo correctly identifies captain."""
    from barkem.bot import TeamInfo

    team = TeamInfo(
        team_id=1,
        name="Test Team",
        players=[
            {"embark_id": "Captain#1234", "display_name": "Captain"},
            {"embark_id": "Player2#5678", "display_name": "Player2"},
            {"embark_id": "Player3#9012", "display_name": "Player3"},
        ],
    )

    assert team.captain_embark_id == "Captain#1234"
    assert team.captain["display_name"] == "Captain"


def test_match_config():
    """Test MatchConfig dataclass."""
    from barkem.bot import MatchConfig

    config = MatchConfig(
        match_id="test-123",
        mode="final_round",
        map="monaco",
        cancel_timeout_seconds=300,
    )

    assert config.match_id == "test-123"
    assert config.mode == "final_round"
    assert config.variant == "default"
    assert config.cancel_timeout_seconds == 300
