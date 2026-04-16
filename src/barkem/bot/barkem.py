"""
BarkEm bot — Main state machine for private match automation.
"""

import asyncio
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

from statemachine import State, StateMachine

from barkem.config import get_settings


class MatchStatus(Enum):
    PENDING = "pending"
    LOBBY_CREATED = "lobby_created"
    WAITING_FOR_PLAYERS = "waiting_for_players"
    TEAMS_PLACED = "teams_placed"
    WAITING_FOR_READY = "waiting_for_ready"
    IN_PROGRESS = "in_progress"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ERROR = "error"


@dataclass
class MatchConfig:
    match_id: str
    mode: str
    map: str
    variant: str = "default"
    best_of: int = 1
    cancel_timeout_seconds: int = 300
    webhook_url: Optional[str] = None
    metadata: dict = field(default_factory=dict)


@dataclass
class TeamInfo:
    team_id: int
    name: str
    players: list[dict]

    @property
    def captain(self) -> dict:
        return self.players[0] if self.players else {}

    @property
    def captain_embark_id(self) -> str:
        return self.captain.get("embark_id", "")


@dataclass
class MatchState:
    config: MatchConfig
    team1: TeamInfo
    team2: TeamInfo
    lobby_code: Optional[str] = None
    status: MatchStatus = MatchStatus.PENDING
    team1_ready: bool = False
    team2_ready: bool = False
    is_paused: bool = False
    pause_count: int = 0
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    results: Optional[dict] = None


class BarkEmStateMachine(StateMachine):
    """State machine for the BarkEm bot."""

    # States
    idle = State(initial=True)
    creating_lobby = State()
    waiting_for_players = State()
    placing_teams = State()
    waiting_for_ready = State()
    countdown_start = State()
    starting_match = State()
    monitoring_match = State()
    pausing_match = State()
    match_paused = State()
    countdown_unpause = State()
    unpausing_match = State()
    capturing_score = State()
    returning_results = State()
    reconfiguring = State()
    match_cancelled = State()

    # Main flow
    receive_match_request = idle.to(creating_lobby)
    lobby_created = creating_lobby.to(waiting_for_players)
    players_joined = waiting_for_players.to(placing_teams)
    teams_placed = placing_teams.to(waiting_for_ready)
    both_captains_ready = waiting_for_ready.to(countdown_start)
    countdown_complete = countdown_start.to(starting_match)
    match_started = starting_match.to(monitoring_match)
    match_ended = monitoring_match.to(capturing_score)
    score_captured = capturing_score.to(returning_results)
    series_complete = returning_results.to(idle)
    next_match = returning_results.to(reconfiguring)
    reconfigured = reconfiguring.to(waiting_for_players)

    # Pause flow
    pause_requested = monitoring_match.to(pausing_match)
    paused = pausing_match.to(match_paused)
    unpause_requested = match_paused.to(countdown_unpause)
    unpause_countdown_complete = countdown_unpause.to(unpausing_match)
    unpaused = unpausing_match.to(monitoring_match)

    # Timeout / cancel
    cancel_timeout = (
        waiting_for_players.to(match_cancelled)
        | placing_teams.to(match_cancelled)
        | waiting_for_ready.to(match_cancelled)
    )
    cancelled_acknowledged = match_cancelled.to(idle)


