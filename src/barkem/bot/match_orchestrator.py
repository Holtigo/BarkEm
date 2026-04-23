"""
Phase 7 — End-to-end match orchestrator.

Sequences the full flow from a ``POST /api/v1/match/start`` request:

  1. Focus the game window (``WindowManager.focus``).
  2. Create the private-match lobby (``LobbyCreator``) and OCR the code.
  3. Wait for every expected Embark ID to appear unassigned
     (``RosterWaiter``) — replaces the manual "press Enter" gate from
     the Phase 2+3 tools.
  4. Place players onto teams (``TeamPlacer``).
  5. Poll chat for ``-em ready`` from captains and press X
     (``MatchStarter``).
  6. Drive the live match until the scoreboard is captured
     (``MatchMonitor``): sparse end detection + pause handling.
  7. Build a webhook payload from the scoreboard + pauses and POST it.

The orchestrator owns exactly one shared gamepad/keyboard/capture
stack for the whole run.  Previously each Phase-N tool built its own
stack via a local ``_build`` helper; the orchestrator consolidates
those builders so the API path doesn't rebuild a VGamepad every time
a phase transitions.

Two ``ChatReader`` instances are kept distinct:
  * ``chat_lobby``  — ``regions.chat.chat_area``
  * ``chat_match``  — ``regions.chat.in_match_chat_area``

swapping is cheap (``set_region``), but constructing both upfront is
clearer than a mid-run swap and matches how the test tools run.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from barkem.api.schemas import (
    MatchModeConfig,
    PauseOverrides,
    StartMatchRequest,
    Team,
)
from barkem.bot.lobby import LobbyCreator
from barkem.bot.match_monitor import MatchMonitor, MatchMonitorConfig, MatchMonitorResult
from barkem.bot.match_starter import MatchStarter
from barkem.bot.pause_handler import PauseHandler, PauseLimits
from barkem.bot.placement import PlacementResult, TeamPlacer
from barkem.bot.roster_waiter import RosterWaiter
from barkem.bot.scoreboard_reader import ScoreboardReader
from barkem.config import Settings, get_settings
from barkem.input.controller import GamepadConfig, GamepadController
from barkem.input.keyboard import KeyboardConfig, KeyboardController
from barkem.input.navigator import (
    LobbyGrid,
    LobbyNavigator,
    MenuNavigator,
    MenuSequences,
)
from barkem.input.window import WindowManager
from barkem.logging import get_logger
from barkem.vision.capture import ScreenCapture
from barkem.vision.chat import ChatReader
from barkem.vision.lobby_reader import LobbyReader
from barkem.vision.ocr import TextReader
from barkem.vision.regions import ScreenRegions, load_regions_from_dict
from barkem.vision.state_detector import GameStateDetector
from barkem.vision.templates import TemplateMatcher


log = get_logger("orchestrator")


class OrchestratorPhase(str, Enum):
    """Granular phase label for the status endpoint."""

    IDLE = "idle"
    FOCUSING_WINDOW = "focusing_window"
    CREATING_LOBBY = "creating_lobby"
    WAITING_FOR_PLAYERS = "waiting_for_players"
    PLACING_TEAMS = "placing_teams"
    WAITING_FOR_READY = "waiting_for_ready"
    MONITORING_MATCH = "monitoring_match"
    CAPTURING_SCORE = "capturing_score"
    DELIVERING_RESULTS = "delivering_results"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ERROR = "error"


@dataclass
class OrchestratorRuntime:
    """All the built-once stack components.  One per orchestrator instance."""

    pad: GamepadController
    kb: KeyboardController
    cap: ScreenCapture
    ocr: TextReader
    regions: ScreenRegions
    detector: GameStateDetector
    window: WindowManager
    lobby_creator: LobbyCreator
    placer: TeamPlacer
    roster_waiter: RosterWaiter
    chat_lobby: ChatReader
    chat_match: ChatReader
    scoreboard_reader: ScoreboardReader


@dataclass
class MatchRun:
    """Live state of a single match — what the status endpoint reads."""

    match_id: str
    config: MatchModeConfig
    teams: list[Team]
    webhook_url: Optional[str]
    metadata: dict

    phase: OrchestratorPhase = OrchestratorPhase.IDLE
    lobby_code: Optional[str] = None
    players_joined: int = 0
    players_expected: int = 0
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    error: Optional[str] = None

    # Internal cancel-request flag.  Checked between phases; the
    # MatchMonitor loop has its own ``abort()`` method that trips at
    # the next poll.
    _cancel_requested: bool = False

    # Resolved per-match policy (request overrides + settings fallback)
    cancel_timeout_s: float = 300.0
    ready_timeout_s: float = 300.0
    min_ready_captains: int = 2
    max_match_duration_s: float = 1200.0
    pause_limits: PauseLimits = field(default_factory=PauseLimits)

    # Collected outcomes — written by the orchestrator as phases complete
    placement_result: Optional[PlacementResult] = None
    monitor_result: Optional[MatchMonitorResult] = None


# ── Public builder ──────────────────────────────────────────────────


def build_runtime(settings: Optional[Settings] = None) -> OrchestratorRuntime:
    """Construct the full input/vision stack — one-time per process."""
    settings = settings or get_settings()
    icfg = settings.input

    pad = GamepadController(
        config=GamepadConfig(
            button_delay=icfg.button_delay,
            hold_duration=icfg.hold_duration,
            anchor_presses=icfg.anchor_presses,
            anchor_settle=icfg.anchor_settle,
        )
    )
    pad.connect()

    kb = KeyboardController(config=KeyboardConfig())
    kb.connect()

    cap = ScreenCapture(target_fps=settings.vision.capture_fps)
    cap.start()

    ocr = TextReader(
        upscale_factor=settings.vision.ocr_upscale_factor,
        tesseract_cmd=settings.vision.tesseract_cmd,
    )
    regions = load_regions_from_dict(settings.regions)
    matcher = TemplateMatcher(threshold=settings.vision.template_threshold)
    detector = GameStateDetector(threshold=settings.vision.template_threshold)
    window = WindowManager(window_title=settings.game.window_title)

    menu_nav = MenuNavigator(
        controller=pad,
        capture=cap,
        matcher=matcher,
        sequences=MenuSequences(
            mode_down_to_private=settings.sequences.mode_down_to_private,
            private_to_create=settings.sequences.private_to_create,
        ),
        transition_wait=icfg.transition_wait,
    )
    lobby_nav = LobbyNavigator(
        controller=pad,
        grid=LobbyGrid(
            team1_rows=settings.grid.team1_rows,
            team2_rows=settings.grid.team2_rows,
            gap_between_teams=settings.grid.gap_between_teams,
            context_move_self=settings.grid.context_move_self,
            context_move_other=settings.grid.context_move_other,
            dropdown_anchor_up=settings.grid.dropdown_anchor_up,
        ),
        step_wait=icfg.step_wait,
    )
    lobby_reader = LobbyReader(
        ocr=ocr,
        lobby=regions.lobby,
        context_menu=regions.context_menu,
    )
    lobby_creator = LobbyCreator(
        menu_nav=menu_nav,
        lobby_nav=lobby_nav,
        capture=cap,
        text_reader=ocr,
        regions=regions,
        state_detector=detector,
        mode_indices=settings.mode_map.modes,
        map_indices=settings.mode_map.maps,
        window_manager=window,
    )
    placer = TeamPlacer(
        lobby_nav=lobby_nav,
        lobby_reader=lobby_reader,
        capture=cap,
        bot_embark_id=settings.game.bot_embark_id,
        step_wait=icfg.step_wait,
    )
    roster_waiter = RosterWaiter(
        lobby_reader=lobby_reader,
        capture=cap,
    )
    chat_lobby = ChatReader(
        chat_region=regions.chat.chat_area.as_tuple(),
        text_reader=ocr,
    )
    in_match_region = regions.chat.in_match_chat_area
    if in_match_region.is_zero:
        log.warning(
            "regions.chat.in_match_chat_area is zero — falling back to lobby chat "
            "region for in-match reads.  Pause detection will be unreliable."
        )
        in_match_region = regions.chat.chat_area
    chat_match = ChatReader(
        chat_region=in_match_region.as_tuple(),
        text_reader=ocr,
    )
    scoreboard_reader = ScoreboardReader(ocr=ocr, regions=regions.scoreboard)

    return OrchestratorRuntime(
        pad=pad,
        kb=kb,
        cap=cap,
        ocr=ocr,
        regions=regions,
        detector=detector,
        window=window,
        lobby_creator=lobby_creator,
        placer=placer,
        roster_waiter=roster_waiter,
        chat_lobby=chat_lobby,
        chat_match=chat_match,
        scoreboard_reader=scoreboard_reader,
    )


def shutdown_runtime(runtime: OrchestratorRuntime) -> None:
    """Release all hardware resources held by the runtime."""
    try:
        runtime.pad.disconnect()
    except Exception as exc:
        log.warning("gamepad disconnect failed: {}", exc)
    try:
        runtime.kb.disconnect()
    except Exception as exc:
        log.warning("keyboard disconnect failed: {}", exc)
    try:
        runtime.cap.stop()
    except Exception as exc:
        log.warning("capture stop failed: {}", exc)


# ── Orchestrator ────────────────────────────────────────────────────


class MatchOrchestrator:
    """Drives one match end-to-end.  Re-usable across consecutive matches."""

    def __init__(self, runtime: OrchestratorRuntime, settings: Optional[Settings] = None):
        self.rt = runtime
        self.settings = settings or get_settings()
        self._current: Optional[MatchRun] = None
        self._monitor: Optional[MatchMonitor] = None

    # ── Public API ──────────────────────────────────────────────────

    @property
    def current(self) -> Optional[MatchRun]:
        return self._current

    def is_busy(self) -> bool:
        run = self._current
        if run is None:
            return False
        return run.phase not in (
            OrchestratorPhase.IDLE,
            OrchestratorPhase.COMPLETED,
            OrchestratorPhase.CANCELLED,
            OrchestratorPhase.ERROR,
        )

    def request_cancel(self) -> bool:
        """Flag the current run for cancellation.  Returns False if nothing to cancel."""
        run = self._current
        if run is None or not self.is_busy():
            return False
        run._cancel_requested = True
        if self._monitor is not None:
            self._monitor.abort()
        log.info("cancel requested for match {}", run.match_id)
        return True

    async def prepare_match(self, request: StartMatchRequest) -> MatchRun:
        """Phases 1–2 only.  Returns the MatchRun with a lobby code attached.

        This is what the ``POST /match/start`` handler awaits synchronously —
        the response body needs the lobby code.  The rest of the pipeline
        runs via ``run_remaining_phases()`` in a background task.
        """
        if self.is_busy():
            raise RuntimeError("Orchestrator is busy — only one match at a time.")

        run = self._new_run(request)
        self._current = run
        run.started_at = time.time()

        try:
            await self._focus_window(run)
            await self._create_lobby(run)
        except Exception as exc:
            run.phase = OrchestratorPhase.ERROR
            run.error = str(exc)
            log.exception("match {} aborted during preparation: {}", run.match_id, exc)
            raise

        return run

    async def run_remaining_phases(self) -> None:
        """Phases 3–7.  Must be awaited after ``prepare_match`` returns."""
        run = self._current
        if run is None:
            return
        try:
            await self._wait_for_roster(run)
            if await self._check_cancel_async(run):
                return

            await self._place_teams(run)
            if await self._check_cancel_async(run):
                return

            await self._wait_ready_and_start(run)
            if await self._check_cancel_async(run):
                return

            await self._monitor_match(run)
            if await self._check_cancel_async(run):
                return

            await self._deliver_results(run)
            run.phase = OrchestratorPhase.COMPLETED
            run.completed_at = time.time()
            log.info("match {} complete", run.match_id)

        except Exception as exc:
            run.phase = OrchestratorPhase.ERROR
            run.error = str(exc)
            run.completed_at = time.time()
            log.exception("match {} failed: {}", run.match_id, exc)
            await self._deliver_error(run, status="error")

    # ── Individual phase handlers ───────────────────────────────────

    async def _focus_window(self, run: MatchRun) -> None:
        run.phase = OrchestratorPhase.FOCUSING_WINDOW
        log.info("[match {}] focusing game window", run.match_id)
        ok = await asyncio.to_thread(self.rt.window.focus)
        if not ok:
            raise RuntimeError(
                f"Could not focus game window matching "
                f"{self.rt.window.window_title!r}"
            )

    async def _create_lobby(self, run: MatchRun) -> None:
        run.phase = OrchestratorPhase.CREATING_LOBBY
        log.info(
            "[match {}] creating lobby  mode={!r}  map={!r}",
            run.match_id, run.config.mode, run.config.map,
        )
        result = await asyncio.to_thread(
            self.rt.lobby_creator.create_and_read_code,
            run.config.mode,
            run.config.map,
        )
        if not result.success or not result.lobby_code:
            raise RuntimeError(f"Lobby creation failed: {result.error}")
        run.lobby_code = result.lobby_code
        log.info("[match {}] lobby code = {}", run.match_id, run.lobby_code)

    async def _wait_for_roster(self, run: MatchRun) -> None:
        run.phase = OrchestratorPhase.WAITING_FOR_PLAYERS
        expected = self._expected_embark_ids(run.teams)
        run.players_expected = len(expected)
        log.info(
            "[match {}] waiting for {} players (timeout {:.0f}s)",
            run.match_id, len(expected), run.cancel_timeout_s,
        )

        def _progress(matched: list[str], missing: list[str]) -> None:
            run.players_joined = len(matched)
            log.debug(
                "[match {}] roster poll — {}/{} joined.  missing={}",
                run.match_id, len(matched), len(expected), missing,
            )

        result = await asyncio.to_thread(
            self.rt.roster_waiter.wait,
            expected,
            run.cancel_timeout_s,
            _progress,
        )
        run.players_joined = len(result.matched)
        if not result.ready:
            raise RuntimeError(
                result.error or
                f"Timed out waiting for players — missing {result.missing}"
            )

    async def _place_teams(self, run: MatchRun) -> None:
        run.phase = OrchestratorPhase.PLACING_TEAMS
        team1 = [p.embark_id for p in self._team(run, 1).players]
        team2 = [p.embark_id for p in self._team(run, 2).players]
        log.info(
            "[match {}] placing teams — team1={} team2={}",
            run.match_id, team1, team2,
        )
        result: PlacementResult = await asyncio.to_thread(
            self.rt.placer.place_teams,
            team1,
            team2,
            True,   # verify_after
            True,   # spectate_bot
        )
        run.placement_result = result
        if not result.success:
            raise RuntimeError(f"Team placement failed: {result.error}")
        if result.verify_mismatches:
            log.warning(
                "[match {}] placement mismatches (proceeding anyway): {}",
                run.match_id, result.verify_mismatches,
            )

    async def _wait_ready_and_start(self, run: MatchRun) -> None:
        run.phase = OrchestratorPhase.WAITING_FOR_READY
        captain1 = self._team(run, 1).captain.embark_id
        captain2 = self._team(run, 2).captain.embark_id
        starter = MatchStarter(
            gamepad=self.rt.pad,
            capture=self.rt.cap,
            chat_reader=self.rt.chat_lobby,
            captain1=captain1,
            captain2=captain2,
            min_ready_captains=run.min_ready_captains,
            poll_interval=self.settings.monitoring.chat_poll_interval,
        )
        log.info(
            "[match {}] waiting for {} captain(s) to ready (timeout {:.0f}s)",
            run.match_id, run.min_ready_captains, run.ready_timeout_s,
        )
        result = await asyncio.to_thread(
            starter.wait_and_start,
            run.ready_timeout_s,
            False,   # dry_run
        )
        if not result.success or not result.started:
            raise RuntimeError(
                result.error or "MatchStarter did not press X — unknown failure"
            )

    async def _monitor_match(self, run: MatchRun) -> None:
        run.phase = OrchestratorPhase.MONITORING_MATCH
        captains = {
            "team1": self._team(run, 1).captain.embark_id,
            "team2": self._team(run, 2).captain.embark_id,
        }
        mon_settings = self.settings.monitoring

        pause_handler = PauseHandler(
            gamepad=self.rt.pad,
            keyboard=self.rt.kb,
            capture=self.rt.cap,
            chat_reader=self.rt.chat_match,
            limits=run.pause_limits,
            menu_hold_duration=mon_settings.menu_hold_duration,
            chat_open_settle=mon_settings.chat_open_settle,
            keyboard_warmup=mon_settings.keyboard_warmup,
            gamepad_recovery=mon_settings.gamepad_recovery,
            pause_countdown=mon_settings.pause_countdown_seconds,
            unpause_countdown=mon_settings.unpause_countdown_seconds,
            poll_interval=mon_settings.pause_poll_interval,
        )
        monitor_cfg = MatchMonitorConfig(
            pause_poll_interval=mon_settings.pause_poll_interval,
            early_poll_interval=float(mon_settings.initial_poll_interval),
            mid_poll_interval=float(mon_settings.mid_poll_interval),
            late_poll_interval=float(mon_settings.late_poll_interval),
            late_threshold_s=float(mon_settings.late_threshold_seconds),
            menu_hold_duration=mon_settings.menu_hold_duration,
            chat_open_settle=mon_settings.chat_open_settle,
            summary_skip_delay=mon_settings.summary_skip_delay,
            summary_to_scoreboard_timeout=mon_settings.summary_to_scoreboard_timeout,
            max_match_duration_s=run.max_match_duration_s,
        )
        monitor = MatchMonitor(
            gamepad=self.rt.pad,
            capture=self.rt.cap,
            state_detector=self.rt.detector,
            chat_reader=self.rt.chat_match,
            pause_handler=pause_handler,
            scoreboard_reader=self.rt.scoreboard_reader,
            captains=captains,
            config=monitor_cfg,
        )
        self._monitor = monitor
        log.info("[match {}] starting in-match monitor", run.match_id)
        try:
            result = await asyncio.to_thread(monitor.run)
        finally:
            self._monitor = None
        run.monitor_result = result
        if result.timed_out:
            raise RuntimeError(
                f"Match exceeded max_match_duration_s ({run.max_match_duration_s}s)"
            )
        if result.error and not (result.scoreboard and result.scoreboard.ok):
            raise RuntimeError(result.error)

    async def _deliver_results(self, run: MatchRun) -> None:
        run.phase = OrchestratorPhase.DELIVERING_RESULTS
        monitor_result = run.monitor_result
        if monitor_result is None or monitor_result.scoreboard is None:
            raise RuntimeError("No scoreboard captured — nothing to deliver")

        from barkem.api import webhook
        from barkem.bot.results_builder import build_completed_payload

        duration = (
            (run.completed_at or time.time()) - (run.started_at or time.time())
        )
        payload = build_completed_payload(
            match_id=run.match_id,
            config=run.config,
            teams=run.teams,
            scoreboard=monitor_result.scoreboard,
            pauses=monitor_result.pause_outcomes,
            duration_seconds=duration,
            metadata=run.metadata,
        )
        await webhook.deliver(run.webhook_url, payload)

    async def _deliver_error(self, run: MatchRun, status: str) -> None:
        """Fire a webhook for a cancelled / errored match.  Best-effort."""
        from barkem.api import webhook
        from barkem.bot.results_builder import build_error_payload

        duration = (
            (run.completed_at or time.time()) - (run.started_at or time.time())
        )
        pauses = (
            run.monitor_result.pause_outcomes if run.monitor_result else []
        )
        payload = build_error_payload(
            match_id=run.match_id,
            config=run.config,
            duration_seconds=duration,
            error=run.error or "unknown",
            status=status,
            metadata=run.metadata,
            pauses=pauses,
        )
        await webhook.deliver(run.webhook_url, payload)

    # ── Internals ───────────────────────────────────────────────────

    def _new_run(self, request: StartMatchRequest) -> MatchRun:
        run = MatchRun(
            match_id=request.match_id,
            config=request.config,
            teams=list(request.teams),
            webhook_url=request.webhook_url,
            metadata=dict(request.metadata),
        )
        self._apply_policy(run, request)
        return run

    def _apply_policy(self, run: MatchRun, request: StartMatchRequest) -> None:
        """Resolve request overrides against settings defaults."""
        s = self.settings
        run.cancel_timeout_s = float(
            request.cancel_timeout_seconds or s.timing.default_cancel_timeout
        )
        run.ready_timeout_s = float(
            request.ready_timeout_seconds or s.monitoring.ready_timeout_seconds
        )
        run.min_ready_captains = int(
            request.min_ready_captains or s.monitoring.min_ready_captains
        )
        run.max_match_duration_s = float(
            request.max_match_duration_s or s.timing.match_max_duration
        )
        run.pause_limits = self._resolve_pause_limits(request.pause)

    def _resolve_pause_limits(self, overrides: Optional[PauseOverrides]) -> PauseLimits:
        s = self.settings.pause
        if overrides is None:
            return PauseLimits(
                max_duration_s=s.max_duration_s,
                max_pauses_per_team=s.max_pauses_per_team,
                cooldown_s=s.cooldown_s,
            )
        return PauseLimits(
            max_duration_s=overrides.max_duration_s
                if overrides.max_duration_s is not None else s.max_duration_s,
            max_pauses_per_team=overrides.max_pauses_per_team
                if overrides.max_pauses_per_team is not None else s.max_pauses_per_team,
            cooldown_s=overrides.cooldown_s
                if overrides.cooldown_s is not None else s.cooldown_s,
        )

    def _expected_embark_ids(self, teams: list[Team]) -> list[str]:
        ids: list[str] = []
        for team in teams:
            ids.extend(p.embark_id for p in team.players)
        return ids

    def _team(self, run: MatchRun, team_id: int) -> Team:
        for t in run.teams:
            if t.team_id == team_id:
                return t
        raise ValueError(f"No team with team_id={team_id}")

    async def _check_cancel_async(self, run: MatchRun) -> bool:
        """If a cancel was requested, finalise the run and return True."""
        if not run._cancel_requested:
            return False
        run.phase = OrchestratorPhase.CANCELLED
        run.completed_at = time.time()
        run.error = run.error or "cancelled by user"
        log.info("[match {}] cancelled", run.match_id)
        await self._deliver_error(run, status="cancelled")
        return True
