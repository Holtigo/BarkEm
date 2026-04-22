"""
OCR for reading player names, lobby codes, and scores.

Tesseract path is set explicitly to avoid PATH issues.
Configure via settings.yaml: vision.tesseract_cmd
"""

from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np
import pytesseract


@dataclass
class OCRResult:
    """Result of an OCR operation."""

    text: str
    confidence: float
    region: tuple[int, int, int, int]


class TextReader:
    """Handles OCR for extracting text from game UI."""

    def __init__(
            self,
            upscale_factor: int = 3,
            tesseract_cmd: Optional[str] = None,
    ):
        """
        Initialize the text reader.

        Args:
            upscale_factor: How much to upscale images before OCR.
            tesseract_cmd: Explicit path to tesseract.exe.
                           Defaults to standard Windows install location.
        """
        self.upscale_factor = upscale_factor

        # Set Tesseract path explicitly — no PATH required
        if tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
        else:
            # Default Windows install location
            pytesseract.pytesseract.tesseract_cmd = (
                r"C:\Program Files\Tesseract-OCR\tesseract.exe"
            )

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

    def preprocess_chat(
        self,
        image: np.ndarray,
        v_threshold: int = 130,
    ) -> np.ndarray:
        """
        Preprocess chat-region images using the HSV value channel.

        The Finals renders chat with two foreground colors: a saturated
        teal (~hsl(171,65%,45%), V≈190) for player names and near-white
        (~hsl(180,100%,98%), V≈250) for message bodies.  The background
        is a semi-transparent dark overlay that sits at V≈40–80 on top
        of whatever game world is behind it.

        ``cvtColor(..., COLOR_BGR2GRAY)`` collapses the teal and the
        dark background into overlapping gray values, and Otsu's
        single-cutoff threshold then splits between *teal names* and
        *white messages* — turning names into background and dropping
        the first letter of every message at the teal→white transition.

        The fix: threshold on ``V = max(B, G, R)`` instead.  Both
        foreground colors sit well above 130; the background sits
        well below.  A fixed cutoff separates them cleanly regardless
        of what's behind the chat window (fire, sky, snow — doesn't
        matter, the HUD overlay keeps the background dim).
        """
        image = cv2.resize(
            image,
            None,
            fx=self.upscale_factor,
            fy=self.upscale_factor,
            interpolation=cv2.INTER_CUBIC,
        )

        if len(image.shape) == 3:
            v = image.max(axis=2)
        else:
            v = image

        # Foreground (names + text) is bright → mask to 0, background
        # to 255 so tesseract sees dark text on light.
        _, binary = cv2.threshold(v, v_threshold, 255, cv2.THRESH_BINARY_INV)

        # The teal name color renders with thinner strokes than the
        # white message body.  Dilate 1px (on the inverted "ink"
        # channel) so names don't get read as thinner lookalikes
        # (S↔5, O↔0, etc.).  On the upscaled image one dilation pass
        # thickens strokes by a fraction of a glyph-width, which is
        # enough to stabilize character identity without merging
        # adjacent letters.
        inked = cv2.bitwise_not(binary)
        kernel = np.ones((2, 2), np.uint8)
        inked = cv2.dilate(inked, kernel, iterations=1)
        binary = cv2.bitwise_not(inked)

        binary = cv2.copyMakeBorder(
            binary, 10, 10, 10, 10, cv2.BORDER_CONSTANT, value=255
        )
        return binary

    def read_chat_text(
        self,
        image: np.ndarray,
        psm: int = 6,
        v_threshold: int = 130,
    ) -> str:
        """OCR a chat ROI using V-channel preprocessing."""
        processed = self.preprocess_chat(image, v_threshold=v_threshold)
        config = f"--oem 3 --psm {psm}"
        text = pytesseract.image_to_string(processed, config=config)
        return text.strip()

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
            psm: Page segmentation mode.
                 7 = single line (for names, codes).
                 6 = block of text (for chat).

        Returns:
            Extracted text string.
        """
        processed = self.preprocess(image)

        config = f"--oem 3 --psm {psm}"
        if whitelist:
            config += f" -c tessedit_char_whitelist={whitelist}"

        text = pytesseract.image_to_string(processed, config=config)
        return text.strip()

    def read_text_with_confidence(
            self,
            image: np.ndarray,
            whitelist: Optional[str] = None,
            psm: int = 7,
    ) -> OCRResult:
        """
        Extract text with confidence score.

        Args:
            image: BGR or grayscale image.
            whitelist: Optional character whitelist.
            psm: Page segmentation mode.

        Returns:
            OCRResult with text and confidence.
        """
        processed = self.preprocess(image)

        config = f"--oem 3 --psm {psm}"
        if whitelist:
            config += f" -c tessedit_char_whitelist={whitelist}"

        # Get detailed data
        data = pytesseract.image_to_data(
            processed, config=config, output_type=pytesseract.Output.DICT
        )

        # Combine text and calculate average confidence
        words = []
        confidences = []
        for i, text in enumerate(data["text"]):
            text = text.strip()
            if text:
                words.append(text)
                conf = int(data["conf"][i])
                if conf > 0:
                    confidences.append(conf)

        combined_text = " ".join(words)
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

        return OCRResult(
            text=combined_text,
            confidence=avg_confidence,
            region=(0, 0, image.shape[1], image.shape[0]),
        )

    def read_player_name(self, image: np.ndarray) -> str:
        """Read a player name (Embark ID format: PlayerName#1234)."""
        whitelist = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789#_-"
        return self.read_text(image, whitelist=whitelist)

    def read_lobby_code(self, image: np.ndarray) -> str:
        """Read the 4-character alphanumeric lobby code."""
        whitelist = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        text = self.read_text(image, whitelist=whitelist)
        # Remove any spaces/noise and take first 4 chars
        text = text.replace(" ", "").strip()
        return text[:4] if len(text) >= 4 else text

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

    def read_region_with_confidence(
            self,
            frame: np.ndarray,
            region: tuple[int, int, int, int],
            **kwargs,
    ) -> OCRResult:
        """Read text with confidence from a specific region of the frame."""
        x1, y1, x2, y2 = region
        roi = frame[y1:y2, x1:x2]
        result = self.read_text_with_confidence(roi, **kwargs)
        # Update region to match the frame coordinates
        result.region = (x1, y1, x2, y2)
        return result