"""
Child bot state machine.
"""

from enum import Enum, auto
from typing import Optional

from statemachine import State, StateMachine

from barkem.config import get_settings


class ChildState(Enum):
    """States for the child bot."""

    IDLE = auto()
    INVITING_TEAM2 = auto()
    WAITING_FOR_CODE = auto()
    JOINING_LOBBY = auto()
    SIGNALING_JOINED = auto()
    WAITING_FOR_RELEASE = auto()
    LEAVING_LOBBY = auto()
    ERROR_RECOVERY = auto()


class ChildStateMachine(StateMachine):
    """State machine for the child bot."""

    # States
    idle = State(initial=True)
    inviting_team2 = State()
    waiting_for_code = State()
    joining_lobby = State()
    signaling_joined = State()
    waiting_for_release = State()
    leaving_lobby = State()
    error_recovery = State()

    # Transitions
    receive_team2_assignment = idle.to(inviting_team2)
    team2_in_party = inviting_team2.to(waiting_for_code)
    code_received = waiting_for_code.to(joining_lobby)
    joined_lobby = joining_lobby.to(signaling_joined)
    orchestrator_acknowledged = signaling_joined.to(waiting_for_release)
    teams_placed_signal = waiting_for_release.to(leaving_lobby)
    left_lobby = leaving_lobby.to(idle)

    # Error handling
    timeout = (
        inviting_team2.to(error_recovery)
        | waiting_for_code.to(error_recovery)
        | joining_lobby.to(error_recovery)
    )
    recovered = error_recovery.to(idle)


class ChildBot:
    """
    Child bot that handles Team 2 party management.

    Responsibilities:
    - Receive Team 2 player list from orchestrator
    - Invite Team 2 players to party
    - Wait for lobby code from orchestrator
    - Enter lobby code (party auto-joins)
    - Signal orchestrator when joined
    - Wait for teams placed signal
    - Leave lobby and return to idle
    """

    def __init__(self):
        self.settings = get_settings()
        self.state_machine = ChildStateMachine()
        self.current_assignment: Optional[dict] = None

    async def receive_assignment(self, team2_players: list[dict], orchestrator_id: str) -> None:
        """
        Receive a new team assignment.

        Args:
            team2_players: List of Team 2 player data.
            orchestrator_id: ID of the orchestrator for communication.
        """
        self.current_assignment = {
            "players": team2_players,
            "orchestrator_id": orchestrator_id,
        }
        self.state_machine.receive_team2_assignment()
        # TODO: Implement assignment flow

    async def run(self) -> None:
        """Main bot loop."""
        # TODO: Implement main loop
        pass
