import queue

from enum import Enum

from django import dispatch
from typing import Callable


class ServiceSignalBindType(Enum):
    BEFORE = 0
    AFTER = 1
    BEFORE_AND_AFTER = 2


class RegisteredServiceSignal:

    def __init__(self, providing_args=None):
        """
        Due to how python manage class prototypes, there's a chance that class definition using register_service_signal
        will not be loaded until first import of given class. Therefore it's likely that binding function responsible
        for loading functions called before/after signal will be invoked before signal register. In this case functions
        are queued and connected to actual signal after the registration. Whether or not registration took place
        is defined by providing_args. If argument is None, signal is considered not registered.
        """
        self.__signal_results = {'before': None, 'after': None}
        self.__connection_queue = {type_: queue.Queue() for type_ in ServiceSignalBindType}
        self.__signals_before = []
        self.__signals_after = []

        if not providing_args:
            self.__before_service_signal = None
            self.__after_service_signal = None
        else:
            self.__before_service_signal = dispatch.Signal(providing_args=providing_args)
            self.__after_service_signal = dispatch.Signal(providing_args=providing_args + ['result'])

    @property
    def connected_signals(self):
        return {
            'before': self.__signals_before,
            'after': self.__signals_after
        }

    def send_signal_before(self, sender, **signal_call_args):
        result = self.before_service_signal.send(sender=sender, **signal_call_args)
        self.__signal_results['before'] = result

    def send_signal_after(self, sender, **signal_call_args):
        result = self.after_service_signal.send(sender=sender, **signal_call_args)
        self.__signal_results['after'] = result

    @property
    def signal_results(self):
        return self.__signal_results

    @property
    def before_service_signal(self):
        return self.__before_service_signal

    @property
    def after_service_signal(self):
        return self.__after_service_signal

    def connect_signal(self, func: Callable, bind_type: ServiceSignalBindType = ServiceSignalBindType.BEFORE_AND_AFTER):
        if self.is_signal_registered():
            self._add_connection(func, bind_type)
        else:
            self.__connection_queue[bind_type].put(func)

    def register_signal(self, providing_args):
        if self.is_signal_registered():
            raise ValueError(f"Signal {self} already registered.")

        self.__before_service_signal = dispatch.Signal(providing_args=providing_args)
        self.__after_service_signal = dispatch.Signal(providing_args=providing_args + ['result'])
        self._connect_queued()

    def is_signal_registered(self):
        return self.__before_service_signal is not None and self.__after_service_signal is not None

    def _add_connection(self, func, bind_type):
        if bind_type == ServiceSignalBindType.BEFORE:
            self.__before_service_signal.connect(func)
            self.__signals_before.append(func)
        elif bind_type == ServiceSignalBindType.AFTER:
            self.__after_service_signal.connect(func)
            self.__signals_after.append(func)
        elif bind_type == ServiceSignalBindType.BEFORE_AND_AFTER:
            self.__before_service_signal.connect(func)
            self.__after_service_signal.connect(func)
            self.__signals_after.append(func)
            self.__signals_before.append(func)
        else:
            raise AttributeError(f"Invalid bind_type {bind_type}, should be one of {ServiceSignalBindType}.")

    def _connect_queued(self):
        for binding_type, awaiting_queue in self.__connection_queue.items():
            while not awaiting_queue.empty():
                self.connect_signal(awaiting_queue.get(), binding_type)
