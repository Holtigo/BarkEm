# BarkEm

🐕 **Private match automation for The Finals**

Stop manually creating lobbies. BarkEm handles lobby creation, team placement, match monitoring, and result capture so you can focus on running tournaments, not clicking menus. Built with virtual controller emulation for GeForce NOW cloud gaming compatibility.

## Features

- **Automated lobby creation** — Creates private matches with configured mode, map, and variant
- **Manual player join** — Returns lobby code via API, players join themselves
- **Team placement** — OCR identifies each joined player (with background-colour classification to tell empty `---` slots from real ones); players are moved via the Manage Lobby overlay + *Move in Lobby* shortcut
- **Captain ready system** — Match starts when both team captains type `-em ready` in game chat
- **Pause/unpause support** — Captains can type `-em pause` and `-em unpause` during matches
- **Match monitoring** — Sparse polling to detect match completion without resource waste
- **Result capture** — Screenshots scoreboard, extracts scores via OCR
- **Platform-agnostic API** — RESTful endpoints + webhooks for integration with any tournament system
- **Cross-platform** — Windows (vgamepad/ViGEmBus) and Linux (evdev/uinput) support

## Architecture

BarkEm uses a **single bot model** with **virtual controller emulation**:

1. Bot creates private match lobby via D-pad menu navigation
2. Returns lobby code via API → players join manually
3. Bot places players onto their teams through the **Manage Lobby (Y)** overlay: OCR identifies each joined player, the bot opens the context menu on each one, picks *Move in Lobby*, then presses the dedicated Team 1 / Team 2 / Spectator shortcut. The bot finally sends itself to spectator via its own RS shortcut.
4. Monitors chat for captain `-em ready` commands
5. Both captains ready → countdown → match starts
6. During match: monitors for `-em pause` / `-em unpause`
7. Match ends → captures scoreboard → returns results via webhook

The bot uses computer vision (DXcam screen capture + template matching + OCR) and virtual gamepad input (XInput on Windows, uinput on Linux). No memory reading, no code injection, no network interception — safe with Easy Anti-Cheat.

**Why controller input?** GeForce NOW virtualizes mouse input through a browser, causing severe coordinate desync. XInput bypasses this entirely — the cloud gaming client natively forwards virtual controller input to the VM, and The Finals' UI uses snap-to-grid selection for controllers, enabling deterministic D-pad navigation.

## Requirements

- **Windows 10/11** or **Linux** (Ubuntu 22+)
- Python 3.11+
- [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki)
- The Finals running in **Borderless Windowed** mode
- One game account for the bot

