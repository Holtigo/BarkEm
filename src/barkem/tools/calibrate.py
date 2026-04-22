"""
BarkEm Phase 1 — Calibration & Testing Tool

Run this script to:
  1. Capture a screenshot from the game
  2. Interactively find pixel coordinates for OCR regions
  3. Test OCR on specific regions
  4. Test template matching / state detection
  5. Visualise all configured regions on a screenshot

Usage:
    python -m barkem.tools.calibrate              # Interactive coordinate finder
    python -m barkem.tools.calibrate --test-ocr    # Test OCR on configured regions
    python -m barkem.tools.calibrate --test-state  # Test state detection
    python -m barkem.tools.calibrate --draw-regions # Draw all regions on screenshot
    python -m barkem.tools.calibrate --screenshot   # Just save a screenshot

Prerequisites:
    - The Finals running in Borderless Windowed mode
    - Tesseract installed (default: C:\\Program Files\\Tesseract-OCR\\tesseract.exe)
"""

import argparse
import os
import time

import cv2
import numpy as np


def get_settings():
    try:
        from barkem.config import get_settings
        return get_settings()
    except Exception as e:
        print(f"[WARN] Could not load settings: {e}")
        print("[WARN] Using defaults.")
        return None


def create_capture():
    from barkem.vision.capture import ScreenCapture
    cap = ScreenCapture()
    cap.start()
    return cap


def capture_screenshot(cap) -> np.ndarray:
    for _ in range(10):
        frame = cap.grab()
        if frame is not None:
            return frame
        time.sleep(0.1)
    raise RuntimeError("Failed to capture screenshot after 10 attempts.")


# ─── Mode: Interactive Coordinate Finder ───────────────────────────────────

