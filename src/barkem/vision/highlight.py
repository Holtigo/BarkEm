"""
Highlight detection — which lobby slot currently has the D-pad cursor?

The selected slot gets a distinct bright/blue glow on its border.  We
score every candidate slot by counting pixels in its bounding box that
fall inside a configurable blue-highlight colour range (HSV), and pick
the slot with the highest score.

We match on pixel *count* rather than a fixed template because:
  • The glow blooms and pulses slightly (animated).
  • Slots can contain different name text, which would break template
    matching, but doesn't affect border-pixel count.

The caller passes the subset of slot regions it cares about (e.g. just
the unassigned + spectator rows while in the lobby) so we don't waste
work and don't get confused by permanently-selected UI elsewhere.
"""

from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np

from barkem.vision.regions import Region


# Default HSV range for the blue highlight glow.  Tune via the
# `tools.highlight_watch` live viewer if the colour shifts.
#
# OpenCV HSV: H ∈ [0,179], S ∈ [0,255], V ∈ [0,255].
# Blue glow ≈ H 90-130, high saturation + value.
DEFAULT_HSV_LOWER = (90, 120, 180)
DEFAULT_HSV_UPPER = (130, 255, 255)


@dataclass
class HighlightScore:
    """Score for a single candidate slot."""
    name: str
    score: int          # number of matching blue pixels in the slot
    region: Region


class HighlightDetector:
    """
    Scores a set of slot regions by how much blue highlight glow is
    present in each, returning the one most likely to be selected.
    """

    def __init__(
        self,
        hsv_lower: tuple[int, int, int] = DEFAULT_HSV_LOWER,
        hsv_upper: tuple[int, int, int] = DEFAULT_HSV_UPPER,
        min_pixels: int = 50,
        border_margin: int = 8,
    ):
        """
        Args:
            hsv_lower / hsv_upper: inclusive HSV range for "blue glow".
            min_pixels: minimum matching-pixel count to call a slot selected.
                Below this, `detect` returns None.
            border_margin: extend each slot region by this many pixels in
                every direction before scoring — the glow tends to sit
                just outside the tight OCR name bounding box.
        """
        self.lower = np.array(hsv_lower, dtype=np.uint8)
        self.upper = np.array(hsv_upper, dtype=np.uint8)
        self.min_pixels = min_pixels
        self.border_margin = border_margin

    def score_region(self, frame: np.ndarray, region: Region) -> int:
        """Count glow pixels inside a single (padded) region."""
        h, w = frame.shape[:2]
        m = self.border_margin
        x1 = max(0, region.x1 - m)
        y1 = max(0, region.y1 - m)
        x2 = min(w, region.x2 + m)
        y2 = min(h, region.y2 + m)
        roi = frame[y1:y2, x1:x2]
        if roi.size == 0:
            return 0
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, self.lower, self.upper)
        return int(np.count_nonzero(mask))

    def score_all(
        self,
        frame: np.ndarray,
        candidates: list[tuple[str, Region]],
    ) -> list[HighlightScore]:
        """Score every candidate; results are sorted high → low."""
        scores = [
            HighlightScore(name=name, score=self.score_region(frame, r), region=r)
            for name, r in candidates
            if not r.is_zero
        ]
        scores.sort(key=lambda s: s.score, reverse=True)
        return scores

    def detect(
        self,
        frame: np.ndarray,
        candidates: list[tuple[str, Region]],
    ) -> Optional[HighlightScore]:
        """
        Return the slot most likely to be selected, or None if no
        candidate clears ``min_pixels``.
        """
        scores = self.score_all(frame, candidates)
        if not scores:
            return None
        best = scores[0]
        if best.score < self.min_pixels:
            return None
        return best