**Windows only:**
- [ViGEmBus driver](https://github.com/ViGEm/ViGEmBus/releases) (one-time install, admin required)

**Linux only:**
- Write access to `/dev/uinput` (`sudo chmod 666 /dev/uinput` or udev rule)

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/barkem.git
cd barkem

# Create virtual environment
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux

# Install dependencies (platform-specific deps auto-selected)
pip install -r requirements.txt

# Or install as editable package
pip install -e ".[dev]"

# Copy example config
copy config\settings.example.yaml config\settings.yaml
```

## Configuration

Edit `config/settings.yaml`:

```yaml
game:
  resolution: "1920x1080"
  window_title: "THE FINALS"
  bot_embark_id: "YourBotAccount#1234"

# Controller timing
input:
  button_delay: 0.15
  hold_duration: 0.05
  anchor_presses: 5

# Menu navigation
sequences:
  mode_down_to_private: 7

# Lobby grid (3-column layout)
grid:
  team1_rows: 3
  team2_rows: 3
  # DOWN presses from top of the context menu to "Move in Lobby".
  # Menu order: block / report / promote / kick / move-in-lobby → 4.
  context_move_other: 4
  dropdown_anchor_up: 14
```

See `config/settings.example.yaml` for the full configuration reference.

## Tools

```bash
# Keyboard → virtual gamepad emulator (test without physical controller)
python -m barkem.tools.keyboard_gamepad

# Interactive D-pad tester (count presses for calibration)
python -m barkem.tools.gamepad_test

# Interactive coordinate finder for OCR regions
python -m barkem.tools.calibrate

# Test OCR on all configured regions
python -m barkem.tools.calibrate --test-ocr

# Test game state detection via templates
python -m barkem.tools.calibrate --test-state

# Draw all configured regions on a screenshot
python -m barkem.tools.calibrate --draw-regions

# Continuously poll the detected game state (every 3s by default)
python -m barkem.tools.state_watch

# Phase 2 — end-to-end lobby creation test
python -m barkem.tools.create_lobby --mode final_round --map monaco
python -m barkem.tools.create_lobby --focus-only       # just verify window focus
python -m barkem.tools.create_lobby --nav-only         # just menu nav, no OCR
python -m barkem.tools.create_lobby --read-code-only   # OCR lobby code from current screen

# Phase 3 — read lobby state + place players onto teams
python -m barkem.tools.place_teams --snapshot          # OCR snapshot of current lobby
python -m barkem.tools.place_teams --dry-run \
    --team1 A#0001 B#0002 C#0003 \
    --team2 D#0004 E#0005 F#0006                       # plan preview, no input
python -m barkem.tools.place_teams \
    --team1 A#0001 --team2 B#0002                      # partial rosters OK

# Phase 2 + 3 combined — create lobby, wait for players, then place
python -m barkem.tools.create_and_place \
    --mode final_round --map monaco \
    --team1 A#0001 --team2 B#0002
python -m barkem.tools.create_and_place --skip-create \
    --team1 A#0001 --team2 B#0002                      # reuse existing lobby

# Phase 4 — captain ready detection + match start
python -m barkem.tools.ready_watch --captain1 A#0001   # live chat OCR + ready spotter
python -m barkem.tools.ready_watch --raw               # dump full chat OCR each tick

python -m barkem.tools.start_match --skip-ready        # press X immediately (no chat)
python -m barkem.tools.start_match --captain1 A#0001 \
    --min-ready 1                                      # solo-captain test: 1 ready → X
python -m barkem.tools.start_match \
    --captain1 A#0001 --captain2 B#0002 --min-ready 2  # production: both captains

# Full Phase 2 → 3 → 4 pipeline (create, place, wait-for-ready, start)
python -m barkem.tools.start_match --full \
    --mode final_round --map monaco \
    --team1 A#0001 --team2 B#0002 --min-ready 1

# Phase 5 — in-match monitor, pause handling
python -m barkem.tools.match_chat_watch --captain1 A#0001     # live in-match chat OCR
python -m barkem.tools.match_watch --captain1 A#0001 \
    --max-pause 120 --max-pauses-per-team 1                   # full monitor loop
python -m barkem.tools.match_watch --read-scoreboard          # one-shot scoreboard OCR
python -m barkem.tools.match_watch --skip-summary             # wait for SUMMARY, A-skip, OCR

# Phase 6 — full scoreboard capture (per-player statline)
python -m barkem.tools.calibrate --scoreboard                 # guided row/column wizard
python -m barkem.tools.scoreboard_read                        # OCR current scoreboard
python -m barkem.tools.scoreboard_read --raw                  # dump every cell's raw OCR
python -m barkem.tools.scoreboard_read --draw                 # draw every cell on a screenshot

# Live highlight (blue-glow cursor) debugger
python -m barkem.tools.highlight_watch
```

## Usage

### Start the API server

```bash
python -m barkem.api
```

### Create a match via API

```bash
curl -X POST http://localhost:8080/api/v1/match/start \
  -H "Content-Type: application/json" \
  -d '{
    "match_id": "test-001",
    "config": {
      "mode": "final_round",
      "map": "monaco",
      "variant": "default"
    },
    "cancel_timeout_seconds": 300,
    "teams": [
      {
        "team_id": 1,
        "players": [
          {"embark_id": "Player1#1234"},
          {"embark_id": "Player2#5678"},
          {"embark_id": "Player3#9012"}
        ]
      },
      {
        "team_id": 2,
        "players": [
          {"embark_id": "Player4#3456"},
          {"embark_id": "Player5#7890"},
          {"embark_id": "Player6#2345"}
        ]
      }
    ],
    "webhook_url": "https://your-service.com/results"
  }'