def run_coordinate_finder():
    print("=" * 60)
    print("  BarkEm Coordinate Finder")
    print("=" * 60)
    print()
    print("Capturing screenshot...")

    cap = create_capture()
    frame = capture_screenshot(cap)
    cap.stop()

    print(f"Screenshot captured: {frame.shape[1]}x{frame.shape[0]}")
    print()
    print("Instructions:")
    print("  - Hover mouse to see (x, y) in the window title")
    print("  - LEFT CLICK  → print coordinate to console")
    print("  - RIGHT CLICK → mark region corner (2 clicks = region)")
    print("  - Press S     → save screenshot to debug/")
    print("  - Press Q/ESC → quit")
    print()

    display = frame.copy()
    window_name = "BarkEm Calibration — Hover for coordinates"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window_name, 1280, 720)

    region_start = None
    click_log = []

    def mouse_callback(event, x, y, flags, param):
        nonlocal region_start, display

        if event == cv2.EVENT_MOUSEMOVE:
            cv2.setWindowTitle(window_name, f"BarkEm Calibration ({x}, {y})")

        elif event == cv2.EVENT_LBUTTONDOWN:
            print(f"  CLICK: ({x}, {y})")
            click_log.append((x, y))
            display = frame.copy()
            for cx, cy in click_log:
                cv2.drawMarker(display, (cx, cy), (0, 0, 255), cv2.MARKER_CROSS, 20, 2)
            cv2.imshow(window_name, display)

        elif event == cv2.EVENT_RBUTTONDOWN:
            if region_start is None:
                region_start = (x, y)
                print(f"  REGION START: ({x}, {y})")
            else:
                rx1, ry1 = region_start
                x1, y1 = min(rx1, x), min(ry1, y)
                x2, y2 = max(rx1, x), max(ry1, y)
                print(f"  REGION END:   ({x}, {y})")
                print(f"  → REGION: [{x1}, {y1}, {x2}, {y2}]")
                print()
                display = frame.copy()
                cv2.rectangle(display, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.imshow(window_name, display)
                region_start = None

    cv2.setMouseCallback(window_name, mouse_callback)
    cv2.imshow(window_name, display)

    while True:
        key = cv2.waitKey(50) & 0xFF
        if key in (ord('q'), ord('Q'), 27):
            break
        elif key in (ord('s'), ord('S')):
            os.makedirs("debug/screenshots", exist_ok=True)
            path = f"debug/screenshots/calibration_{int(time.time())}.png"
            cv2.imwrite(path, frame)
            print(f"  Saved: {path}")

    cv2.destroyAllWindows()
    print()
    print("Coordinate log:")
    for i, (cx, cy) in enumerate(click_log):
        print(f"  {i + 1}. ({cx}, {cy})")


# ─── Mode: Test OCR on Configured Regions ──────────────────────────────────

def run_ocr_test():
    print("=" * 60)
    print("  BarkEm OCR Test")
    print("=" * 60)
    print()

    settings = get_settings()

    from barkem.vision.ocr import TextReader
    from barkem.vision.regions import ScreenRegions, Region, load_regions_from_dict
    from barkem.vision.debug import draw_ocr_result, save_debug_screenshot

    tesseract_cmd = None
    if settings and hasattr(settings.vision, 'tesseract_cmd'):
        tesseract_cmd = settings.vision.tesseract_cmd

    reader = TextReader(tesseract_cmd=tesseract_cmd)

    regions = ScreenRegions()
    if settings and hasattr(settings, 'regions'):
        regions = load_regions_from_dict(settings.regions)

    print("Capturing screenshot...")
    cap = create_capture()
    frame = capture_screenshot(cap)
    cap.stop()

    annotated = frame.copy()
    ocr_targets = []

    # Lobby regions
    lobby = regions.lobby
    for name in [
        "lobby_code",
        "team1_player1_name", "team1_player2_name", "team1_player3_name",
        "team2_player1_name", "team2_player2_name", "team2_player3_name",
        "unassigned_player1_name", "unassigned_player2_name",
        "unassigned_player3_name", "unassigned_player4_name",
        "unassigned_player5_name", "unassigned_player6_name",
        "unassigned_player7_name", "unassigned_player8_name",
        "unassigned_player9_name", "unassigned_player10_name",
        "spectator1_name", "spectator2_name", "spectator3_name",
    ]:
        region = getattr(lobby, name, None)
        if region and isinstance(region, Region) and not region.is_zero:
            ocr_targets.append((f"lobby.{name}", region))

    # Context menu player name
    ctx_name = regions.context_menu.player_name
    if not ctx_name.is_zero:
        ocr_targets.append(("context_menu.player_name", ctx_name))

    # Chat
    chat_area = regions.chat.chat_area
    if not chat_area.is_zero:
        ocr_targets.append(("chat.chat_area", chat_area))

    # Scoreboard — team totals + every row×column cell
    from barkem.vision.regions import SCOREBOARD_STAT_COLUMNS
    sb = regions.scoreboard
    for name in ("team1_score", "team2_score"):
        region = getattr(sb, name)
        if not region.is_zero:
            ocr_targets.append((f"scoreboard.{name}", region))

    for team_id in (1, 2):
        for row_idx in range(3):
            for col in ("class", "name", *SCOREBOARD_STAT_COLUMNS):
                cell = sb.cell(team_id, row_idx, col)
                if cell.is_zero:
                    continue
                ocr_targets.append(
                    (f"scoreboard.t{team_id}p{row_idx + 1}.{col}", cell)
                )

    if not ocr_targets:
        print()
        print("[!] No regions configured yet.")
        print("    Run 'python -m barkem.tools.calibrate' to find coordinates,")
        print("    then add them to config/settings.yaml under 'regions'.")
        path = save_debug_screenshot(frame, "ocr_test_raw")
        print(f"    Saved raw screenshot: {path}")
        return

    print(f"Testing OCR on {len(ocr_targets)} region(s)...")
    print()

    stat_col_suffixes = tuple(
        f".{c}" for c in ("elims", "assists", "deaths", "revives",
                          "damage", "support", "objective")
    )
    for name, region in ocr_targets:
        if name.endswith(".class"):
            whitelist = "LMH"
            mode_label = "class glyph"
        elif name.endswith(".name"):
            whitelist = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789#_-"
            mode_label = "player name"
        elif name.endswith(stat_col_suffixes) or name.endswith("_score"):
            whitelist = "0123456789,."
            mode_label = "digits"
        elif "lobby_code" in name:
            whitelist = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
            mode_label = "lobby code"
        elif "chat" in name:
            whitelist = None
            mode_label = "chat (block)"
        else:
            whitelist = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789#_-"
            mode_label = "player name"

        if name.endswith(".class"):
            psm = 10
        elif "chat" in name:
            psm = 6
        else:
            psm = 7

        # Scoreboard regions (team totals + every cell) render white
        # text on a coloured team-tile background — route them through
        # the V-channel path for accurate calibration readback.
        use_v = name.startswith("scoreboard.")

        result = reader.read_region_with_confidence(
            frame, region.as_tuple(),
            whitelist=whitelist, psm=psm, use_v_channel=use_v,
        )

        status = "OK" if result.text else "EMPTY"
        print(f"  [{status}] {name} ({mode_label})")
        print(f"         Region: [{region.x1}, {region.y1}, {region.x2}, {region.y2}]")
        print(f"         Text:   '{result.text}'")
        print(f"         Conf:   {result.confidence:.1f}%")
        print()

        annotated = draw_ocr_result(annotated, region, result.text, result.confidence)

    path = save_debug_screenshot(annotated, "ocr_test_annotated")
    print(f"Annotated screenshot saved: {path}")


# ─── Mode: Test State Detection ───────────────────────────────────────────

def run_state_test():
    print("=" * 60)
    print("  BarkEm State Detection Test")
    print("=" * 60)
    print()

    from barkem.vision.state_detector import GameStateDetector, GameScreen
    from barkem.vision.debug import draw_template_match, save_debug_screenshot

    detector = GameStateDetector()
    missing = detector.get_missing_templates()
    available = detector.get_available_templates()

    print("Template status:")
    for screen in GameScreen:
        if screen == GameScreen.UNKNOWN:
            continue
        avail = available.get(screen, [])
        miss = missing.get(screen, [])
        status = "READY" if avail and not miss else ("PARTIAL" if avail else "MISSING")
        print(f"  [{status}] {screen.name}")
        for t in avail:
            print(f"           ✓ {t}.png")
        for t in miss:
            print(f"           ✗ {t}.png  (create this template!)")
    print()

    if not available:
        print("[!] No template images found in templates/ directory.")
        return

    print("Capturing screenshot...")
    cap = create_capture()
    frame = capture_screenshot(cap)
    cap.stop()

    screen, match = detector.detect(frame)
    print(f"Detected screen: {screen.name}")
    if match:
        print(f"  Template: {match.template_name}")
        print(f"  Position: ({match.x}, {match.y})")
        print(f"  Confidence: {match.confidence:.3f}")
        annotated = draw_template_match(frame, match.x, match.y, match.template_name, match.confidence)
        path = save_debug_screenshot(annotated, "state_test")
        print(f"  Saved: {path}")
    else:
        print("  No template matched.")
        path = save_debug_screenshot(frame, "state_test_unknown")
        print(f"  Raw screenshot saved: {path}")


# ─── Mode: Draw All Regions ───────────────────────────────────────────────

def run_draw_regions():
    print("=" * 60)
    print("  BarkEm Region Visualiser")
    print("=" * 60)
    print()

    settings = get_settings()
    from barkem.vision.regions import ScreenRegions, load_regions_from_dict
    from barkem.vision.debug import draw_all_regions, save_debug_screenshot

    regions = ScreenRegions()
    if settings and hasattr(settings, 'regions'):
        regions = load_regions_from_dict(settings.regions)

    print("Capturing screenshot...")
    cap = create_capture()
    frame = capture_screenshot(cap)
    cap.stop()

    annotated = draw_all_regions(frame, regions, skip_zero=True)
    path = save_debug_screenshot(annotated, "regions_overlay")
    print(f"Annotated screenshot saved: {path}")


# ─── Mode: Scoreboard Calibration Wizard ──────────────────────────────────

# 6 player rows (team1×3, team2×3) + 10 columns (class, name, 8 stats)
# — 16 spans total.  Each span is two right-clicks: top-left, bottom-right.
_SCOREBOARD_ROW_PROMPTS: tuple[tuple[str, str], ...] = (
    ("team1_row1", "Team 1 · Player 1 row"),
    ("team1_row2", "Team 1 · Player 2 row"),
    ("team1_row3", "Team 1 · Player 3 row"),
    ("team2_row1", "Team 2 · Player 1 row"),
    ("team2_row2", "Team 2 · Player 2 row"),
    ("team2_row3", "Team 2 · Player 3 row"),
)

_SCOREBOARD_COL_PROMPTS: tuple[tuple[str, str], ...] = (
    ("class",     "Class column (L/M/H glyph)"),
    ("name",      "Name column (Embark ID)"),
    ("elims",     "Eliminations column"),
    ("assists",   "Assists column"),
    ("deaths",    "Deaths column"),
    ("revives",   "Revives column"),
    ("damage",    "Damage column"),
    ("support",   "Support column"),
    ("objective", "Objective column"),
)


def _capture_span(frame, window_name: str, prompt: str) -> tuple[int, int, int, int]:
    """Wait for the user to right-click twice; return (x1, y1, x2, y2)."""
    print(f"\n  [{prompt}]")
    print("    Right-click the TOP-LEFT, then BOTTOM-RIGHT corner.  (q/esc to abort)")
    display = frame.copy()
    cv2.setWindowTitle(window_name, prompt)
    cv2.imshow(window_name, display)

    clicks: list[tuple[int, int]] = []

    def on_mouse(event, x, y, flags, param):
        nonlocal display
        if event == cv2.EVENT_MOUSEMOVE:
            cv2.setWindowTitle(window_name, f"{prompt} — ({x}, {y})")
        elif event == cv2.EVENT_RBUTTONDOWN:
            clicks.append((x, y))
            display = frame.copy()
            if len(clicks) == 1:
                cv2.drawMarker(display, clicks[0], (0, 255, 0), cv2.MARKER_CROSS, 20, 2)
            elif len(clicks) == 2:
                (x1, y1), (x2, y2) = clicks
                rx1, ry1 = min(x1, x2), min(y1, y2)
                rx2, ry2 = max(x1, x2), max(y1, y2)
                cv2.rectangle(display, (rx1, ry1), (rx2, ry2), (0, 255, 0), 2)
            cv2.imshow(window_name, display)

    cv2.setMouseCallback(window_name, on_mouse)

    while True:
        key = cv2.waitKey(50) & 0xFF
        if key in (ord("q"), ord("Q"), 27):
            raise KeyboardInterrupt
        if len(clicks) >= 2:
            break

    (x1, y1), (x2, y2) = clicks[0], clicks[1]
    return min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)


