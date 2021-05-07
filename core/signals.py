from django.dispatch import Signal as BaseSignal
from django.dispatch.dispatcher import _make_id


class Signal(BaseSignal):

    def connect(self, receiver, sender=None, weak=True, dispatch_uid=None, priority=50):
        if dispatch_uid is None:
            dispatch_uid = _make_id(receiver)

        inner_uid = '{0}{1}'.format(priority, dispatch_uid)
        super(Signal, self).connect(receiver, sender=sender, weak=weak, dispatch_uid=inner_uid)
        self.receivers.sort()