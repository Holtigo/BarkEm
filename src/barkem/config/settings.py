"""
Settings management using Pydantic.
"""

from functools import lru_cache
from pathlib import Path
from typing import Any, Literal
import os

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class GameSettings(BaseModel):
    resolution: str = "1920x1080"
    display_mode: Literal["borderless", "windowed", "fullscreen"] = "borderless"
    window_title: str = "THE FINALS"
    bot_embark_id: str = "BarkEmBot#0746"


class VisionSettings(BaseModel):
    capture_fps: int = 10
    template_threshold: float = 0.85
    ocr_upscale_factor: int = 3
    debug_screenshots: bool = True
    screenshot_dir: str = "./debug/screenshots"
    tesseract_cmd: str = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


class InputSettings(BaseModel):
    """XInput controller timing settings."""

    button_delay: float = 0.15
    hold_duration: float = 0.05
    anchor_presses: int = 5
    anchor_settle: float = 0.3
    transition_wait: float = 0.5
    step_wait: float = 0.3


class SequenceSettings(BaseModel):
    """Menu navigation config."""

    # Game mode selection screen — cursor starts at top on entry, so
    # just DOWN×N to reach Private Match.
    mode_down_to_private: int = 7

    # Private Match screen → Create Game
    private_to_create: list[str] = Field(default_factory=lambda: ["a"])

    # Inside lobby — start match
    lobby_start_match: list[str] = Field(default_factory=lambda: ["start"])


class GridSettings(BaseModel):
    """
    Lobby grid config for 3-column D-pad navigation.

    LEFT column  = match detail dropdowns (Game Mode, Arena, …)
    CENTER column = unassigned players + spectators (anchor lands here)
    RIGHT column  = Team 1 + Team 2 slots
    """

    # Teams column (RIGHT)
    team1_rows: int = 3
    team2_rows: int = 3
    gap_between_teams: int = 0

    # Context menu — "Move in Lobby" is at a different row depending
    # on whether you clicked the bot (fewer options) or another player.
    context_move_self: int = 1   # D-pad Downs for bot's own context menu
    context_move_other: int = 2  # D-pad Downs for other players

    # Dropdown anchoring — UP presses to guarantee the cursor is at
    # index 0 inside an open dropdown (mode, map, variant, etc.).
    dropdown_anchor_up: int = 14


class ModeMapIndexSettings(BaseModel):
    """
    Zero-based dropdown indices for modes and maps.

    After opening the dropdown, press D-pad Down this many times to
    reach the desired option, then press A.
    """

    modes: dict[str, int] = Field(default_factory=lambda: {
        "final_round": 0,
        "cashout": 1,
        "quick_cash": 2,
        "head2head": 3,
        "team_deathmatch": 4,
        "power_shift": 5,
        "point_break": 6,
    })
    maps: dict[str, int] = Field(default_factory=lambda: {
        "monaco": 0,
        "seoul": 1,
        "skyway_stadium": 2,
        "las_vegas": 3,
        "las_vegas_stadium": 4,
        "nozomi_citadel": 5,
        "sys_horizon": 6,
        "kyoto": 7,
        "fortune_stadium": 8,
        "bernal": 9,
        "fangwai_city": 10,
    })


class TimingSettings(BaseModel):
    default_cancel_timeout: int = 300
    match_max_duration: int = 1200
    state_transition_timeout: int = 10
    countdown_seconds: int = 3
    pause_cooldown: float = 30.0


class PauseSettings(BaseModel):
    """
    Default limits for in-match pauses.  Per-match overrides can come
    from the API request's ``config`` block.
    """

    # How long a single pause is allowed to last before auto-unpause.
    max_duration_s: float = 300.0
    # How many pauses each team may request across the full match.
    max_pauses_per_team: int = 2
    # How long between a team's pauses (prevents spam).  Matches the
    # old TimingSettings.pause_cooldown but scoped here.
    cooldown_s: float = 30.0


class MonitoringSettings(BaseModel):
    initial_poll_interval: int = 60
    mid_poll_interval: int = 30
    late_poll_interval: int = 10
    late_threshold_seconds: int = 600
    chat_poll_interval: float = 1.0

    # Phase 4 — ready watching
    # How many captains must type "-em ready" before the bot presses X.
    # 2 = production (both teams agree).  1 = testing with a single real
    # account.  Can be overridden per-run via the CLI --min-ready flag.
    min_ready_captains: int = 2
    # Command chat fades after ~8s in-game.  Polling at 1s is safe; 2s
    # still catches anything as long as the captain types once.
    ready_timeout_seconds: int = 300

    # Phase 5 — in-match monitoring
    # In-match chat isn't persistent on-screen — the bot has to hold
    # the Menu button to open it, OCR, then close with B.  We do this
    # at a slower cadence than lobby chat.
    pause_poll_interval: float = 5.0
    # How long to hold the Menu button to open chat (tap = escape menu).
    menu_hold_duration: float = 0.8
    # Settle time after holding Menu before OCR.
    chat_open_settle: float = 0.4
    # Seconds between SUMMARY detection and pressing A to skip it.
    # The screen auto-advances after ~20s regardless, so a short wait
    # lets any transitions finish rendering before we send A.
    summary_skip_delay: float = 1.0
    # How long to wait for the scoreboard after SUMMARY was skipped
    # before giving up and OCR'ing whatever is on screen.
    summary_to_scoreboard_timeout: float = 10.0
    # Unpause countdown (also used as pause-announce countdown).
    pause_countdown_seconds: int = 3
    unpause_countdown_seconds: int = 5
    # Wait between priming keystroke and real chat message.  On GeForce
    # NOW the chat widget needs time to take keyboard focus after the
    # gamepad→keyboard handoff; keystrokes sent into that gap are
    # dropped.  Bump this if you still see mangled message prefixes.
    keyboard_warmup: float = 0.6
    # Wait between finishing a chat message and the next gamepad press
    # (D-pad Left for pause toggle).  Cloud streaming has to swap input
    # modes back to gamepad — a button press into that gap is eaten.
    gamepad_recovery: float = 0.4


class APISettings(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8080
    webhook_timeout: int = 30
    webhook_retries: int = 3


class LoggingSettings(BaseModel):
    level: str = "INFO"
    file: str = "./logs/bot.log"
    rotation: str = "10 MB"
    retention: str = "30 days"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="BARKEM_",
        env_nested_delimiter="__",
    )

    game: GameSettings = Field(default_factory=GameSettings)
    vision: VisionSettings = Field(default_factory=VisionSettings)
    input: InputSettings = Field(default_factory=InputSettings)
    sequences: SequenceSettings = Field(default_factory=SequenceSettings)
    grid: GridSettings = Field(default_factory=GridSettings)
    mode_map: ModeMapIndexSettings = Field(default_factory=ModeMapIndexSettings)
    timing: TimingSettings = Field(default_factory=TimingSettings)
    pause: PauseSettings = Field(default_factory=PauseSettings)
    monitoring: MonitoringSettings = Field(default_factory=MonitoringSettings)
    api: APISettings = Field(default_factory=APISettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)

    # OCR regions — raw dict from YAML, parsed by vision/regions.py
    regions: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_yaml(cls, path: str = "config/settings.yaml") -> "Settings":
        if not os.path.exists(path):
            raise FileNotFoundError(f"Settings file not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return cls(**data)


@lru_cache
def get_settings() -> Settings:
    config_path = Path("config/settings.yaml")
    if config_path.exists():
        return Settings.from_yaml(config_path)
    return Settings()
