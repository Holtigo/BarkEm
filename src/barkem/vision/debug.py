"""
Debug visualisation for drawing detected regions, OCR results,
and template matches onto screenshots.
"""

import os

import cv2
import numpy as np

from barkem.vision.regions import Region


# Colour scheme (BGR)
COLOR_REGION = (0, 255, 0)       # Green — OCR regions
COLOR_TEMPLATE = (255, 0, 0)     # Blue — template matches
COLOR_TEXT = (255, 255, 255)
COLOR_TEXT_BG = (0, 0, 0)
COLOR_OCR_RESULT = (0, 255, 255) # Yellow


def draw_region(
    frame: np.ndarray,
    region: Region,
    label: str = "",
    color: tuple[int, int, int] = COLOR_REGION,
    thickness: int = 2,
) -> np.ndarray:
    frame = frame.copy()
    cv2.rectangle(frame, (region.x1, region.y1), (region.x2, region.y2), color, thickness)
    if label:
        _draw_label(frame, label, (region.x1, region.y1 - 5), color)
    return frame


def draw_ocr_result(
    frame: np.ndarray,
    region: Region,
    text: str,
    confidence: float = -1,
    color: tuple[int, int, int] = COLOR_REGION,
) -> np.ndarray:
    frame = draw_region(frame, region, color=color)
    label = f"{text} ({confidence:.0f}%)" if confidence >= 0 else text
    _draw_label(frame, label, (region.x1, region.y2 + 15), COLOR_OCR_RESULT)
    return frame


def draw_template_match(
    frame: np.ndarray,
    x: int,
    y: int,
    template_name: str,
    confidence: float,
    color: tuple[int, int, int] = COLOR_TEMPLATE,
) -> np.ndarray:
    frame = frame.copy()
    cv2.drawMarker(frame, (x, y), color, cv2.MARKER_DIAMOND, 15, 2)
    _draw_label(frame, f"{template_name} ({confidence:.2f})", (x + 12, y - 5), color)
    return frame


def draw_all_regions(
    frame: np.ndarray,
    regions,
    skip_zero: bool = True,
) -> np.ndarray:
    """Draw ALL configured OCR regions on a frame for visual verification."""
    annotated = frame.copy()

    for group_name in ["context_menu", "lobby", "chat", "match"]:
        group = getattr(regions, group_name, None)
        if group is None:
            continue
        for field_name in vars(group):
            if field_name.startswith("_"):
                continue
            val = getattr(group, field_name)
            if isinstance(val, Region):
                if skip_zero and val.is_zero:
                    continue
                annotated = draw_region(annotated, val, label=f"{group_name}.{field_name}")

    annotated = draw_scoreboard_regions(annotated, regions.scoreboard, skip_zero=skip_zero)
    return annotated


def draw_scoreboard_regions(frame: np.ndarray, sb, skip_zero: bool = True) -> np.ndarray:
    """Draw scoreboard totals + every row×column cell."""
    from barkem.vision.regions import SCOREBOARD_STAT_COLUMNS

    for name in ("team1_score", "team2_score"):
        r = getattr(sb, name)
        if skip_zero and r.is_zero:
            continue
        frame = draw_region(frame, r, label=f"scoreboard.{name}")

    columns = ("class", "name", *SCOREBOARD_STAT_COLUMNS)
    for team_id in (1, 2):
        for row_idx in range(3):
            for col in columns:
                cell = sb.cell(team_id, row_idx, col)
                if skip_zero and cell.is_zero:
                    continue
                label = f"sb.t{team_id}r{row_idx + 1}.{col}"
                frame = draw_region(frame, cell, label=label)
    return frame


def save_debug_screenshot(
    frame: np.ndarray,
    name: str,
    debug_dir: str = "./debug/screenshots",
) -> str:
    os.makedirs(debug_dir, exist_ok=True)
    path = os.path.join(debug_dir, f"{name}.png")
    cv2.imwrite(path, frame)
    return path


def _draw_label(
    frame: np.ndarray,
    text: str,
    pos: tuple[int, int],
    color: tuple[int, int, int],
    font_scale: float = 0.5,
    thickness: int = 1,
) -> None:
    font = cv2.FONT_HERSHEY_SIMPLEX
    (w, h), baseline = cv2.getTextSize(text, font, font_scale, thickness)
    x, y = pos
    cv2.rectangle(frame, (x - 1, y - h - 3), (x + w + 1, y + baseline + 1), COLOR_TEXT_BG, cv2.FILLED)
    cv2.putText(frame, text, (x, y), font, font_scale, color, thickness, cv2.LINE_AA)
