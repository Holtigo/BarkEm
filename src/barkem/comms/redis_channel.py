"""
Inter-bot communication via Redis Pub/Sub.
"""

import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Optional

# TODO: Import when implementing
# import redis.asyncio as redis


class MessageType(Enum):
    """Types of inter-bot messages."""

    # Orchestrator -> Child
    TEAM2_ASSIGNMENT = "team2_assignment"
    LOBBY_CODE = "lobby_code"
    TEAMS_PLACED = "teams_placed"

    # Child -> Orchestrator
    TEAM2_READY = "team2_ready"
    JOINED_LOBBY = "joined_lobby"
    LEFT_LOBBY = "left_lobby"

    # Both
    PING = "ping"
    PONG = "pong"
    ERROR = "error"


@dataclass
class Message:
    """Inter-bot message."""

    type: MessageType
    sender_id: str
    payload: dict
    timestamp: float


class RedisChannel:
    """
    Handles Redis Pub/Sub communication between bots.

    Channels:
    - barkem:orchestrator:{id} - Messages to a specific orchestrator
    - barkem:child:{id} - Messages to a specific child bot
    - barkem:broadcast - Broadcast messages
    """

    def __init__(
        self,
        bot_id: str,
        bot_type: str,  # "orchestrator" or "child"
        redis_url: str = "redis://localhost:6379",
        channel_prefix: str = "barkem",
    ):
        self.bot_id = bot_id
        self.bot_type = bot_type
        self.redis_url = redis_url
        self.channel_prefix = channel_prefix
        self._client: Optional[Any] = None  # redis.Redis
        self._pubsub: Optional[Any] = None
        self._handlers: dict[MessageType, Callable] = {}

    @property
    def my_channel(self) -> str:
        """Get this bot's channel name."""
        return f"{self.channel_prefix}:{self.bot_type}:{self.bot_id}"

    def target_channel(self, bot_type: str, bot_id: str) -> str:
        """Get channel name for a target bot."""
        return f"{self.channel_prefix}:{bot_type}:{bot_id}"

    async def connect(self) -> None:
        """Connect to Redis."""
        # TODO: Implement
        # self._client = redis.from_url(self.redis_url)
        # self._pubsub = self._client.pubsub()
        # await self._pubsub.subscribe(self.my_channel)
        pass

    async def disconnect(self) -> None:
        """Disconnect from Redis."""
        # TODO: Implement
        pass

    def on(self, message_type: MessageType, handler: Callable) -> None:
        """Register a handler for a message type."""
        self._handlers[message_type] = handler

    async def send(
        self,
        target_type: str,
        target_id: str,
        message_type: MessageType,
        payload: dict,
    ) -> None:
        """
        Send a message to another bot.

        Args:
            target_type: "orchestrator" or "child"
            target_id: Target bot's ID
            message_type: Type of message
            payload: Message data
        """
        # TODO: Implement
        pass

    async def broadcast(self, message_type: MessageType, payload: dict) -> None:
        """Broadcast a message to all bots."""
        # TODO: Implement
        pass

    async def listen(self) -> None:
        """Listen for incoming messages."""
        # TODO: Implement message listening loop
        pass

    async def ping(self, target_type: str, target_id: str) -> bool:
        """
        Ping another bot to check if it's alive.

        Returns:
            True if pong received, False otherwise.
        """
        # TODO: Implement
        return False
