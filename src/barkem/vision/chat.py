"""
Chat reading and command detection for in-game chat.
"""

import time
from dataclasses import dataclass
from typing import Optional

import numpy as np
from rapidfuzz import fuzz

from barkem.vision.ocr import TextReader


@dataclass
class ChatMessage:
    """A parsed chat message."""

    player_name: str
    message: str
    timestamp: float
    raw_text: str = ""


class ChatReader:
    """
    Reads and parses game chat messages from the screen.

    The chat appears in a fixed region (bottom-left corner) with format:
    PlayerName#1234: message text here
    """

    def __init__(
        self,
        chat_region: tuple[int, int, int, int],
        text_reader: Optional[TextReader] = None,
    ):
        """
        Initialize chat reader.

        Args:
            chat_region: (x1, y1, x2, y2) bounding box for chat area.
            text_reader: Optional TextReader instance.
        """
        self.chat_region = chat_region
        self.text_reader = text_reader or TextReader()
        self.last_messages: list[ChatMessage] = []
        self._last_raw_text: str = ""

    def read_chat(self, frame: np.ndarray) -> list[ChatMessage]:
        """
        Read all visible chat messages from frame.

        Args:
            frame: BGR screenshot of the game.

        Returns:
            List of parsed chat messages.
        """
        x1, y1, x2, y2 = self.chat_region
        chat_roi = frame[y1:y2, x1:x2]

        # OCR the chat region (block of text mode)
        raw_text = self.text_reader.read_text(chat_roi, psm=6)

        # Parse into individual messages
        messages = self._parse_chat_text(raw_text)

        return messages

    def read_new_messages(self, frame: np.ndarray) -> list[ChatMessage]:
        """
        Read chat and return only new messages since last read.

        Args:
            frame: BGR screenshot of the game.

        Returns:
            List of new chat messages.
        """
        current_messages = self.read_chat(frame)

        # Simple diff: compare raw text
        new_messages = []
        for msg in current_messages:
            if not self._message_seen(msg):
                new_messages.append(msg)

        # Update last seen
        self.last_messages = current_messages

        return new_messages

    def _message_seen(self, message: ChatMessage) -> bool:
        """Check if we've already seen this message."""
        for prev in self.last_messages:
            if (
                prev.player_name == message.player_name
                and prev.message == message.message
            ):
                return True
        return False

    def _parse_chat_text(self, raw_text: str) -> list[ChatMessage]:
        """
        Parse raw OCR text into chat messages.

        The Finals renders chat as ``Name message`` (no colon, no ``#tag`` —
        the discriminator that appears on every Embark ID is stripped in
        chat).  The first whitespace-separated token is the sender's
        display name; everything after it is the message.

        Some clients / OCR passes will occasionally include a colon
        (``Name: message``) — we handle that too by treating the colon
        as an optional separator.

        Args:
            raw_text: Raw OCR output from chat region.

        Returns:
            List of parsed ChatMessage objects.
        """
        messages = []
        lines = raw_text.strip().split("\n")

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Split on the first whitespace run — "Name message" → ("Name", "message")
            parts = line.split(None, 1)
            if len(parts) != 2:
                continue
            player_name, message_text = parts[0].strip(), parts[1].strip()

            # Some chat variants keep the colon: "Name: message" → "Name:"
            # Strip a trailing colon from the name token.
            if player_name.endswith(":"):
                player_name = player_name[:-1].strip()

            if not player_name or not message_text:
                continue

            # Guard against single-character OCR noise being mistaken for a name.
            if len(player_name) < 2:
                continue

            messages.append(
                ChatMessage(
                    player_name=player_name,
                    message=message_text,
                    timestamp=time.time(),
                    raw_text=line,
                )
            )

        return messages

    def check_for_command(
        self,
        frame: np.ndarray,
        command: str,
        allowed_players: list[str],
        fuzzy_threshold: int = 80,
        only_new: bool = False,
    ) -> Optional[str]:
        """
        Check if any allowed player sent a specific command.

        Args:
            frame: BGR screenshot of the game.
            command: Command to look for (e.g., "ready", "pause").
            allowed_players: List of Embark IDs who can trigger this command.
            fuzzy_threshold: Minimum fuzzy match score (0-100).
            only_new: If True, only inspect messages not seen in the prior
                poll.  Default False — The Finals' chat fades fast, so for
                ready detection we want to accept *any currently visible*
                matching message.  Set True for pause/unpause-style
                edge-triggered commands where re-firing must not be
                counted twice in a row.

        Returns:
            The matched player's Embark ID if found, None otherwise.
        """
        messages = (
            self.read_new_messages(frame) if only_new else self.read_chat(frame)
        )

        for msg in messages:
            # Check if message matches command (with fuzzy matching for typos)
            if self._command_matches(msg.message, command, fuzzy_threshold):
                # Check if player is allowed
                for player in allowed_players:
                    if self._names_match(msg.player_name, player, fuzzy_threshold):
                        return player

        return None

    def _command_matches(
            self, message: str, command: str, threshold: int = 80
    ) -> bool:
        """
        Check if a message matches a command with -em prefix.

        Tolerant to common OCR distortions: missing dash (``em ready``),
        missing space (``-emready``), trailing punctuation (``ready!``),
        and the discriminator absence that's normal in chat.
        """
        message = message.lower().strip()
        command = command.lower().strip()
        expected = f"-em {command}"

        # Exact match
        if message == expected:
            return True

        # Substring match — catches OCR stray prefixes/suffixes and the
        # discriminator-less forms (``em ready`` as well as ``-em ready``).
        # Collapse whitespace + strip non-alphanumerics to compare cores.
        def _core(s: str) -> str:
            return "".join(c for c in s if c.isalnum())

        if _core(expected) in _core(message):
            return True
        # Also accept "em ready" (dash dropped) at a word boundary
        if ("em " + command) in message:
            return True

        # Common abbreviations (with prefix)
        abbreviations = {
            "ready": ["-em rdy", "-em r", "-em ready!", "em ready", "emready"],
            "pause": ["-em p", "-em paus", "em pause"],
            "unpause": ["-em unp", "-em resume", "-em unpasue", "em unpause"],
        }

        if command in abbreviations:
            if message in abbreviations[command]:
                return True

        # Fuzzy match against expected (with prefix)
        score = fuzz.ratio(message, expected)
        return score >= threshold

    def _names_match(self, ocr_name: str, expected_name: str, threshold: int = 70) -> bool:
        """
        Fuzzy match player names to handle OCR errors.

        Args:
            ocr_name: Name as read by OCR.
            expected_name: Expected Embark ID.
            threshold: Minimum fuzzy match score.

        Returns:
            True if names match within threshold.
        """
        # Normalize
        ocr_name = ocr_name.lower().strip()
        expected_name = expected_name.lower().strip()

        # Exact match
        if ocr_name == expected_name:
            return True

        # Try matching without discriminator (the #1234 part)
        ocr_base = ocr_name.split("#")[0] if "#" in ocr_name else ocr_name
        expected_base = expected_name.split("#")[0] if "#" in expected_name else expected_name

        if ocr_base == expected_base:
            return True

        # Fuzzy match
        score = fuzz.ratio(ocr_name, expected_name)
        if score >= threshold:
            return True

        # Try fuzzy on base names only
        base_score = fuzz.ratio(ocr_base, expected_base)
        return base_score >= threshold


