"""
Screen region definitions for OCR and template matching.

Every bounding-box region the bot's *vision* system needs is defined
here.  Navigation targets (button sequences, grid indices) live in
``input.navigator`` and ``config/settings.yaml`` under ``input:``.

Region format: (x1, y1, x2, y2) — top-left to bottom-right bounding box.

HOW TO FIND COORDINATES:
  1. Run: python -m barkem.tools.calibrate
  2. Hover your mouse over the corners of each UI element
  3. Left-click for point coordinates, right-click twice for regions
  4. Paste them into config/settings.yaml under ``regions:``
"""

from dataclasses import dataclass, field


@dataclass
class Region:
    """A bounding box region (x1, y1, x2, y2)."""

    x1: int
    y1: int
    x2: int
    y2: int

    def as_tuple(self) -> tuple[int, int, int, int]:
        return (self.x1, self.y1, self.x2, self.y2)

    @property
    def width(self) -> int:
        return self.x2 - self.x1

    @property
    def height(self) -> int:
        return self.y2 - self.y1

    @property
    def center(self) -> tuple[int, int]:
        return (self.x1 + self.width // 2, self.y1 + self.height // 2)

    @property
    def is_zero(self) -> bool:
        return self.x1 == 0 and self.y1 == 0 and self.x2 == 0 and self.y2 == 0


_ZERO = lambda: Region(0, 0, 0, 0)


# ── Context menu ──────────────────────────────────────────────────────────

@dataclass
class ContextMenuRegions:
    """
    OCR region for the player context menu popup.

    The player name displayed in the popup is always in the same screen
    position regardless of which player was selected — good for OCR
    verification before placement.
    """

    player_name: Region = field(default_factory=_ZERO)


# ── Dropdowns (match details column) ──────────────────────────────────────

@dataclass
class DropdownRegions:
    """
    OCR regions for the *currently displayed value* of each dropdown
    in the LEFT (match details) column.  Used to verify a dropdown
    actually applied the selection (GeForce NOW lag can drop inputs).
    """

    game_mode: Region = field(default_factory=_ZERO)
    arena: Region = field(default_factory=_ZERO)
    variant: Region = field(default_factory=_ZERO)
    condition: Region = field(default_factory=_ZERO)
    game_show: Region = field(default_factory=_ZERO)


# ── Lobby ─────────────────────────────────────────────────────────────────

@dataclass
class LobbyRegions:
    """
    OCR regions for reading names in the lobby.

    Navigation / placement is handled by ``LobbyNavigator`` using
    D-pad grid indices — no click targets needed here.
    """

    # The 4-character lobby code
    lobby_code: Region = field(default_factory=_ZERO)

    # Team 1 player name slots
    team1_player1_name: Region = field(default_factory=_ZERO)
    team1_player2_name: Region = field(default_factory=_ZERO)
    team1_player3_name: Region = field(default_factory=_ZERO)

    # Team 2 player name slots
    team2_player1_name: Region = field(default_factory=_ZERO)
    team2_player2_name: Region = field(default_factory=_ZERO)
    team2_player3_name: Region = field(default_factory=_ZERO)

    # Unassigned player pool (up to 10)
    unassigned_player1_name: Region = field(default_factory=_ZERO)
    unassigned_player2_name: Region = field(default_factory=_ZERO)
    unassigned_player3_name: Region = field(default_factory=_ZERO)
    unassigned_player4_name: Region = field(default_factory=_ZERO)
    unassigned_player5_name: Region = field(default_factory=_ZERO)
    unassigned_player6_name: Region = field(default_factory=_ZERO)
    unassigned_player7_name: Region = field(default_factory=_ZERO)
    unassigned_player8_name: Region = field(default_factory=_ZERO)
    unassigned_player9_name: Region = field(default_factory=_ZERO)
    unassigned_player10_name: Region = field(default_factory=_ZERO)

    # Spectator name slots
    spectator1_name: Region = field(default_factory=_ZERO)
    spectator2_name: Region = field(default_factory=_ZERO)
    spectator3_name: Region = field(default_factory=_ZERO)

    # ── Named iterators (used by highlight detection, OCR, etc.) ──
    def unassigned_slots(self) -> list[tuple[str, Region]]:
        """Return (name, region) pairs for every defined unassigned slot."""
        out = []
        for i in range(1, 11):
            r = getattr(self, f"unassigned_player{i}_name")
            if not r.is_zero:
                out.append((f"unassigned{i}", r))
        return out

    def spectator_slots(self) -> list[tuple[str, Region]]:
        out = []
        for i in range(1, 4):
            r = getattr(self, f"spectator{i}_name")
            if not r.is_zero:
                out.append((f"spectator{i}", r))
        return out

    def team_slots(self) -> list[tuple[str, Region]]:
        out = []
        for team in (1, 2):
            for i in range(1, 4):
                r = getattr(self, f"team{team}_player{i}_name")
                if not r.is_zero:
                    out.append((f"team{team}_player{i}", r))
        return out

    def all_player_slots(self) -> list[tuple[str, Region]]:
        """All lobby slots a D-pad cursor can land on (for highlight detection)."""
        return self.unassigned_slots() + self.spectator_slots() + self.team_slots()


# ── Chat ──────────────────────────────────────────────────────────────────

@dataclass
class ChatRegions:
    """Region for in-game chat reading."""

    chat_area: Region = field(default_factory=_ZERO)


# ── Scoreboard ────────────────────────────────────────────────────────────

@dataclass
class ScoreboardRegions:
    """OCR regions for end-of-match scoreboard."""

    team1_score: Region = field(default_factory=_ZERO)
    team2_score: Region = field(default_factory=_ZERO)

    team1_player1_score_name: Region = field(default_factory=_ZERO)
    team1_player1_score_value: Region = field(default_factory=_ZERO)
    team1_player2_score_name: Region = field(default_factory=_ZERO)
    team1_player2_score_value: Region = field(default_factory=_ZERO)
    team1_player3_score_name: Region = field(default_factory=_ZERO)
    team1_player3_score_value: Region = field(default_factory=_ZERO)

    team2_player1_score_name: Region = field(default_factory=_ZERO)
    team2_player1_score_value: Region = field(default_factory=_ZERO)
    team2_player2_score_name: Region = field(default_factory=_ZERO)
    team2_player2_score_value: Region = field(default_factory=_ZERO)
    team2_player3_score_name: Region = field(default_factory=_ZERO)
    team2_player3_score_value: Region = field(default_factory=_ZERO)


# ── Match ─────────────────────────────────────────────────────────────────

@dataclass
class MatchRegions:
    """Regions used during an active match."""

    pause_indicator: Region = field(default_factory=_ZERO)


# ── Root container ────────────────────────────────────────────────────────

@dataclass
class ScreenRegions:
    """All OCR regions for a specific resolution."""

    context_menu: ContextMenuRegions = field(default_factory=ContextMenuRegions)
    dropdowns: DropdownRegions = field(default_factory=DropdownRegions)
    lobby: LobbyRegions = field(default_factory=LobbyRegions)
    chat: ChatRegions = field(default_factory=ChatRegions)
    scoreboard: ScoreboardRegions = field(default_factory=ScoreboardRegions)
    match: MatchRegions = field(default_factory=MatchRegions)


def load_regions_from_dict(data: dict) -> ScreenRegions:
    """
    Load ScreenRegions from a nested dict (e.g. from YAML config).

    Lists of length 4 → Region(x1, y1, x2, y2).
    Other values are silently ignored.
    """
    regions = ScreenRegions()
    if not data:
        return regions

    group_map = {
        "context_menu": regions.context_menu,
        "dropdowns": regions.dropdowns,
        "lobby": regions.lobby,
        "chat": regions.chat,
        "scoreboard": regions.scoreboard,
        "match": regions.match,
    }

    for group_name, group_obj in group_map.items():
        group_data = data.get(group_name, {})
        if not group_data:
            continue

        for key, val in group_data.items():
            if not val or not hasattr(group_obj, key):
                continue
            if isinstance(val, list) and len(val) == 4:
                setattr(group_obj, key, Region(val[0], val[1], val[2], val[3]))

    return regions
