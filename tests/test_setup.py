"""
Basic tests to verify project setup and imports.
"""

import pytest


def test_import_barkem():
    import barkem
    assert barkem.__version__ == "0.1.0"


def test_import_vision():
    from barkem.vision import (
        ScreenCapture, TemplateMatcher, TextReader,
        ChatReader, CommandMonitor, GameStateDetector, GameScreen,
    )
    assert ScreenCapture is not None
    assert GameStateDetector is not None


def test_import_input():
    from barkem.input import (
        GamepadController, GamepadConfig,
        MenuNavigator, MenuSequences,
        LobbyNavigator, LobbyGrid,
        WindowManager,
    )
    assert GamepadController is not None
    assert MenuNavigator is not None
    assert LobbyNavigator is not None


def test_import_bot():
    from barkem.bot import BarkEmBot, BarkEmStateMachine, MatchConfig, TeamInfo
    assert BarkEmBot is not None


def test_import_config():
    from barkem.config import Settings, get_settings
    assert Settings is not None
    settings = Settings()
    assert settings.game.resolution == "1920x1080"


def test_settings_defaults():
    from barkem.config import Settings
    settings = Settings()
    assert settings.game.window_title == "THE FINALS"
    assert settings.api.port == 8080
    assert settings.input.button_delay == 0.15
    assert settings.input.anchor_presses == 5


def test_team_info_captain():
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


def test_match_config():
    from barkem.bot import MatchConfig
    config = MatchConfig(
        match_id="test-123",
        mode="final_round",
        map="monaco",
    )
    assert config.variant == "default"
    assert config.cancel_timeout_seconds == 300


def test_gamepad_config_defaults():
    from barkem.input import GamepadConfig
    cfg = GamepadConfig()
    assert cfg.button_delay == 0.15
    assert cfg.hold_duration == 0.05
    assert cfg.anchor_presses == 5


def test_lobby_grid_defaults():
    from barkem.input import LobbyGrid
    grid = LobbyGrid()
    assert grid.team1_rows == 3
    assert grid.team2_rows == 3
    assert grid.context_move_self == 1
    assert grid.context_move_other == 2


def test_menu_sequences_defaults():
    from barkem.input import MenuSequences
    seq = MenuSequences()
    assert seq.mode_anchor_up == 7
    assert seq.mode_down_to_private == 7
    assert len(seq.private_to_create) >= 1


def test_regions_load_from_dict():
    from barkem.vision.regions import load_regions_from_dict
    data = {
        "lobby": {
            "lobby_code": [69, 195, 133, 234],
            "team1_player1_name": [1235, 142, 1861, 184],
        },
        "chat": {
            "chat_area": [100, 806, 509, 994],
        },
    }
    regions = load_regions_from_dict(data)
    assert regions.lobby.lobby_code.x1 == 69
    assert regions.lobby.team1_player1_name.x2 == 1861
    assert regions.chat.chat_area.y2 == 994


def test_regions_skip_non_region_values():
    from barkem.vision.regions import load_regions_from_dict
    data = {
        "lobby": {
            "lobby_code": [69, 195, 133, 234],
            "nonexistent_field": [1, 2, 3, 4],  # should be ignored
        },
    }
    regions = load_regions_from_dict(data)
    assert regions.lobby.lobby_code.x1 == 69


def test_settings_input_controller_fields():
    from barkem.config import Settings
    s = Settings()
    assert hasattr(s.input, "button_delay")
    assert hasattr(s.input, "hold_duration")
    assert hasattr(s.input, "anchor_presses")
    assert not hasattr(s.input, "click_delay_min")  # old mouse field gone


def test_settings_sequences():
    from barkem.config import Settings
    s = Settings()
    assert isinstance(s.sequences.mode_anchor_up, int)
    assert isinstance(s.grid.team1_rows, int)
    assert isinstance(s.mode_map.modes, dict)
    assert "final_round" in s.mode_map.modes
