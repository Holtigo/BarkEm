"""
BarkEm Phase 1 — Calibration & Testing Tool

Run this script to:
  1. Capture a screenshot from the game
  2. Interactively find pixel coordinates (hover to see x,y in title bar)
  3. Test OCR on specific regions
  4. Test template matching / state detection
  5. Visualize all configured regions on a screenshot

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
import sys
import time

import cv2
import numpy as np


def get_settings():
    """Load settings, or return defaults if not configured."""
    try:
        from barkem.config import get_settings
        return get_settings()
    except Exception as e:
        print(f"[WARN] Could not load settings: {e}")
        print("[WARN] Using defaults.")
        return None


def create_capture():
    """Create and start a screen capture device."""
    from barkem.vision.capture import ScreenCapture
    cap = ScreenCapture()
    cap.start()
    return cap


def capture_screenshot(cap) -> np.ndarray:
    """Grab a screenshot, retrying a few times."""
    for _ in range(10):
        frame = cap.grab()
        if frame is not None:
            return frame
        time.sleep(0.1)
    raise RuntimeError("Failed to capture screenshot after 10 attempts.")


# ─── Mode: Interactive Coordinate Finder ───────────────────────────────────


def run_coordinate_finder():
    """
    Capture a screenshot and open it in a window where you can
    hover your mouse to see coordinates in the title bar.

    Left-click to print coordinates to the console.
    Right-click to mark a region start/end.
    Press 'S' to save the current screenshot.
    Press 'Q' or ESC to quit.
    """
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

        # OpenCV mouse callbacks provide coordinates (x, y) relative to the image
        actual_x, actual_y = x, y

        if event == cv2.EVENT_MOUSEMOVE:
            cv2.setWindowTitle(
                window_name,
                f"BarkEm Calibration ({actual_x}, {actual_y})"
            )

        elif event == cv2.EVENT_LBUTTONDOWN:
            print(f"  CLICK: ({actual_x}, {actual_y})")
            click_log.append((actual_x, actual_y))
            # Draw marker on display
            display = frame.copy()
            for cx, cy in click_log:
                cv2.drawMarker(display, (cx, cy), (0, 0, 255),
                               cv2.MARKER_CROSS, 20, 2)
            cv2.imshow(window_name, display)

        elif event == cv2.EVENT_RBUTTONDOWN:
            if region_start is None:
                region_start = (actual_x, actual_y)
                print(f"  REGION START: ({actual_x}, {actual_y})")
            else:
                rx1, ry1 = region_start
                rx2, ry2 = actual_x, actual_y
                # Normalize
                x1, y1 = min(rx1, rx2), min(ry1, ry2)
                x2, y2 = max(rx1, rx2), max(ry1, ry2)
                print(f"  REGION END:   ({actual_x}, {actual_y})")
                print(f"  → REGION: [{x1}, {y1}, {x2}, {y2}]")
                print()
                # Draw rectangle
                display = frame.copy()
                cv2.rectangle(display, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.imshow(window_name, display)
                region_start = None

    cv2.setMouseCallback(window_name, mouse_callback)
    cv2.imshow(window_name, display)

    while True:
        key = cv2.waitKey(50) & 0xFF
        if key in (ord('q'), ord('Q'), 27):  # Q or ESC
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
    """
    Capture a screenshot and run OCR on all configured regions.
    Prints results and saves annotated debug image.
    """
    print("=" * 60)
    print("  BarkEm OCR Test")
    print("=" * 60)
    print()

    settings = get_settings()

    from barkem.vision.ocr import TextReader
    from barkem.vision.regions import ScreenRegions, Region, load_regions_from_dict
    from barkem.vision.debug import draw_ocr_result, save_debug_screenshot

    # Determine tesseract path
    tesseract_cmd = None
    if settings and hasattr(settings.vision, 'tesseract_cmd'):
        tesseract_cmd = settings.vision.tesseract_cmd

    reader = TextReader(tesseract_cmd=tesseract_cmd)

    # Load regions
    regions = ScreenRegions()
    if settings and hasattr(settings, 'regions'):
        regions = load_regions_from_dict(settings.regions)

    print("Capturing screenshot...")
    cap = create_capture()
    frame = capture_screenshot(cap)
    cap.stop()

    annotated = frame.copy()

    # Collect all OCR-able regions
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
        if region and isinstance(region, Region):
            if region.x1 != 0 or region.y1 != 0 or region.x2 != 0 or region.y2 != 0:
                ocr_targets.append((f"lobby.{name}", region))

    # Context menu player name (the clean name shown in the popup)
    ctx_name = regions.context_menu.player_name
    if ctx_name.x1 != 0 or ctx_name.x2 != 0:
        ocr_targets.append(("context_menu.player_name", ctx_name))

    # Chat region
    chat_area = regions.chat.chat_area
    if chat_area.x1 != 0 or chat_area.x2 != 0:
        ocr_targets.append(("chat.chat_area", chat_area))

    # Scoreboard regions
    sb = regions.scoreboard
    for name in [
        "team1_score", "team2_score",
        "team1_player1_score_name", "team1_player1_score_value",
        "team1_player2_score_name", "team1_player2_score_value",
        "team1_player3_score_name", "team1_player3_score_value",
        "team2_player1_score_name", "team2_player1_score_value",
        "team2_player2_score_name", "team2_player2_score_value",
        "team2_player3_score_name", "team2_player3_score_value",
    ]:
        region = getattr(sb, name, None)
        if region and isinstance(region, Region):
            if region.x1 != 0 or region.y1 != 0 or region.x2 != 0 or region.y2 != 0:
                ocr_targets.append((f"scoreboard.{name}", region))

    if not ocr_targets:
        print()
        print("[!] No regions configured yet.")
        print("    Run 'python -m barkem.tools.calibrate' to find coordinates,")
        print("    then add them to config/settings.yaml under 'regions'.")
        print()
        print("    Saving raw screenshot for reference...")
        path = save_debug_screenshot(frame, "ocr_test_raw")
        print(f"    Saved: {path}")
        return

    print(f"Testing OCR on {len(ocr_targets)} region(s)...")
    print()

    for name, region in ocr_targets:
        # Determine OCR mode
        if "score_value" in name or "score" in name and "name" not in name:
            whitelist = "0123456789"
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

        psm = 6 if "chat" in name else 7

        result = reader.read_region_with_confidence(
            frame, region.as_tuple(), whitelist=whitelist, psm=psm,
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
    """
    Capture a screenshot and test game state detection.
    Shows which templates were found and which are missing.
    """
    print("=" * 60)
    print("  BarkEm State Detection Test")
    print("=" * 60)
    print()

    from barkem.vision.state_detector import GameStateDetector, GameScreen
    from barkem.vision.debug import draw_template_match, save_debug_screenshot

    detector = GameStateDetector()

    # Check template availability
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
        print("    Capture template images from the game and save as .png files.")
        print("    See Appendix B in the project report for the full checklist.")
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

        annotated = draw_template_match(
            frame, match.x, match.y, match.template_name, match.confidence
        )
        path = save_debug_screenshot(annotated, "state_test")
        print(f"  Saved: {path}")
    else:
        print("  No template matched. Game may be on an unknown screen.")
        path = save_debug_screenshot(frame, "state_test_unknown")
        print(f"  Raw screenshot saved: {path}")


# ─── Mode: Draw All Regions ───────────────────────────────────────────────


def run_draw_regions():
    """
    Capture a screenshot and draw all configured regions on it.
    Great for visually verifying your coordinate configuration.
    """
    print("=" * 60)
    print("  BarkEm Region Visualizer")
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
    print("Open this image to verify your region coordinates.")


# ─── Mode: Just Screenshot ────────────────────────────────────────────────


def run_screenshot():
    """Just capture and save a screenshot."""
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
        description="BarkEm Phase 1 — Calibration & Testing Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Modes:
  (default)        Interactive coordinate finder — hover to see (x,y)
  --test-ocr       Run OCR on all configured regions
  --test-state     Test game state detection via templates
  --draw-regions   Draw all configured regions on a screenshot
  --screenshot     Just capture and save a screenshot
        """,
    )
    parser.add_argument("--test-ocr", action="store_true", help="Test OCR on configured regions")
    parser.add_argument("--test-state", action="store_true", help="Test game state detection")
    parser.add_argument("--draw-regions", action="store_true", help="Draw all regions on screenshot")
    parser.add_argument("--screenshot", action="store_true", help="Just save a screenshot")

    args = parser.parse_args()

    if args.test_ocr:
        run_ocr_test()
    elif args.test_state:
        run_state_test()
    elif args.draw_regions:
        run_draw_regions()
    elif args.screenshot:
        run_screenshot()
    else:
        run_coordinate_finder()


if __name__ == "__main__":
    main()
