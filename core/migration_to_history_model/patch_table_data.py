from django.db import models
from simple_history.utils import get_history_model_for_model


class Patcher:
    """
    Patcher is meant to be used only in context of migration. It relies on temporary transition tables
    that are meant to be removed after migration process is done.
    """

    def __init__(self, model):
        self.model = model

    def patch_data(self):
        self._move_not_valid_entries_to_historical_table()

    def _move_not_valid_entries_to_historical_table(self):
        history_model = get_history_model_for_model(self.model)
        data_fields = [x.name for x in self.model._meta.get_fields() if isinstance(x, models.fields.Field)]
        print(data_fields)

