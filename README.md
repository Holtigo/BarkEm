# BarkEm

**Private match automation for The Finals**

> Bark 'em into the lobby.

Stop manually creating lobbies. BarkEm handles lobby creation, team placement, match monitoring, and result capture so you can focus on running tournaments, not clicking menus.

## Features

- **Automated lobby creation** — Creates private matches with configured mode, map, and variant
- **Manual player join** — Returns lobby code via API, players join themselves
- **Team placement** — Uses OCR to identify players and drag them to correct teams
- **Captain ready system** — Match starts when both team captains type `-em ready` in game chat
- **Pause/unpause support** — Captains can type `-em pause` and `-em unpause` during matches
- **Match monitoring** — Sparse polling to detect match completion without resource waste
- **Result capture** — Screenshots scoreboard, extracts scores via OCR
- **Platform-agnostic API** — RESTful endpoints + webhooks for integration with any tournament system

## Architecture

BarkEm uses a **single bot model**:

1. Bot creates private match lobby
2. Returns lobby code via API → players join manually
3. Bot moves itself to spectator, then places players on correct teams
4. Monitors chat for captain `-em ready` commands
5. Both captains ready → countdown → match starts
6. During match: monitors for `-em pause` / `-em unpause`
7. Match ends → captures scoreboard → returns results via webhook

The bot uses computer vision (screen capture + template matching + OCR) and standard Windows input APIs, ensuring compatibility with Easy Anti-Cheat.

## Requirements

- Windows 10/11
- Python 3.11+
- [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) (add to PATH)
- The Finals running in **Borderless Windowed** mode
- One game account for the bot

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/barkem.git
cd barkem

# Create virtual environment
python -m venv venv
venv\Scripts\activate  # Windows

# Install dependencies
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

api:
  host: "0.0.0.0"
  port: 8080
```

See [docs/configuration.md](docs/configuration.md) for full options.

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

### Response

```json
{
  "status": "accepted",
  "match_id": "test-001",
  "lobby_code": "AB12",
  "captains": {
    "team1": "Player1#1234",
    "team2": "Player4#3456"
  }
}
```

Distribute the `lobby_code` to players so they can join the match.

## Project Structure

```
barkem/
├── src/barkem/
│   ├── vision/        # Screen capture, template matching, OCR, chat reading
│   ├── input/         # Mouse/keyboard simulation
│   ├── bot/           # Main bot state machine
│   ├── api/           # FastAPI endpoints
│   └── config/        # Settings management
├── templates/         # UI element images (user-captured)
├── config/            # Runtime configuration
├── tests/
└── docs/
```

## Development Status

**Proof of Concept** — Not yet production-ready.

See [docs/roadmap.md](docs/roadmap.md) for implementation phases.

## Legal Disclaimer

This tool automates UI interactions using screen capture and standard input simulation. It does not:
- Read or modify game memory
- Inject code into the game process
- Intercept network traffic

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