```

**Note:** The first player in each team is the **captain**. Only captains can trigger `-em ready`, `-em pause`, and `-em unpause` commands.

## Project Structure

```
barkem/
├── src/barkem/
│   ├── vision/        # Screen capture, template matching, OCR, chat reading
│   ├── input/         # Virtual gamepad controller + D-pad navigators
│   ├── bot/           # Main bot state machine
│   ├── api/           # FastAPI endpoints
│   ├── config/        # Settings management
│   └── tools/         # Calibration, gamepad test, keyboard emulator
├── templates/         # UI element template images (user-captured)
├── config/            # Runtime configuration (YAML)
├── tests/
└── docs/
```

## Development Status

**Phase 1 complete** — Vision foundation + controller input refactor.

**Phase 2 complete** — Window focus, menu navigation, lobby creation,
mode/map dropdown selection with OCR verification + retry, lobby code
OCR.

**Phase 3 complete** — Lobby state OCR (unassigned / spectators / team
slots, with background-color classification to distinguish empty
`---` rows from real players), and team placement via the Manage Lobby
(Y) overlay + context-menu **Move in Lobby** flow. The bot itself uses
the one-press RS self-shortcut to spectate at the end. Supports partial
rosters for testing with a limited number of real accounts.

**Phase 4 complete** — Chat-based captain ready detection (`-em ready`)
and match start. The bot polls the chat region via OCR (~1s cadence;
messages fade after ~8s in-game so anything faster than that catches
them). When the configured number of captains have ready'd up, the
bot presses **X** from the private-match lobby — the game's "Start
Match" shortcut works from any focus state, so no button navigation
is needed. `--min-ready 1` supports solo testing with a single real
account; production runs use `--min-ready 2`. The 5-15s server-side
wait between the X press and the actual match start is visible as
the in-game loading screen, so no bot-authored chat announcement is
sent.

**Phase 5 complete** — In-match lifecycle.  The bot polls chat during
a live match by holding the Menu button to open the in-match chat
window (different region from the lobby chat), OCRs, then closes
with B.  On `-em pause` from a captain it runs a 3-sec chat countdown
(typed via a virtual keyboard, since each message auto-closes chat
and has to be re-opened), toggles pause with D-pad Left, waits for
`-em unpause` / `-em continue` from the same captain *or* a
configurable `max_duration_s` timeout, runs a 5-sec unpause
countdown, and toggles pause off.  Per-team `max_pauses_per_team`
and `cooldown_s` limits are enforced and API-overridable.

Chat OCR uses a chat-specific preprocessing path (HSV-value threshold
plus a 1-px stroke dilate) instead of the generic grayscale+Otsu
pipeline — player names render in saturated teal and message bodies
in near-white, and the generic pipeline was collapsing the teal into
the background on bright scenes (fire, sky, snow). The V-channel
threshold separates foreground from background regardless of what's
behind the semi-transparent chat overlay. Bot-authored chat messages
are typed in lowercase: pynput's `Controller.type()` on Windows + The
Finals' chat widget drops shift-modified keys (the first real
uppercase letter after a burst of lowercase input disappears
outright), and lowercase sidesteps the shift path entirely.

Match end is detected via the "SUMMARY" screen template — the bot
presses A to skip it immediately, then hands the final scoreboard
frame to `ScoreboardReader` for OCR.

**Phase 6 complete** — Full scoreboard capture (Final Round /
Head2Head: 2 teams × 3 players).  `ScoreboardReader` now returns the
complete per-player statline, not just a team total:

- Team money total (per team)
- Per player: class indicator (L / M / H), Embark ID, eliminations,
  assists, deaths, revives, total damage dealt, total support
  (healing + damage blocked + cover), total objective (box inserts +
  steals + platform time + …)

Team names are intentionally not captured — private matches can't
rename teams, so the label is always the default.  **Coins**
(self-revive charges remaining) are only shown in the live in-match
HUD, not on the post-match spectator scoreboard, so they're excluded
from the capture.

Region layout is a **row × column grid** rather than a flat list of
(player, stat) boxes.  All 6 player rows share the same x-coordinates
for every column, so calibration only needs 3 y-spans per team + one
x-span per column (class, name, and the 7 stat columns) — 15 inputs
instead of 50+ flat regions.  The reader crosses a row y-span with a
column x-span to get each cell bounding box.

OCR is column-aware: the L/M/H glyph uses a single-character whitelist
(`tessedit_char_whitelist=LMH`, psm 10), integer stats whitelist digits
plus thousand separators which are stripped before parsing, and names
use the player-name whitelist (the discriminator is included in the
OCR'd name; fuzzy-matching against the known roster is the caller's
job).

**Preprocessing — V-channel for the whole scoreboard.** Scoreboard
cells render white text on the team's coloured tile (orange, pink,
blue, teal, …). Grayscale+Otsu picks a single global cutoff and on
pale team colours the white glyphs and background end up on the same
side of the threshold. The chat-OCR V-channel path (`V = max(B, G,
R)`) avoids this entirely: pure white sits at V≈255 regardless of
hue, while team tiles sit at V≈150-200, so a fixed cutoff separates
them cleanly. Every scoreboard read — team totals, class glyph,
name, and the 8 stat columns — is routed through `preprocess_chat`.

A guided calibration wizard lives at `python -m barkem.tools.calibrate
--scoreboard`: it captures a screenshot, prompts through all 16 spans
via two right-clicks each, then prints a ready-to-paste YAML block for
`regions.scoreboard`.

**Phase 7 next** — API endpoints, webhook result delivery, and the
orchestrator that wires Phases 2-5 together behind a single
`POST /api/v1/match/start` call.

**Phase 8+ (future, not started)** — Once the core bot runs
unattended and reliably, the direction is a small product around
it:

1. **Packaged distributable.** Windows `.exe` (PyInstaller)
   bundling the signed ViGEmBus MSI alongside, so operators don't
   have to install the driver separately. Linux installer script
   with the `/dev/uinput` udev rule pre-wired. Bot name +
   coordinator endpoint configurable at invocation time (CLI /
   env / first-run wizard), not YAML-only.
2. **Self-hostable coordinator service.** One coordinator
   container + N bot VMs (each running The Finals inside a
   GeForce NOW browser session). The coordinator fans match
   requests out to idle bots, forwards results back to the
   tournament system, and watches bot liveness — if a GeForce
   NOW session drops or a bot goes unreachable, the operator
   gets visibility.
3. **Marketing site + opt-in global telemetry.** A public page
   showing what BarkEm does, plus aggregate-only numbers (total
   sessions managed, match-hours supervised) for operators who
   opt in. No per-match detail, no PII.

Phase 7 design decisions — API binding, configuration
precedence, structured logging, heartbeat endpoint — are picked
to avoid painting Phase 8+ into a corner. See the
`the-finals-bot-report_v2_4.md` Appendix D for the full
long-term plan.

### Mode / map / variant relationships

A few things to know when configuring a match:

- **Map pool varies by game mode.** Most competitive modes (Final
  Round, Cashout, Quick Cash, Head2Head) share the same pool, but some
  modes restrict it. The current config assumes the standard pool —
  per-mode map lists may need to be added later.
- **Variants, conditions, and game shows are per-map.** Each map
  exposes a different set of options, and some maps don't have one or
  more of these dropdowns at all. Use index `0` ("ANY"/default) as the
  safe choice unless you've calibrated per-map indices.
- **Dropdowns are anchored before each selection.** The bot opens a
  dropdown, presses UP×14 to guarantee index 0, then DOWN×N to the
  target. After confirming, it OCRs the displayed value and retries up
  to 3 times — important on GeForce NOW where input lag occasionally
  drops D-pad presses.

## Legal Disclaimer

This tool automates UI interactions using screen capture and virtual controller input. It does not read or modify game memory, inject code into the game process, or intercept network traffic.

Use at your own risk. The developers are not responsible for any account actions taken by Embark Studios or Easy Anti-Cheat.

## License

Shield: [![CC BY-NC 4.0][cc-by-nc-shield]][cc-by-nc]

This work is licensed under a
[Creative Commons Attribution-NonCommercial 4.0 International License][cc-by-nc].

[![CC BY-NC 4.0][cc-by-nc-image]][cc-by-nc]

[cc-by-nc]: https://creativecommons.org/licenses/by-nc/4.0/
[cc-by-nc-image]: https://licensebuttons.net/l/by-nc/4.0/88x31.png
[cc-by-nc-shield]: https://img.shields.io/badge/License-CC%20BY--NC%204.0-lightgrey.svg

---

*Made for the competitive Finals community*