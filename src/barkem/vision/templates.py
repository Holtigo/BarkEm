"""
Template matching for UI element detection.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import cv2
import numpy as np


@dataclass
class MatchResult:
    """Result of a template match operation."""

    x: int
    y: int
    confidence: float
    template_name: str


class TemplateMatcher:
    """Handles template matching for game UI elements."""

    def __init__(self, templates_dir: str | Path = "templates", threshold: float = 0.85):
        self.templates_dir = Path(templates_dir)
        self.threshold = threshold
        self._templates: dict[str, np.ndarray] = {}

    def load_template(self, name: str) -> Optional[np.ndarray]:
        """Load a template image by name."""
        if name in self._templates:
            return self._templates[name]

        path = self.templates_dir / f"{name}.png"
        if not path.exists():
            return None

        template = cv2.imread(str(path))
        if template is not None:
            self._templates[name] = template
        return template

    def find(
        self,
        frame: np.ndarray,
        template_name: str,
        threshold: Optional[float] = None,
    ) -> Optional[MatchResult]:
        """
        Find a template in the frame.

        Args:
            frame: BGR image to search in.
            template_name: Name of the template to find.
            threshold: Optional confidence threshold override.

        Returns:
            MatchResult with center coordinates if found, None otherwise.
        """
        template = self.load_template(template_name)
        if template is None:
            return None

        threshold = threshold or self.threshold

        # Convert to grayscale for faster matching
        frame_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)

        result = cv2.matchTemplate(frame_gray, template_gray, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)

        if max_val >= threshold:
            h, w = template_gray.shape
            center_x = max_loc[0] + w // 2
            center_y = max_loc[1] + h // 2
            return MatchResult(
                x=center_x,
                y=center_y,
                confidence=max_val,
                template_name=template_name,
            )

        return None

    def find_all(
        self,
        frame: np.ndarray,
        template_name: str,
        threshold: Optional[float] = None,
    ) -> list[MatchResult]:
        """Find all instances of a template in the frame."""
        # TODO: Implement multi-match with non-maximum suppression
        result = self.find(frame, template_name, threshold)
        return [result] if result else []