class BarkEmBot:
    """
    Main bot class that orchestrates private match creation and monitoring.

    Uses GamepadController + MenuNavigator + LobbyNavigator for all input.
    """

    def __init__(self):
        self.settings = get_settings()
        self.state_machine = BarkEmStateMachine()
        self.current_match: Optional[MatchState] = None
        self._cancel_timeout_task: Optional[asyncio.Task] = None

        # Input — initialised lazily in run()
        self._gamepad = None
        self._menu_nav = None
        self._lobby_nav = None
        self._lobby_creator = None

    def _init_input(self):
        """Create controller, vision, and navigators from settings."""
        from barkem.input.controller import GamepadController, GamepadConfig
        from barkem.input.navigator import (
            MenuNavigator, MenuSequences,
            LobbyNavigator, LobbyGrid,
        )
        from barkem.vision.capture import ScreenCapture
        from barkem.vision.templates import TemplateMatcher
        from barkem.vision.ocr import TextReader
        from barkem.vision.regions import load_regions_from_dict
        from barkem.vision.state_detector import GameStateDetector
        from barkem.bot.lobby import LobbyCreator
        from barkem.input.window import WindowManager

        cfg = self.settings.input
        pad_cfg = GamepadConfig(
            button_delay=cfg.button_delay,
            hold_duration=cfg.hold_duration,
            anchor_presses=cfg.anchor_presses,
            anchor_settle=cfg.anchor_settle,
        )
        self._gamepad = GamepadController(config=pad_cfg)
        self._gamepad.connect()

        # Vision — needed by MenuNavigator for main menu template matching
        self._capture = ScreenCapture(target_fps=self.settings.vision.capture_fps)
        self._capture.start()
        self._matcher = TemplateMatcher(
            threshold=self.settings.vision.template_threshold,
        )

        seq = self.settings.sequences
        self._menu_nav = MenuNavigator(
            controller=self._gamepad,
            capture=self._capture,
            matcher=self._matcher,
            sequences=MenuSequences(
                mode_anchor_up=seq.mode_anchor_up,
                mode_down_to_private=seq.mode_down_to_private,
                private_to_create=seq.private_to_create,
            ),
            transition_wait=cfg.transition_wait,
        )

        grid = self.settings.grid
        self._lobby_nav = LobbyNavigator(
            controller=self._gamepad,
            grid=LobbyGrid(
                team1_rows=grid.team1_rows,
                team2_rows=grid.team2_rows,
                gap_between_teams=grid.gap_between_teams,
                context_move_self=grid.context_move_self,
                context_move_other=grid.context_move_other,
                dropdown_anchor_up=grid.dropdown_anchor_up,
            ),
            step_wait=cfg.step_wait,
        )

        # Phase 2 — vision pieces for lobby creation + code OCR
        self._text_reader = TextReader(
            upscale_factor=self.settings.vision.ocr_upscale_factor,
            tesseract_cmd=self.settings.vision.tesseract_cmd,
        )
        self._regions = load_regions_from_dict(self.settings.regions)
        self._detector = GameStateDetector(
            threshold=self.settings.vision.template_threshold,
        )
        self._window = WindowManager(window_title=self.settings.game.window_title)
        self._lobby_creator = LobbyCreator(
            menu_nav=self._menu_nav,
            lobby_nav=self._lobby_nav,
            capture=self._capture,
            text_reader=self._text_reader,
            regions=self._regions,
            state_detector=self._detector,
            mode_indices=self.settings.mode_map.modes,
            map_indices=self.settings.mode_map.maps,
            window_manager=self._window,
        )

    @property
    def captains(self) -> tuple[str, str]:
        if not self.current_match:
            return ("", "")
        return (
            self.current_match.team1.captain_embark_id,
            self.current_match.team2.captain_embark_id,
        )

    async def start_match(
        self,
        config: MatchConfig,
        team1: TeamInfo,
        team2: TeamInfo,
    ) -> str:
        self.current_match = MatchState(config=config, team1=team1, team2=team2)
        self.state_machine.receive_match_request()

        if self._lobby_creator is None:
            self._init_input()

        result = self._lobby_creator.create_and_read_code(
            mode=config.mode,
            map_name=config.map,
        )
        if not result.success:
            self.current_match.status = MatchStatus.ERROR
            raise RuntimeError(f"Lobby creation failed: {result.error}")

        self.current_match.lobby_code = result.lobby_code
        self.current_match.status = MatchStatus.LOBBY_CREATED
        self.state_machine.lobby_created()

        self._start_cancel_timeout(config.cancel_timeout_seconds)
        return result.lobby_code

    def _start_cancel_timeout(self, seconds: int) -> None:
        if self._cancel_timeout_task:
            self._cancel_timeout_task.cancel()

        async def timeout_handler():
            await asyncio.sleep(seconds)
            if self.state_machine.current_state in [
                self.state_machine.waiting_for_players,
                self.state_machine.placing_teams,
                self.state_machine.waiting_for_ready,
            ]:
                self.state_machine.cancel_timeout()
                if self.current_match:
                    self.current_match.status = MatchStatus.CANCELLED

        self._cancel_timeout_task = asyncio.create_task(timeout_handler())

    def check_ready(self, player_name: str) -> bool:
        if not self.current_match:
            return False
        captain1, captain2 = self.captains
        if self._names_match(player_name, captain1):
            self.current_match.team1_ready = True
        elif self._names_match(player_name, captain2):
            self.current_match.team2_ready = True
        return self.current_match.team1_ready and self.current_match.team2_ready

    def check_pause(self, player_name: str) -> bool:
        if not self.current_match:
            return False
        captain1, captain2 = self.captains
        return self._names_match(player_name, captain1) or self._names_match(
            player_name, captain2
        )

    def _names_match(self, ocr_name: str, expected_name: str) -> bool:
        # TODO: Use rapidfuzz
        return ocr_name.lower().strip() == expected_name.lower().strip()

    async def pause_match(self) -> None:
        """Pause via Start button."""
        if self._gamepad:
            self._gamepad.pause_toggle()

    async def unpause_match(self) -> None:
        """Unpause via Start button."""
        if self._gamepad:
            self._gamepad.pause_toggle()

    async def do_countdown(self, seconds: int = 3) -> None:
        for i in range(seconds, 0, -1):
            await asyncio.sleep(1)

    async def run(self) -> None:
        """Main bot loop."""
        self._init_input()
        # TODO: implement main loop
        pass

    async def cancel(self) -> None:
        if self._cancel_timeout_task:
            self._cancel_timeout_task.cancel()
        if self.current_match:
            self.current_match.status = MatchStatus.CANCELLED
        self.state_machine.cancel_timeout()

    def cleanup(self) -> None:
        """Disconnect the virtual gamepad."""
        if self._gamepad:
            self._gamepad.disconnect()
