"""
OCR for reading player names and scores.
"""

from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np

# TODO: Import when implementing
# import pytesseract


@dataclass
class OCRResult:
    """Result of an OCR operation."""

    text: str
    confidence: float
    region: tuple[int, int, int, int]


class TextReader:
    """Handles OCR for extracting text from game UI."""

    def __init__(self, upscale_factor: int = 3):
        self.upscale_factor = upscale_factor

    def preprocess(self, image: np.ndarray) -> np.ndarray:
        """
        Preprocess image for OCR.

        Steps:
        1. Upscale for better accuracy
        2. Convert to grayscale
        3. Invert if needed (light text on dark background)
        4. Binarize with Otsu's method
        5. Add padding
        """
        # Upscale
        image = cv2.resize(
            image,
            None,
            fx=self.upscale_factor,
            fy=self.upscale_factor,
            interpolation=cv2.INTER_CUBIC,
        )

        # Grayscale
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image

        # Invert if dark background
        if np.mean(gray) < 128:
            gray = cv2.bitwise_not(gray)

        # Binarize
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        # Add padding
        binary = cv2.copyMakeBorder(
            binary, 10, 10, 10, 10, cv2.BORDER_CONSTANT, value=255
        )

        return binary

    def read_text(
        self,
        image: np.ndarray,
        whitelist: Optional[str] = None,
        psm: int = 7,
    ) -> str:
        """
        Extract text from image.

        Args:
            image: BGR or grayscale image.
            whitelist: Optional character whitelist.
            psm: Page segmentation mode (default: 7 = single line).

        Returns:
            Extracted text string.
        """
        processed = self.preprocess(image)

        config = f"--oem 3 --psm {psm}"
        if whitelist:
            config += f" -c tessedit_char_whitelist={whitelist}"

        # TODO: Implement
        # text = pytesseract.image_to_string(processed, config=config)
        # return text.strip()
        return ""

    def read_player_name(self, image: np.ndarray) -> str:
        """Read a player name (Embark ID format)."""
        whitelist = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789#_-"
        return self.read_text(image, whitelist=whitelist)

    def read_score(self, image: np.ndarray) -> Optional[int]:
        """Read a numeric score."""
        text = self.read_text(image, whitelist="0123456789")
        text = text.replace(",", "").replace(" ", "")
        try:
            return int(text)
        except ValueError:
            return None

    def read_region(
        self,
        frame: np.ndarray,
        region: tuple[int, int, int, int],
        **kwargs,
    ) -> str:
        """Read text from a specific region of the frame."""
        x1, y1, x2, y2 = region
        roi = frame[y1:y2, x1:x2]
        return self.read_text(roi, **kwargs)
