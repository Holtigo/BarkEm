# BarkEm

🐕 **Private match automation for The Finals**

Stop manually creating lobbies. BarkEm handles lobby creation, team placement, match monitoring, and result capture so you can focus on running tournaments, not clicking menus. Built with virtual controller emulation for GeForce NOW cloud gaming compatibility.

## Features

- **Automated lobby creation** — Creates private matches with configured mode, map, and variant
- **Manual player join** — Returns lobby code via API, players join themselves
- **Team placement** — Uses OCR to identify players, D-pad grid navigation to place them on correct teams
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
3. Bot moves itself to spectator, then places players on correct teams via grid navigation
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
  mode_anchor_up: 7
  mode_down_to_private: 7

# Lobby grid (3-column layout)
grid:
  team1_rows: 3
  team2_rows: 3
  context_move_self: 1
  context_move_other: 2
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

**Phase 3 next** — Team placement (OCR player names, place into team
slots via D-pad).

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