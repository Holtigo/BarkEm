"""
BarkEm bot - Main state machine for private match automation.
"""

import asyncio
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

from statemachine import State, StateMachine

from barkem.config import get_settings


class MatchStatus(Enum):
    """Status codes for match lifecycle."""

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
    """Configuration for a match."""

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
    """Information about a team."""

    team_id: int
    name: str
    players: list[dict]  # List of player dicts with embark_id, discord_id, etc.

    @property
    def captain(self) -> dict:
        """First player is the captain."""
        return self.players[0] if self.players else {}

    @property
    def captain_embark_id(self) -> str:
        """Get captain's Embark ID."""
        return self.captain.get("embark_id", "")


@dataclass
class MatchState:
    """Current state of a match."""

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
    """
    State machine for the BarkEm bot.

    Flow:
    1. Receive match request → Create lobby
    2. Return lobby code → Players join manually
    3. Place players on correct teams
    4. Wait for both captains to say "ready" in chat
    5. Countdown → Start match
    6. Monitor match (sparse polling) + watch chat for "pause"/"unpause"
    7. On match end → Capture scoreboard → Return results
    """

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

    # Main flow transitions
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

    # Timeout/cancel
    cancel_timeout = (
        waiting_for_players.to(match_cancelled)
        | placing_teams.to(match_cancelled)
        | waiting_for_ready.to(match_cancelled)
    )
    cancelled_acknowledged = match_cancelled.to(idle)


class BarkEmBot:
    """
    Main bot class that orchestrates private match creation and monitoring.

    Responsibilities:
    - Create private match lobby
    - Return lobby code via API
    - Wait for players to join manually
    - Drag players to correct teams
    - Monitor chat for captain "ready" commands
    - Start match after countdown
    - Monitor for pause/unpause during match
    - Capture and return results
    """

    def __init__(self):
        self.settings = get_settings()
        self.state_machine = BarkEmStateMachine()
        self.current_match: Optional[MatchState] = None
        self._cancel_timeout_task: Optional[asyncio.Task] = None

    @property
    def captains(self) -> tuple[str, str]:
        """Get captain Embark IDs for current match."""
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
        """
        Start processing a new match request.

        Args:
            config: Match configuration.
            team1: Team 1 info (first player = captain).
            team2: Team 2 info (first player = captain).

        Returns:
            Lobby code once created.
        """
        self.current_match = MatchState(
            config=config,
            team1=team1,
            team2=team2,
        )

        # Trigger state transition
        self.state_machine.receive_match_request()

        # TODO: Implement lobby creation
        # - Navigate to private match
        # - Select mode, map, variant
        # - Create lobby
        # - OCR lobby code

        lobby_code = "XXXX"  # Placeholder
        self.current_match.lobby_code = lobby_code
        self.current_match.status = MatchStatus.LOBBY_CREATED

        self.state_machine.lobby_created()

        # In PLACING_TEAMS state implementation (future):

        async def place_teams(self):
            """Place all players on correct teams."""

            # STEP 1: Move bot to spectator FIRST
            bot_id = self.settings.game.bot_embark_id
            await self._drag_player_to_spectator(bot_id)

            # STEP 2: Then move players to their teams
            for player in self.current_match.team1.players:
                await self._drag_player_to_team(player["embark_id"], team=1)

            for player in self.current_match.team2.players:
                await self._drag_player_to_team(player["embark_id"], team=2)
        # Start cancel timeout
        self._start_cancel_timeout(config.cancel_timeout_seconds)

        return lobby_code

    def _start_cancel_timeout(self, seconds: int) -> None:
        """Start the cancel timeout timer."""
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
                # TODO: Send webhook notification

        self._cancel_timeout_task = asyncio.create_task(timeout_handler())

    def check_ready(self, player_name: str) -> bool:
        """
        Process a "ready" command from a player.

        Args:
            player_name: Embark ID of player who said ready.

        Returns:
            True if both teams are now ready.
        """
        if not self.current_match:
            return False

        captain1, captain2 = self.captains

        # Fuzzy match would happen here
        if self._names_match(player_name, captain1):
            self.current_match.team1_ready = True
        elif self._names_match(player_name, captain2):
            self.current_match.team2_ready = True

        return self.current_match.team1_ready and self.current_match.team2_ready

    def check_pause(self, player_name: str) -> bool:
        """
        Check if a captain requested pause.

        Args:
            player_name: Embark ID of player who said pause.

        Returns:
            True if this is a valid pause request from a captain.
        """
        if not self.current_match:
            return False

        captain1, captain2 = self.captains
        return self._names_match(player_name, captain1) or self._names_match(
            player_name, captain2
        )

    def _names_match(self, ocr_name: str, expected_name: str) -> bool:
        """Fuzzy match two player names."""
        # TODO: Use rapidfuzz for fuzzy matching
        return ocr_name.lower().strip() == expected_name.lower().strip()

    async def do_countdown(self, seconds: int = 3) -> None:
        """
        Perform a countdown before starting/unpausing.

        Args:
            seconds: Number of seconds to count down.
        """
        for i in range(seconds, 0, -1):
            # TODO: Optionally send to webhook
            await asyncio.sleep(1)

    async def pause_match(self) -> None:
        """Pause the match by pressing P key."""
        # TODO: Implement via InputController
        # pydirectinput.press('p')
        pass

    async def unpause_match(self) -> None:
        """Unpause the match by pressing P key."""
        # TODO: Implement via InputController
        # pydirectinput.press('p')
        pass

    async def run(self) -> None:
        """Main bot loop."""
        # TODO: Implement main loop
        # - Poll for state-specific actions
        # - Check chat during WAITING_FOR_READY
        # - Monitor match during MONITORING_MATCH
        # - Handle pause/unpause
        pass

    async def cancel(self) -> None:
        """Cancel the current match."""
        if self._cancel_timeout_task:
            self._cancel_timeout_task.cancel()

        if self.current_match:
            self.current_match.status = MatchStatus.CANCELLED

        self.state_machine.cancel_timeout()
