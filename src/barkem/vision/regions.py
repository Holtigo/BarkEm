"""
Screen region definitions for all supported resolutions.

Every coordinate region used by BarkEm is defined here. When setting up for the
first time, you need to capture the correct pixel coordinates from your game at
your resolution and fill them into config/settings.yaml under the 'regions' key.

Region format: (x1, y1, x2, y2) — top-left to bottom-right bounding box.
Click target format: (x, y) — single point to click.

PLAYER MOVEMENT WORKFLOW (Move in Lobby):
  1. Click on a player in the unassigned list → context menu opens
  2. Context menu shows the player's name (clean text, no surrounding clutter — great for OCR)
  3. Click "Move in Lobby" button in the context menu
     - Button position differs: bot (self) has fewer options than other players
  4. UI enters placement mode — click a specific slot in Team 1, Team 2, or Spectator
  5. Player is moved to that slot

DROPDOWN SELECTORS (Mode, Map, Variant, Condition, Gameshow):
  Mode and map selectors are scrollable dropdowns. The options listed in the YAML
  are their positions AFTER scrolling to the correct spot. Scrolling logic is
  handled in the bot code, not in this region map.

HOW TO FIND COORDINATES:
  1. Run: python -m barkem.tools.calibrate
  2. Hover your mouse over the corners of each UI element
  3. The coordinates are displayed in the window title
  4. Left-click for click targets, right-click twice for regions
  5. Paste them into config/settings.yaml
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ClickTarget:
    """A single (x, y) point to click."""
    x: int
    y: int

    def as_tuple(self) -> tuple[int, int]:
        return (self.x, self.y)


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
        return (
            self.x1 + self.width // 2,
            self.y1 + self.height // 2,
        )



_ZERO_CLICK = lambda: ClickTarget(0, 0)
_ZERO_REGION = lambda: Region(0, 0, 0, 0)



@dataclass
class MenuRegions:
    """Click targets for main menu → private match navigation."""
    play_button: ClickTarget = field(default_factory=_ZERO_CLICK)
    private_match_tile: ClickTarget = field(default_factory=_ZERO_CLICK)
    private_match_enter_button: ClickTarget = field(default_factory=_ZERO_CLICK)
    create_game_button: ClickTarget = field(default_factory=_ZERO_CLICK)



@dataclass
class ModeMapRegions:
    """
    Click targets for match configuration dropdowns.

    IMPORTANT: Mode and map are scrollable dropdowns. The positions below
    are where each option appears when scrolled into view. Scrolling to
    reach the correct item is handled by the bot's navigation logic.

    Selection is instant — no confirm button needed. Clicking an option
    immediately applies it.
    """
    # Dropdown openers
    mode_selector: ClickTarget = field(default_factory=_ZERO_CLICK)
    map_selector: ClickTarget = field(default_factory=_ZERO_CLICK)
    variant_selector: ClickTarget = field(default_factory=_ZERO_CLICK)
    condition_selector: ClickTarget = field(default_factory=_ZERO_CLICK)
    gameshow_selector: ClickTarget = field(default_factory=_ZERO_CLICK)

    # ── Mode positions (when mode dropdown is open) ──
    mode_final_round: ClickTarget = field(default_factory=_ZERO_CLICK)
    mode_cashout: ClickTarget = field(default_factory=_ZERO_CLICK)
    mode_quick_cash: ClickTarget = field(default_factory=_ZERO_CLICK)
    mode_head2head: ClickTarget = field(default_factory=_ZERO_CLICK)
    mode_team_deathmatch: ClickTarget = field(default_factory=_ZERO_CLICK)
    mode_power_shift: ClickTarget = field(default_factory=_ZERO_CLICK)
    mode_point_break: ClickTarget = field(default_factory=_ZERO_CLICK)

    # ── Map positions (when map dropdown is open) ──
    map_monaco: ClickTarget = field(default_factory=_ZERO_CLICK)
    map_seoul: ClickTarget = field(default_factory=_ZERO_CLICK)
    map_skyway_stadium: ClickTarget = field(default_factory=_ZERO_CLICK)
    map_las_vegas: ClickTarget = field(default_factory=_ZERO_CLICK)
    map_las_vegas_stadium: ClickTarget = field(default_factory=_ZERO_CLICK)
    map_nozomi_citadel: ClickTarget = field(default_factory=_ZERO_CLICK)
    map_sys_horizon: ClickTarget = field(default_factory=_ZERO_CLICK)
    map_kyoto: ClickTarget = field(default_factory=_ZERO_CLICK)
    map_fortune_stadium: ClickTarget = field(default_factory=_ZERO_CLICK)
    map_bernal: ClickTarget = field(default_factory=_ZERO_CLICK)
    map_fangwai_city: ClickTarget = field(default_factory=_ZERO_CLICK)



@dataclass
class ContextMenuRegions:
    """
    Regions for the player context menu that appears when you click a player.

    The context menu shows:
      - The player's name (clean text, no surrounding clutter — great for OCR)
      - "Move in Lobby" button (plus other options)

    The "Move in Lobby" button is at a DIFFERENT position depending on whether
    you clicked the bot (self) or another player, because other players have
    additional options (e.g., kick, report) that push "Move in Lobby" down.
    """
    # OCR region for the player name displayed in the popup
    # This is the same position every time regardless of which player
    player_name: Region = field(default_factory=_ZERO_REGION)

    # "Move in Lobby" button when clicking on the BOT itself (fewer menu items)
    move_in_lobby_self: ClickTarget = field(default_factory=_ZERO_CLICK)

    # "Move in Lobby" button when clicking on ANOTHER player (more menu items)
    move_in_lobby_other: ClickTarget = field(default_factory=_ZERO_CLICK)



@dataclass
class LobbyRegions:
    """
    Regions and click targets within the lobby screen.

    Player movement uses the "Move in Lobby" context menu approach:
      1. Click player in unassigned list → opens context menu
      2. Read name from context menu for verification
      3. Click "Move in Lobby" → enters placement mode
      4. Click destination slot (team or spectator)
    """

    # ── OCR Regions (bounding boxes for text reading) ──

    # The 4-character lobby code displayed after creating a match
    lobby_code: Region = field(default_factory=_ZERO_REGION)

    # Team 1 player name slots
    team1_player1_name: Region = field(default_factory=_ZERO_REGION)
    team1_player2_name: Region = field(default_factory=_ZERO_REGION)
    team1_player3_name: Region = field(default_factory=_ZERO_REGION)

    # Team 2 player name slots
    team2_player1_name: Region = field(default_factory=_ZERO_REGION)
    team2_player2_name: Region = field(default_factory=_ZERO_REGION)
    team2_player3_name: Region = field(default_factory=_ZERO_REGION)

    # Unassigned player pool (center area)
    # Up to 10 slots for players who joined but aren't on a team yet
    unassigned_player1_name: Region = field(default_factory=_ZERO_REGION)
    unassigned_player2_name: Region = field(default_factory=_ZERO_REGION)
    unassigned_player3_name: Region = field(default_factory=_ZERO_REGION)
    unassigned_player4_name: Region = field(default_factory=_ZERO_REGION)
    unassigned_player5_name: Region = field(default_factory=_ZERO_REGION)
    unassigned_player6_name: Region = field(default_factory=_ZERO_REGION)
    unassigned_player7_name: Region = field(default_factory=_ZERO_REGION)
    unassigned_player8_name: Region = field(default_factory=_ZERO_REGION)
    unassigned_player9_name: Region = field(default_factory=_ZERO_REGION)
    unassigned_player10_name: Region = field(default_factory=_ZERO_REGION)

    # Spectator name slots
    spectator1_name: Region = field(default_factory=_ZERO_REGION)
    spectator2_name: Region = field(default_factory=_ZERO_REGION)
    spectator3_name: Region = field(default_factory=_ZERO_REGION)

    # ── Click Targets: Unassigned Player Slots ──
    # Click on a player here to open their context menu
    unassigned_slot1_click: ClickTarget = field(default_factory=_ZERO_CLICK)
    unassigned_slot2_click: ClickTarget = field(default_factory=_ZERO_CLICK)
    unassigned_slot3_click: ClickTarget = field(default_factory=_ZERO_CLICK)
    unassigned_slot4_click: ClickTarget = field(default_factory=_ZERO_CLICK)
    unassigned_slot5_click: ClickTarget = field(default_factory=_ZERO_CLICK)
    unassigned_slot6_click: ClickTarget = field(default_factory=_ZERO_CLICK)
    unassigned_slot7_click: ClickTarget = field(default_factory=_ZERO_CLICK)
    unassigned_slot8_click: ClickTarget = field(default_factory=_ZERO_CLICK)
    unassigned_slot9_click: ClickTarget = field(default_factory=_ZERO_CLICK)
    unassigned_slot10_click: ClickTarget = field(default_factory=_ZERO_CLICK)

    # ── Click Targets: Team Slot Destinations ──
    # After clicking "Move in Lobby", click one of these to place the player
    team1_slot1_click: ClickTarget = field(default_factory=_ZERO_CLICK)
    team1_slot2_click: ClickTarget = field(default_factory=_ZERO_CLICK)
    team1_slot3_click: ClickTarget = field(default_factory=_ZERO_CLICK)
    team2_slot1_click: ClickTarget = field(default_factory=_ZERO_CLICK)
    team2_slot2_click: ClickTarget = field(default_factory=_ZERO_CLICK)
    team2_slot3_click: ClickTarget = field(default_factory=_ZERO_CLICK)

    # ── Click Targets: Spectator Slot Destinations ──
    # Where to place the bot (or a player) into spectator
    spectator_slot1_click: ClickTarget = field(default_factory=_ZERO_CLICK)
    spectator_slot2_click: ClickTarget = field(default_factory=_ZERO_CLICK)
    spectator_slot3_click: ClickTarget = field(default_factory=_ZERO_CLICK)

    # ── Lobby Buttons ──
    start_match_button: ClickTarget = field(default_factory=_ZERO_CLICK)



@dataclass
class ChatRegions:
    """Region for in-game chat reading."""
    chat_area: Region = field(default_factory=_ZERO_REGION)



@dataclass
class ScoreboardRegions:
    """Regions for reading the end-of-match scoreboard."""

    team1_score: Region = field(default_factory=_ZERO_REGION)
    team2_score: Region = field(default_factory=_ZERO_REGION)

    # Individual player scores — Team 1
    team1_player1_score_name: Region = field(default_factory=_ZERO_REGION)
    team1_player1_score_value: Region = field(default_factory=_ZERO_REGION)
    team1_player2_score_name: Region = field(default_factory=_ZERO_REGION)
    team1_player2_score_value: Region = field(default_factory=_ZERO_REGION)
    team1_player3_score_name: Region = field(default_factory=_ZERO_REGION)
    team1_player3_score_value: Region = field(default_factory=_ZERO_REGION)

    # Individual player scores — Team 2
    team2_player1_score_name: Region = field(default_factory=_ZERO_REGION)
    team2_player1_score_value: Region = field(default_factory=_ZERO_REGION)
    team2_player2_score_name: Region = field(default_factory=_ZERO_REGION)
    team2_player2_score_value: Region = field(default_factory=_ZERO_REGION)
    team2_player3_score_name: Region = field(default_factory=_ZERO_REGION)
    team2_player3_score_value: Region = field(default_factory=_ZERO_REGION)

    return_to_lobby_button: ClickTarget = field(default_factory=_ZERO_CLICK)


@dataclass
class MatchRegions:
    """Regions used during an active match."""
    pause_indicator: Region = field(default_factory=_ZERO_REGION)


@dataclass
class ScreenRegions:
    """
    All screen regions for a specific resolution.

    Every pixel coordinate the bot needs is defined here.
    Fill these in via config/settings.yaml under the 'regions' key.
    """
    menu: MenuRegions = field(default_factory=MenuRegions)
    mode_map: ModeMapRegions = field(default_factory=ModeMapRegions)
    context_menu: ContextMenuRegions = field(default_factory=ContextMenuRegions)
    lobby: LobbyRegions = field(default_factory=LobbyRegions)
    chat: ChatRegions = field(default_factory=ChatRegions)
    scoreboard: ScoreboardRegions = field(default_factory=ScoreboardRegions)
    match: MatchRegions = field(default_factory=MatchRegions)


def load_regions_from_dict(data: dict) -> ScreenRegions:
    """
    Load ScreenRegions from a nested dictionary (e.g., from YAML config).

    Dynamically sets attributes based on matching field names.
    [x, y] values become ClickTarget, [x1, y1, x2, y2] become Region.
    """
    regions = ScreenRegions()

    if not data:
        return regions

    # Walk each group and set matching attributes
    group_map = {
        "menu": regions.menu,
        "mode_map": regions.mode_map,
        "context_menu": regions.context_menu,
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

            if isinstance(val, list):
                if len(val) == 2:
                    setattr(group_obj, key, ClickTarget(val[0], val[1]))
                elif len(val) == 4:
                    setattr(group_obj, key, Region(val[0], val[1], val[2], val[3]))

    return regions