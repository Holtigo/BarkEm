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
    """
    Regions for in-game chat reading.

    The chat window has different on-screen coordinates in the lobby
    vs during a live match (smaller + centred in-match), so both are
    stored separately.  ``chat_area`` is the lobby chat; the in-match
    version lives at ``in_match_chat_area``.
    """

    chat_area: Region = field(default_factory=_ZERO)
    in_match_chat_area: Region = field(default_factory=_ZERO)


# ── Scoreboard ────────────────────────────────────────────────────────────

# Per-player stat columns rendered in the final scoreboard (left→right,
# after the class glyph + name).  All six player rows share the same
# x-coordinates, so calibration only needs one [x1, x2] span per column.
#
# Note: "coins" (self-revive charges) is only visible during the
# live match — the post-match spectator scoreboard omits it, so it's
# not in this list.
SCOREBOARD_STAT_COLUMNS: tuple[str, ...] = (
    "elims",
    "assists",
    "deaths",
    "revives",
    "damage",
    "support",
    "objective",
)


@dataclass
class ColumnX:
    """Horizontal span [x1, x2] shared across all 6 player rows."""

    x1: int = 0
    x2: int = 0

    @property
    def is_zero(self) -> bool:
        return self.x1 == 0 and self.x2 == 0


@dataclass
class RowY:
    """Vertical span [y1, y2] for one player row."""

    y1: int = 0
    y2: int = 0

    @property
    def is_zero(self) -> bool:
        return self.y1 == 0 and self.y2 == 0


@dataclass
class ScoreboardRegions:
    """
    OCR regions for the end-of-match scoreboard.

    Layout is row-anchored + column-offset: calibration captures a
    y-span for each of the 6 player rows (3 per team) and an x-span
    for each column (class, name, elims, …).  The reader crosses them
    to produce per-cell bounding boxes, so there are ~16 small inputs
    instead of 60+ flat `(player, stat)` regions.
    """

    # Team money totals (already calibrated before Phase 6).
    team1_score: Region = field(default_factory=_ZERO)
    team2_score: Region = field(default_factory=_ZERO)

    # Per-row y-spans — team1 on top, team2 below.  Always 3 rows each.
    team1_rows: list[RowY] = field(default_factory=lambda: [RowY(), RowY(), RowY()])
    team2_rows: list[RowY] = field(default_factory=lambda: [RowY(), RowY(), RowY()])

    # Per-column x-spans.  ``class_`` is the L/M/H glyph column,
    # ``name`` is the Embark ID column, the rest are the stat columns
    # in SCOREBOARD_STAT_COLUMNS order.
    col_class: ColumnX = field(default_factory=ColumnX)
    col_name: ColumnX = field(default_factory=ColumnX)
    col_elims: ColumnX = field(default_factory=ColumnX)
    col_assists: ColumnX = field(default_factory=ColumnX)
    col_deaths: ColumnX = field(default_factory=ColumnX)
    col_revives: ColumnX = field(default_factory=ColumnX)
    col_damage: ColumnX = field(default_factory=ColumnX)
    col_support: ColumnX = field(default_factory=ColumnX)
    col_objective: ColumnX = field(default_factory=ColumnX)

    def row(self, team: int, idx: int) -> RowY:
        """Return the RowY for team (1 or 2), 0-based row index (0..2)."""
        rows = self.team1_rows if team == 1 else self.team2_rows
        return rows[idx]

    def column(self, name: str) -> ColumnX:
        """Return the ColumnX for a column name ('class', 'name', 'elims', …)."""
        attr = "col_class" if name == "class" else f"col_{name}"
        return getattr(self, attr)

    def cell(self, team: int, row_idx: int, col_name: str) -> Region:
        """Cross a row and column into a single cell Region."""
        r = self.row(team, row_idx)
        c = self.column(col_name)
        if r.is_zero or c.is_zero:
            return Region(0, 0, 0, 0)
        return Region(c.x1, r.y1, c.x2, r.y2)


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

    Standard groups (context_menu, dropdowns, lobby, chat, match):
      Lists of length 4 → Region(x1, y1, x2, y2).

    Scoreboard has a richer shape — see :func:`_load_scoreboard`.
    Unknown keys and malformed values are silently ignored.
    """
    regions = ScreenRegions()
    if not data:
        return regions

    group_map = {
        "context_menu": regions.context_menu,
        "dropdowns": regions.dropdowns,
        "lobby": regions.lobby,
        "chat": regions.chat,
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

    _load_scoreboard(regions.scoreboard, data.get("scoreboard", {}) or {})
    return regions


def _load_scoreboard(sb: ScoreboardRegions, data: dict) -> None:
    """Populate ScoreboardRegions from the YAML ``scoreboard:`` block."""
    for team_field in ("team1_score", "team2_score"):
        val = data.get(team_field)
        if isinstance(val, list) and len(val) == 4:
            setattr(sb, team_field, Region(val[0], val[1], val[2], val[3]))

    for team_idx, key in ((1, "team1_rows"), (2, "team2_rows")):
        raw = data.get(key)
        if not isinstance(raw, list):
            continue
        rows = [RowY(r[0], r[1]) for r in raw if isinstance(r, list) and len(r) == 2]
        while len(rows) < 3:
            rows.append(RowY())
        target = sb.team1_rows if team_idx == 1 else sb.team2_rows
        target[:] = rows[:3]

    cols = data.get("columns") or {}
    for col_name in ("class", "name", *SCOREBOARD_STAT_COLUMNS):
        val = cols.get(col_name)
        if not (isinstance(val, list) and len(val) == 2):
            continue
        attr = "col_class" if col_name == "class" else f"col_{col_name}"
        setattr(sb, attr, ColumnX(val[0], val[1]))
