# 🐕 BarkEm

**Private match automation for The Finals**

> Bark 'em into the lobby.

Stop manually creating lobbies. BarkEm handles party invites, lobby creation, team placement, match monitoring, and result capture so you can focus on running tournaments, not clicking menus.

## Features

- **Automated lobby creation** — Creates private matches with configured mode, map, and variant
- **Party-based team population** — Invites players via party system, auto-joins entire teams
- **Team placement** — Uses OCR to identify players and drag them to correct teams
- **Match monitoring** — Sparse polling to detect match completion without resource waste
- **Result capture** — Screenshots scoreboard, extracts scores via OCR
- **Platform-agnostic API** — RESTful endpoints + webhooks for integration with any tournament system

## Architecture

BarkEm uses a **parent/child bot model**:

- **Orchestrator (Parent)** — Handles Team 1 party, creates lobby, manages teams, captures results
- **Child Bot** — Handles Team 2 party, joins via code, leaves after placement (reusable)

Both bots use computer vision (screen capture + template matching) and standard Windows input APIs, ensuring compatibility with Easy Anti-Cheat.

## Requirements

- Windows 10/11
- Python 3.11+
- [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) (add to PATH)
- The Finals running in **Borderless Windowed** mode
- Two game accounts (for orchestrator + child bot)
- Redis (for inter-bot communication)

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

## Project Structure

```
barkem/
├── src/
│   ├── vision/        # Screen capture, template matching, OCR
│   ├── input/         # Mouse/keyboard simulation
│   ├── bot/           # State machines (orchestrator, child)
│   ├── api/           # FastAPI endpoints
│   ├── comms/         # Inter-bot Redis messaging
│   └── config/        # Settings management
├── templates/         # UI element images (user-captured)
├── config/            # Runtime configuration
├── tests/
└── docs/
```

## Development Status

🚧 **Proof of Concept** — Not yet production-ready.

See [docs/roadmap.md](docs/roadmap.md) for implementation phases.

## Legal Disclaimer

This tool automates UI interactions using screen capture and standard input simulation. It does not:
- Read or modify game memory
- Inject code into the game process
- Intercept network traffic

Use at your own risk. The developers are not responsible for any account actions taken by Embark Studios or Easy Anti-Cheat.

## License

MIT License — see [LICENSE](LICENSE) for details.

---

*Made for the competitive Finals community* 🎮
