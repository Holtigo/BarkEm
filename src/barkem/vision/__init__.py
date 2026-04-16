"""
Vision module — Screen capture, template matching, OCR, chat reading, and state detection.
"""

from barkem.vision.capture import ScreenCapture
from barkem.vision.templates import TemplateMatcher
from barkem.vision.ocr import TextReader
from barkem.vision.chat import ChatReader, CommandMonitor
from barkem.vision.state_detector import GameStateDetector, GameScreen
from barkem.vision.regions import ScreenRegions, Region, ContextMenuRegions, load_regions_from_dict

__all__ = [
    "ScreenCapture",
    "TemplateMatcher",
    "TextReader",
    "ChatReader",
    "CommandMonitor",
    "GameStateDetector",
    "GameScreen",
    "ScreenRegions",
    "Region",
    "ContextMenuRegions",
    "load_regions_from_dict",
]
