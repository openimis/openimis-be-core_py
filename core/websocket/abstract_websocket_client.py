from abc import ABC
from contextlib import contextmanager

import websocket
from typing import Union, Callable

try:
    import thread
except ImportError:
    import _thread as thread


class AbstractWebSocketClient(ABC):
    """
    Abstract client for creating websocket clients.
    """

    def __init__(self, socket_url):
        self.socket_url = socket_url
        self.recv_actions = []
        self.close_actions = []
        self.__messages = []
        self.recv_actions = []
        self.websocket = None

    def open_connection(self):
        """
        Opens connection with socket endpoint. Connection has to be opened before any message is sent.
        """
        if not self.websocket:
            ws = websocket.WebSocketApp(self.socket_url,
                                        on_message=lambda ws, msg: self._on_recv(msg),
                                        on_close=lambda: self._on_close(),
                                        )
            self.websocket = ws
            thread.start_new_thread(self.websocket.run_forever, ())

    def close_connection(self):
        """
        Closes connection with websocket
        """
        if self.websocket:
            self.websocket.close()
        self.websocket = None

    def send(self, payload):
        """
        Transforms payload and sends it to the websocket.
        After calling transformation on payload it has to be bytes or str type.
        Otherwise exception is raised.

        :param : Content of the request
        :raises NotImplementedError: when payload has invalid type
        """
        payload = self._transform_payload(payload)
        if type(payload) == bytes:
            self.websocket.send(payload, websocket.ABNF.OPCODE_BINARY)
        elif type(payload) == str:
            self.websocket.send(payload, websocket.ABNF.OPCODE_TEXT)
        else:
            raise NotImplementedError(F"Sending payload of type {type(payload)} not supported")

    def is_open(self):
        """
        Checks if connection to socket is opened.

        :return: True if connection is opened.
        """
        if not self.websocket:
            return False
        else:
            sock = self.websocket.sock
            return sock and sock.connected

    def add_action_on_receive(self, on_receive_func: Callable[[object], None]):
        """
        Functions added through this method are called after payload from socket endpoint is received.

        :param on_receive_func: one argument function, takes socket payload as argument
        """
        self.recv_actions.append(on_receive_func)

    def add_action_on_close(self, on_close_func: Callable):
        """
        Functions added through this method are called when connection with socket is closed.

        :param on_close_func: function with no arguments
        """
        self.close_actions.append(on_close_func)

    def _on_recv(self, message):
        """
        Called after the message is received. If no receive actions were determined it
        adds content of message to __messages.

        :param message: Content of message received from socket.
        """
        for action in self.recv_actions:
            action(message)
        if not self.recv_actions:
            self._default_action(message)

    def _on_close(self):
        """
        Called on connection closing.
        """
        for action in self.close_actions:
            action()
        if not self.close_actions:
            pass

    def _default_action(self, message):
        raise NotImplementedError("Default action has to be implemented")

    def _transform_payload(self, payload):
        """
        Used in send method, used for transforming payload before sending it.
        @param payload: Payload
        @return: Transformed payload
        """
        raise NotImplementedError("Transforming payload has to be implemented")

    @contextmanager
    def connect(self):
        """
        Context manager that allows to use client in with context. On entry it opens connection and close it on exit.
        Example:
            with client_instance.connect() as connection:
                connection.send("Hello world")

        """
        self.open_connection()
        try:
            yield self
        finally:
            self.close_connection()

    def __enter__(self):
        self.open_connection()
        return self

    def __exit__(self, type, value, traceback):
        self.close_connection()
