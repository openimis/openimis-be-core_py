from django.dispatch import Signal as BaseSignal
from django.dispatch.dispatcher import _make_id
import functools

from typing import Callable, Dict

from core.service_signals import RegisteredServiceSignal, ServiceSignalBindType


class Signal(BaseSignal):

    def connect(self, receiver, sender=None, weak=True, dispatch_uid=None, priority=50):
        if dispatch_uid is None:
            dispatch_uid = _make_id(receiver)

        inner_uid = '{0}{1}'.format(priority, dispatch_uid)
        super(Signal, self).connect(receiver, sender=sender, weak=weak, dispatch_uid=inner_uid)
        self.receivers.sort()


REGISTERED_SERVICE_SIGNALS: Dict[str, RegisteredServiceSignal] = {}


def __register_service_signal(signal_name, providing_args):
    signal = REGISTERED_SERVICE_SIGNALS.get(signal_name)
    if signal_name in REGISTERED_SERVICE_SIGNALS:
        if signal.is_signal_registered():
            raise AttributeError(F'Signal name {signal_name} clashes with already existing '
                                 F'signal name {REGISTERED_SERVICE_SIGNALS[signal_name]} and can\'t be registered.')
        else:
            signal.register_signal(providing_args)
    else:
        REGISTERED_SERVICE_SIGNALS[signal_name] = RegisteredServiceSignal(providing_args)


def __raise_unregistered_signal_exception(signal_name):
    raise ValueError(f"Signal for name {signal_name} not found. Was it registered?"
                     f"Note: Classes/functions wrapped in register_service_signal have to be imported in "
                     f"signals.py, as Django doesn't fetch all classes definitions at initializations. Therefore, "
                     f"signal is only registered after import and class definition.")


def register_service_signal(signal_name: str):
    """
    Decorator for registering signals for service. Two signals will be created: one before service and one after.
    Signals are stored in core.signals.REGISTERED_SERVICE_SIGNALS as RegisteredServiceSignal.
    See RegisteredServiceSignal class definition for more information regarding when signals are registered
    and connected. Signal receivers output is stored in RegisteredServiceSignal.signal_results. Results are
    overridden after very call.

    Example use:
        @register_service_signal('create_policy', PolicyServiceClass):
        def create_policy(self, *args, **kwargs)
            ...

        Will create new RegisteredServiceSignal instance available from  REGISTERED_SERVICE_SIGNALS['create_policy'].
        Signal name has to be unique.

    """
    __register_service_signal(signal_name, ['cls_', 'data', 'context'])

    def decorator(func):
        @functools.wraps(func)
        def wrapper_do_twice(*args, **kwargs):
            registered_signal = REGISTERED_SERVICE_SIGNALS.get(signal_name, None)
            if registered_signal is None:
                __raise_unregistered_signal_exception(signal_name)

            context = kwargs.pop('context', None)
            cls_, func_args = args[0], args[1:]  # First element of args is self/cls. Moved to separate variable.
            signal_call_args = {'cls_': cls_, 'data': [func_args, kwargs], 'context': context}

            registered_signal.send_signal_before(sender=cls_, **signal_call_args)

            out = func(*args, **kwargs)

            signal_call_args['result'] = out
            registered_signal.send_signal_after(sender=cls_, **signal_call_args)
            return out
        return wrapper_do_twice

    return decorator


def bind_service_signal(signal_name: str, func: Callable,
                        bind_type: ServiceSignalBindType = ServiceSignalBindType.BEFORE_AND_AFTER):
    """
    By default binding is done after modules are loaded, with same similar approach as for graphql.
    Main OpenIMIS backend is crawling through modules searching for bind_service_signals function
    in module_name.signals path. In most cases function connected to signal will be loaded before signals are
    registered. They're queued and connected after signal definition is provided.

    Example:
        Content of openimis-be-invoice_py/invoice/signals.py:
        from core.signals import bind_service_signal
        def bind_service_signals():
            bind_service_signal('create_signal', connected_signal_function)

    @param signal_name:
    @param func:
    @param bind_type:
    @return:
    """
    if signal_name not in REGISTERED_SERVICE_SIGNALS.keys():
        __register_service_signal(signal_name, None)

    signal = REGISTERED_SERVICE_SIGNALS[signal_name]
    signal.connect_signal(func, bind_type)