class CommandMonitor:
    """
    Monitors chat for captain commands during a match.

    Tracks ready status for both teams and handles pause/unpause requests.
    """

    def __init__(
        self,
        captain1: str,
        captain2: str,
        chat_reader: ChatReader,
    ):
        """
        Initialize command monitor.

        Args:
            captain1: Team 1 captain's Embark ID.
            captain2: Team 2 captain's Embark ID.
            chat_reader: ChatReader instance.
        """
        self.captains = {
            "team1": captain1,
            "team2": captain2,
        }
        self.chat_reader = chat_reader
        self.ready_status = {"team1": False, "team2": False}
        self.last_pause_time: float = 0
        self.pause_cooldown: float = 30.0  # Minimum seconds between pauses

    def check_ready(self, frame: np.ndarray) -> bool:
        """
        Check if both teams are ready.

        Args:
            frame: BGR screenshot of the game.

        Returns:
            True when both captains have said "ready".
        """
        for team, captain in self.captains.items():
            if not self.ready_status[team]:
                result = self.chat_reader.check_for_command(
                    frame, "ready", [captain]
                )
                if result:
                    self.ready_status[team] = True

        return all(self.ready_status.values())

    def check_pause(self, frame: np.ndarray) -> Optional[str]:
        """
        Check if any captain requested pause.

        Args:
            frame: BGR screenshot of the game.

        Returns:
            Captain's Embark ID if pause requested, None otherwise.
        """
        # Check cooldown
        if time.time() - self.last_pause_time < self.pause_cooldown:
            return None

        result = self.chat_reader.check_for_command(
            frame, "pause", list(self.captains.values())
        )

        if result:
            self.last_pause_time = time.time()

        return result

    def check_unpause(self, frame: np.ndarray) -> Optional[str]:
        """
        Check if any captain requested unpause.

        Args:
            frame: BGR screenshot of the game.

        Returns:
            Captain's Embark ID if unpause requested, None otherwise.
        """
        return self.chat_reader.check_for_command(
            frame, "unpause", list(self.captains.values())
        )

    def reset(self) -> None:
        """Reset ready status for a new match."""
        self.ready_status = {"team1": False, "team2": False}
        self.last_pause_time = 0
