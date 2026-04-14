"""
Settings management using Pydantic.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class GameSettings(BaseModel):
    """Game-related settings."""

    resolution: str = "1920x1080"
    display_mode: Literal["borderless", "windowed", "fullscreen"] = "borderless"
    window_title: str = "THE FINALS"


class VisionSettings(BaseModel):
    """Computer vision settings."""

    capture_fps: int = 10
    template_threshold: float = 0.85
    ocr_upscale_factor: int = 3
    debug_screenshots: bool = True
    screenshot_dir: str = "./debug/screenshots"


class InputSettings(BaseModel):
    """Input simulation settings."""

    click_delay_min: float = 0.1
    click_delay_max: float = 0.3
    drag_duration_min: float = 0.2
    drag_duration_max: float = 0.4
    typing_interval: float = 0.1
    humanize_movement: bool = True


class TimingSettings(BaseModel):
    """Timing and timeout settings."""

    party_invite_timeout: int = 30
    player_join_timeout: int = 120
    match_max_duration: int = 1200
    state_transition_timeout: int = 10


class MonitoringSettings(BaseModel):
    """Match monitoring settings."""

    initial_poll_interval: int = 60
    mid_poll_interval: int = 30
    late_poll_interval: int = 10
    late_threshold_seconds: int = 600


class APISettings(BaseModel):
    """API server settings."""

    host: str = "0.0.0.0"
    port: int = 8080
    webhook_timeout: int = 30
    webhook_retries: int = 3


class RedisSettings(BaseModel):
    """Redis connection settings."""

    host: str = "localhost"
    port: int = 6379
    channel_prefix: str = "barkem"

    @property
    def url(self) -> str:
        return f"redis://{self.host}:{self.port}"


class LoggingSettings(BaseModel):
    """Logging settings."""

    level: str = "INFO"
    file: str = "./logs/bot.log"
    rotation: str = "10 MB"
    retention: str = "30 days"


class Settings(BaseSettings):
    """Main application settings."""

    model_config = SettingsConfigDict(
        env_prefix="BARKEM_",
        env_nested_delimiter="__",
    )

    game: GameSettings = Field(default_factory=GameSettings)
    vision: VisionSettings = Field(default_factory=VisionSettings)
    input: InputSettings = Field(default_factory=InputSettings)
    timing: TimingSettings = Field(default_factory=TimingSettings)
    monitoring: MonitoringSettings = Field(default_factory=MonitoringSettings)
    api: APISettings = Field(default_factory=APISettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)

    @classmethod
    def from_yaml(cls, path: str | Path) -> "Settings":
        """Load settings from YAML file."""
        path = Path(path)
        if not path.exists():
            return cls()

        with open(path) as f:
            data = yaml.safe_load(f) or {}

        return cls(**data)


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    config_path = Path("config/settings.yaml")
    if config_path.exists():
        return Settings.from_yaml(config_path)
    return Settings()
