"""
Debug visualization for drawing detected regions, OCR results,
and template matches onto screenshots.

Used during Phase 1 calibration and ongoing debugging.
"""

import os
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from barkem.vision.regions import Region, ClickTarget


# Color scheme (BGR)
COLOR_REGION = (0, 255, 0)       # Green — OCR regions
COLOR_CLICK = (0, 0, 255)        # Red — click targets
COLOR_TEMPLATE = (255, 0, 0)     # Blue — template matches
COLOR_TEXT = (255, 255, 255)     # White — label text
COLOR_TEXT_BG = (0, 0, 0)       # Black — label background
COLOR_OCR_RESULT = (0, 255, 255) # Yellow — OCR result text


def draw_region(
        frame: np.ndarray,
        region: Region,
        label: str = "",
        color: tuple[int, int, int] = COLOR_REGION,
        thickness: int = 2,
) -> np.ndarray:
    """Draw a bounding box region on the frame."""
    frame = frame.copy()
    cv2.rectangle(
        frame,
        (region.x1, region.y1),
        (region.x2, region.y2),
        color,
        thickness,
    )
    if label:
        _draw_label(frame, label, (region.x1, region.y1 - 5), color)
    return frame


def draw_click_target(
        frame: np.ndarray,
        target: ClickTarget,
        label: str = "",
        color: tuple[int, int, int] = COLOR_CLICK,
        radius: int = 8,
) -> np.ndarray:
    """Draw a click target crosshair on the frame."""
    frame = frame.copy()
    x, y = target.x, target.y

    # Crosshair
    cv2.drawMarker(
        frame, (x, y), color,
        markerType=cv2.MARKER_CROSS,
        markerSize=radius * 3,
        thickness=2,
    )
    # Circle
    cv2.circle(frame, (x, y), radius, color, 2)

    if label:
        _draw_label(frame, label, (x + radius + 4, y - 5), color)
    return frame


def draw_ocr_result(
        frame: np.ndarray,
        region: Region,
        text: str,
        confidence: float = -1,
        color: tuple[int, int, int] = COLOR_REGION,
) -> np.ndarray:
    """Draw an OCR region with the detected text underneath."""
    frame = draw_region(frame, region, color=color)

    label = text
    if confidence >= 0:
        label = f"{text} ({confidence:.0f}%)"

    _draw_label(
        frame, label,
        (region.x1, region.y2 + 15),
        COLOR_OCR_RESULT,
    )
    return frame


def draw_template_match(
        frame: np.ndarray,
        x: int,
        y: int,
        template_name: str,
        confidence: float,
        color: tuple[int, int, int] = COLOR_TEMPLATE,
) -> np.ndarray:
    """Draw a template match result."""
    frame = frame.copy()
    cv2.drawMarker(
        frame, (x, y), color,
        markerType=cv2.MARKER_DIAMOND,
        markerSize=15,
        thickness=2,
    )
    label = f"{template_name} ({confidence:.2f})"
    _draw_label(frame, label, (x + 12, y - 5), color)
    return frame


def draw_all_regions(
        frame: np.ndarray,
        regions,
        skip_zero: bool = True,
) -> np.ndarray:
    """
    Draw ALL configured regions on a frame for visual verification.

    Args:
        frame: The screenshot to draw on.
        regions: A ScreenRegions instance.
        skip_zero: If True, skip regions that are still at (0,0,0,0).

    Returns:
        Annotated frame.
    """
    annotated = frame.copy()

    def _is_zero_region(r):
        return isinstance(r, Region) and r.x1 == 0 and r.y1 == 0 and r.x2 == 0 and r.y2 == 0

    def _is_zero_click(c):
        return isinstance(c, ClickTarget) and c.x == 0 and c.y == 0

    # Walk through all region groups
    for group_name in ["menu", "mode_map", "context_menu", "lobby", "chat", "scoreboard", "match"]:
        group = getattr(regions, group_name, None)
        if group is None:
            continue

        for field_name in vars(group):
            if field_name.startswith("_"):
                continue
            val = getattr(group, field_name)

            if isinstance(val, Region):
                if skip_zero and _is_zero_region(val):
                    continue
                label = f"{group_name}.{field_name}"
                annotated = draw_region(annotated, val, label=label)

            elif isinstance(val, ClickTarget):
                if skip_zero and _is_zero_click(val):
                    continue
                label = f"{group_name}.{field_name}"
                annotated = draw_click_target(annotated, val, label=label)

    return annotated


def save_debug_screenshot(
        frame: np.ndarray,
        name: str,
        debug_dir: str = "./debug/screenshots",
) -> str:
    """
    Save a debug screenshot.

    Args:
        frame: Image to save.
        name: Filename (without extension).
        debug_dir: Directory to save to.

    Returns:
        Full path of the saved image.
    """
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
    """Draw a text label with a dark background for readability."""
    font = cv2.FONT_HERSHEY_SIMPLEX
    (w, h), baseline = cv2.getTextSize(text, font, font_scale, thickness)

    x, y = pos
    # Background rectangle
    cv2.rectangle(
        frame,
        (x - 1, y - h - 3),
        (x + w + 1, y + baseline + 1),
        COLOR_TEXT_BG,
        cv2.FILLED,
    )
    # Text
    cv2.putText(frame, text, (x, y), font, font_scale, color, thickness, cv2.LINE_AA)