def run_scoreboard_calibration():
    print("=" * 60)
    print("  BarkEm Scoreboard Calibration")
    print("=" * 60)
    print()
    print("This wizard captures 6 row y-spans + 10 column x-spans.")
    print("For each prompt, right-click the top-left and bottom-right")
    print("corners of the tightest bounding box around that row/column.")
    print("Rows: use full row height.  Columns: use full column width.")
    print()
    print("Capturing screenshot…")

    cap = create_capture()
    frame = capture_screenshot(cap)
    cap.stop()
    print(f"  frame: {frame.shape[1]}x{frame.shape[0]}")

    window_name = "BarkEm Scoreboard Calibration"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window_name, 1280, 720)
    cv2.imshow(window_name, frame)

    rows: dict[str, tuple[int, int, int, int]] = {}
    cols: dict[str, tuple[int, int, int, int]] = {}

    try:
        for key, prompt in _SCOREBOARD_ROW_PROMPTS:
            rows[key] = _capture_span(frame, window_name, prompt)
        for key, prompt in _SCOREBOARD_COL_PROMPTS:
            cols[key] = _capture_span(frame, window_name, prompt)
    except KeyboardInterrupt:
        print("\n  Aborted.")
        cv2.destroyAllWindows()
        return
    finally:
        cv2.destroyAllWindows()

    print()
    print("── Paste into config/settings.yaml under regions.scoreboard ──")
    print()
    print("  scoreboard:")
    print("    team1_score: [x, y, x, y]   # <-- keep existing values")
    print("    team2_score: [x, y, x, y]")
    print()
    for team_idx in (1, 2):
        key = f"team{team_idx}_rows"
        r1 = rows[f"team{team_idx}_row1"]
        r2 = rows[f"team{team_idx}_row2"]
        r3 = rows[f"team{team_idx}_row3"]
        print(
            f"    {key}: "
            f"[[{r1[1]}, {r1[3]}], [{r2[1]}, {r2[3]}], [{r3[1]}, {r3[3]}]]"
        )
    print()
    print("    columns:")
    for col_key, _ in _SCOREBOARD_COL_PROMPTS:
        x1, _, x2, _ = cols[col_key]
        print(f"      {col_key + ':':11}[{x1}, {x2}]")
    print()


