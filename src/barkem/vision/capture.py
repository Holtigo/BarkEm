"""
Screen capture using DXcam.
"""

from typing import Optional

import numpy as np

# TODO: Import when implementing
# import dxcam


class ScreenCapture:
    """Handles screen capture using DXGI Desktop Duplication API."""

    def __init__(self, target_fps: int = 10):
        self.target_fps = target_fps
        self._camera = None

    def start(self) -> None:
        """Initialize the capture device."""
        # TODO: Implement
        # self._camera = dxcam.create(output_color="BGR")
        pass

    def stop(self) -> None:
        """Release the capture device."""
        # TODO: Implement
        pass

    def grab(self, region: Optional[tuple[int, int, int, int]] = None) -> Optional[np.ndarray]:
        """
        Capture a frame from the screen.

        Args:
            region: Optional (x1, y1, x2, y2) tuple to capture specific region.

        Returns:
            BGR numpy array of the captured frame, or None if capture failed.
        """
        # TODO: Implement
        # return self._camera.grab(region=region)
        pass

    def __enter__(self) -> "ScreenCapture":
        self.start()
        return self

    def __exit__(self, *args) -> None:
        self.stop()
