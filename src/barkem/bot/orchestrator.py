"""
Orchestrator (parent) bot state machine.
"""

from enum import Enum, auto
from typing import Optional

from statemachine import State, StateMachine

from barkem.config import get_settings


class OrchestratorState(Enum):
    """States for the orchestrator bot."""

    IDLE = auto()
    INVITING_TEAM1 = auto()
    CREATING_LOBBY = auto()
    SIGNALING_CHILD = auto()
    WAITING_FOR_PLAYERS = auto()
    PLACING_TEAMS = auto()
    SIGNAL_CHILD_OK = auto()
    STARTING_MATCH = auto()
    MONITORING_MATCH = auto()
    CAPTURING_SCORE = auto()
    RETURNING_RESULTS = auto()
    RECONFIGURING = auto()
    ERROR_RECOVERY = auto()


class OrchestratorStateMachine(StateMachine):
    """State machine for the orchestrator bot."""

    # States
    idle = State(initial=True)
    inviting_team1 = State()
    creating_lobby = State()
    signaling_child = State()
    waiting_for_players = State()
    placing_teams = State()
    signal_child_ok = State()
    starting_match = State()
    monitoring_match = State()
    capturing_score = State()
    returning_results = State()
    reconfiguring = State()
    error_recovery = State()

    # Transitions
    receive_match_request = idle.to(inviting_team1)
    team1_in_party = inviting_team1.to(creating_lobby)
    lobby_created = creating_lobby.to(signaling_child)
    child_acknowledged = signaling_child.to(waiting_for_players)
    all_players_joined = waiting_for_players.to(placing_teams)
    teams_placed = placing_teams.to(signal_child_ok)
    child_left = signal_child_ok.to(starting_match)
    match_started = starting_match.to(monitoring_match)
    match_ended = monitoring_match.to(capturing_score)
    score_captured = capturing_score.to(returning_results)
    series_complete = returning_results.to(idle)
    next_match = returning_results.to(reconfiguring)
    reconfigured = reconfiguring.to(waiting_for_players)

    # Error handling
    timeout = (
        waiting_for_players.to(error_recovery)
        | placing_teams.to(error_recovery)
        | monitoring_match.to(error_recovery)
    )
    recovered = error_recovery.to(idle)


class OrchestratorBot:
    """
    Parent bot that orchestrates private match creation.

    Responsibilities:
    - Invite Team 1 players to party
    - Create private match lobby
    - Signal child bot with lobby code
    - Wait for all players to join
    - Drag players to correct teams
    - Start match and monitor for completion
    - Capture and return results
    """

    def __init__(self):
        self.settings = get_settings()
        self.state_machine = OrchestratorStateMachine()
        self.current_match: Optional[dict] = None

    async def start_match(self, match_config: dict) -> None:
        """
        Start processing a new match request.

        Args:
            match_config: Match configuration including teams and settings.
        """
        self.current_match = match_config
        self.state_machine.receive_match_request()
        # TODO: Implement match flow

    async def run(self) -> None:
        """Main bot loop."""
        # TODO: Implement main loop
        pass
