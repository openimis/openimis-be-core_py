import json

from core.websocket.abstract_websocket_client import AbstractWebSocketClient


class BaseWebSocketClient(AbstractWebSocketClient):
    def receive(self):
        """
        If no receive actions were determined, this method returns all messages received from socket.
        """
        return self.__messages

    def _default_action(self, message):
        self.__messages.append(message)

    def _transform_payload(self, payload):
        return str(payload)


class JsonWebSocketClient(BaseWebSocketClient):

    def _transform_payload(self, payload):
        payload = json.dumps(payload)
        return payload
