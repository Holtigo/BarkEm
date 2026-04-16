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

    # Game mode selection screen — anchorable
    mode_anchor_up: int = 7        # UP presses to guarantee top of list
    mode_down_to_private: int = 7  # DOWN presses from top to Private Match

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


class MonitoringSettings(BaseModel):
    initial_poll_interval: int = 60
    mid_poll_interval: int = 30
    late_poll_interval: int = 10
    late_threshold_seconds: int = 600
    chat_poll_interval: float = 1.0


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
