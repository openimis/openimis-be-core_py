import concurrent.futures
import asyncio
import logging
import time
from contextlib import asynccontextmanager
from functools import partial, wraps

from typing import Callable, Coroutine

from asgiref.sync import sync_to_async

from core.websocket.base_websocket_client import BaseWebSocketClient

logger = logging.getLogger(__name__)


class AsyncWebSocketClient(BaseWebSocketClient):
    """
    Asynchronous implementation of WebSocket client.
    """

    def add_action_on_receive(self, on_receive_func: Callable[[object], Coroutine]):
        self.recv_actions.append(on_receive_func)

    async def send(self, payload):
        super().send(payload)

    def _on_recv(self, message):
        # Through to build of websockets.WebSocketApp async cannot be used directly

        # tasks = asyncio.gather(**self.recv_actions)
        loop = asyncio.new_event_loop()
        try:
            for action in self.recv_actions:
                loop.run_until_complete(action(message))
        except Exception as e:
            logger.error(F'Failed to execute action, reason: {e}')
        finally:
            loop.close()
        if not self.recv_actions:
            self._default_action(message)

    @asynccontextmanager
    async def connect(self):
        """
        Allows to use asynchronous context manager.
        Example:
            async with client_instance.connect() as connection:
                connection.send("Hello world")

        """
        self.open_connection()
        try:
            yield self
        finally:
            self.close_connection()

    async def __aenter__(self):
        self.open_connection()
        await self

    async def __aexit__(self, exc_type, exc, tb):
        await self.close_connection()