# ─── Mode: Just Screenshot ────────────────────────────────────────────────

def run_screenshot():
    print("Capturing screenshot...")
    cap = create_capture()
    frame = capture_screenshot(cap)
    cap.stop()

    os.makedirs("debug/screenshots", exist_ok=True)
    path = f"debug/screenshots/screenshot_{int(time.time())}.png"
    cv2.imwrite(path, frame)
    print(f"Saved: {path}")
    print(f"Resolution: {frame.shape[1]}x{frame.shape[0]}")


# ─── Main ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="BarkEm — Calibration & Testing Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Modes:
  (default)        Interactive coordinate finder — hover to see (x,y)
  --test-ocr       Run OCR on all configured regions
  --test-state     Test game state detection via templates
  --draw-regions   Draw all configured regions on a screenshot
  --scoreboard     Guided scoreboard row/column calibration wizard
  --screenshot     Just capture and save a screenshot
        """,
    )
    parser.add_argument("--test-ocr", action="store_true")
    parser.add_argument("--test-state", action="store_true")
    parser.add_argument("--draw-regions", action="store_true")
    parser.add_argument("--scoreboard", action="store_true")
    parser.add_argument("--screenshot", action="store_true")

    args = parser.parse_args()

    if args.test_ocr:
        run_ocr_test()
    elif args.test_state:
        run_state_test()
    elif args.draw_regions:
        run_draw_regions()
    elif args.scoreboard:
        run_scoreboard_calibration()
    elif args.screenshot:
        run_screenshot()
    else:
        run_coordinate_finder()


if __name__ == "__main__":
    main()
