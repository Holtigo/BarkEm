"""
Chat reading and command detection for in-game chat.
"""

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import cv2
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
        drop_top_line: bool = False,
        debug_dump_dir: Optional[str] = None,
    ):
        """
        Initialize chat reader.

        Args:
            chat_region: (x1, y1, x2, y2) bounding box for chat area.
            text_reader: Optional TextReader instance.
            drop_top_line: If True, discard the first OCR line of each
                read.  Only needed when the chat_region is calibrated
                wide enough to clip the top of the oldest visible
                message — OCR then hallucinates nonsense from the
                half-glyphs.  Prefer tightening chat_region so the top
                line is fully visible and leave this off.
            debug_dump_dir: If set, every ``read_chat`` call writes
                three files into this directory — the raw cropped
                chat ROI, the preprocessed (binarized/upscaled) image
                actually handed to tesseract, and a sidecar ``.txt``
                with the raw OCR output.  Use to diagnose why the same
                visible chat reads differently poll-to-poll.
        """
        self.chat_region = chat_region
        self.text_reader = text_reader or TextReader()
        self.drop_top_line = drop_top_line
        self.last_messages: list[ChatMessage] = []
        self._last_raw_text: str = ""
        self._debug_dump_dir: Optional[Path] = (
            Path(debug_dump_dir) if debug_dump_dir else None
        )
        if self._debug_dump_dir is not None:
            self._debug_dump_dir.mkdir(parents=True, exist_ok=True)

    def set_region(self, chat_region: tuple[int, int, int, int]) -> None:
        """
        Swap to a different on-screen chat region.

        The lobby and in-match chat windows have different coordinates
        — callers can reuse a single ChatReader by swapping the region
        between phases.  Resets the "last seen" state so a fresh region
        isn't diffed against a stale one.
        """
        self.chat_region = chat_region
        self.last_messages = []
        self._last_raw_text = ""

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

        # OCR the chat region (block of text mode) using chat-specific
        # V-channel preprocessing — grayscale+Otsu eats the teal names.
        raw_text = self.text_reader.read_chat_text(chat_roi, psm=6)

        if self._debug_dump_dir is not None:
            self._dump_debug(chat_roi, raw_text)

        # Parse into individual messages
        messages = self._parse_chat_text(raw_text)

        return messages

    def _dump_debug(self, chat_roi: np.ndarray, raw_text: str) -> None:
        """
        Dump the chat ROI (raw), the preprocessed image actually sent
        to tesseract, and the returned text for later inspection.
        """
        ts = f"{time.time():.3f}".replace(".", "_")
        base = self._debug_dump_dir / f"chat_{ts}"
        try:
            cv2.imwrite(str(base.with_suffix(".raw.png")), chat_roi)
            processed = self.text_reader.preprocess_chat(chat_roi)
            cv2.imwrite(str(base.with_suffix(".pre.png")), processed)
            base.with_suffix(".txt").write_text(raw_text, encoding="utf-8")
        except Exception:
            # Debug dump must never break the live loop.
            pass

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

        # Top of the chat region usually clips a half-rendered older
        # message — OCR hallucinates gibberish from the half-glyphs.
        if self.drop_top_line and lines:
            lines = lines[1:]

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # The Finals optionally prefixes chat lines with a team/clan
            # tag in brackets or with surrounding punctuation —
            #   "[CLAN] playername -em pause"
            # The real player name is the token AFTER any leading
            # bracketed tag.  Strip it before we split.
            line = self._strip_leading_tag(line)

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

    @staticmethod
    def _strip_leading_tag(line: str) -> str:
        """
        Remove a leading ``[TAG]`` / ``(TAG)`` / ``<TAG>`` prefix plus
        any spacing so the first remaining token is the player name.

        The Finals shows a team/clan/platform tag before the name on
        some chat lines.  OCR reads the whole tag as the first
        whitespace-separated token and mis-attributes the real name
        to the message body.  Handles a few common bracket styles and
        common OCR mangles of brackets (``{``/``}``, ``|``, ``/``).
        """
        stripped = line.lstrip()
        if not stripped:
            return line
        opener = stripped[0]
        pairs = {"[": "]", "(": ")", "<": ">", "{": "}"}
        if opener in pairs:
            closer = pairs[opener]
            end = stripped.find(closer)
            if 0 < end < 40:  # sanity cap — a real tag is short
                return stripped[end + 1:].lstrip()
        return stripped

    def find_command(
        self,
        frame: np.ndarray,
        command: str,
        allowed_players: list[str],
        fuzzy_threshold: int = 80,
    ) -> Optional[tuple[int, int, ChatMessage, str]]:
        """
        Like check_for_command, but returns positional context.

        Returns (index, total_messages, matched_message, captain_id)
        for the *last* matching command in the currently visible chat
        block — or None if no match.

        ``total_messages`` is how many messages are currently visible;
        a caller can treat the match as "fresh" only if there are no
        new messages after it (index == total_messages - 1) AND they
        haven't seen the same (name, message, trailing_context) before.
        """
        messages = self.read_chat(frame)
        total = len(messages)

        for idx in range(total - 1, -1, -1):
            msg = messages[idx]
            if not self._command_matches(msg.message, command, fuzzy_threshold):
                continue
            for player in allowed_players:
                if self._names_match(msg.player_name, player, fuzzy_threshold):
                    return idx, total, msg, player
        return None

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

        STRICT — the ``-em <command>`` (or a tolerated OCR variant) must
        be the *entire* message content.  Embedded commands inside a
        longer sentence are rejected, so captains explaining the syntax
        to teammates ("if you want to pause, type -em pause") won't
        accidentally trigger a pause.

        Still tolerant to normal OCR noise on the edges: a dropped
        leading dash (``em pause``), a trailing ``!`` or ``.``, and a
        single stray 1-character token at the front or back (common
        artifact from avatar/icon pixels bleeding into the OCR).
        """
        message = message.lower().strip()
        command = command.lower().strip()

        # Tokenise on non-alphanumeric so punctuation doesn't split
        # ``em`` and the command, and so ``-em`` and ``em.`` both
        # reduce to the same token stream.
        normalized = "".join(c if c.isalnum() else " " for c in message)
        tokens = [t for t in normalized.split() if t]

        # Strip a single stray 1-char token on either end — these are
        # almost always OCR artifacts (icon fragments, stray ``l``/``i``
        # from the UI chrome) rather than user-typed letters.
        if len(tokens) >= 3 and len(tokens[0]) == 1:
            tokens = tokens[1:]
        if len(tokens) >= 3 and len(tokens[-1]) == 1:
            tokens = tokens[:-1]

        # Must be exactly two tokens: ``em`` and the command.
        if len(tokens) != 2:
            return False
        tok1, tok2 = tokens
        if tok1 != "em":
            return False

        # Exact command match
        if tok2 == command:
            return True

        # Distinctive-substring rules for the pause family (the edit
        # distance between pause and unpause is too small for fuzzy
        # matching to tell them apart reliably).
        #
        #   "unpause" / "unp*" / "unpaus" → always UNPAUSE
        #   "continu*"                    → always CONTINUE
        #   "resume*"                     → always UNPAUSE (alias)
        #   anything starting with "p"
        #     and NOT containing "unp"    → PAUSE
        if command == "unpause":
            if tok2.startswith("unp") or tok2.startswith("resume"):
                return True
            return False
        if command == "continue":
            if tok2.startswith("cont") or tok2.startswith("continu"):
                return True
            return False
        if command == "pause":
            if "unp" in tok2:
                return False
            # "p", "paus", "pause", "pasue" all start with "p"; also
            # accept common one-off OCR artifacts.
            if tok2.startswith("p") and len(tok2) <= 6:
                return True
            return False

        # Non-pause-family commands (e.g. "ready") — fuzzy match.
        abbreviations = {
            "ready": {"rdy", "r", "redy", "redi"},
        }
        if command in abbreviations and tok2 in abbreviations[command]:
            return True
        score = fuzz.ratio(tok2, command)
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
