
class ObjectNotExistException(Exception):

    def __init__(self, model, uuid):
        self.model = model
        self.uuid = uuid
        self.message = '{model} with uuid {uuid} does not exist'\
            .format(model=self.model, uuid=self.uuid)
        super().__init__(self.message)


class MutationValidationException(Exception):

    def __init__(self, mutated_object, *invalidation_reasons):
        self.mutated_object = mutated_object
        self.errors = invalidation_reasons
        self.message = self._build_error_msg()
        super().__init__(self.message)

    def _build_error_msg(self):
        msg = ",\n".join(self.errors)
        return "Validation during a mutation has failed, reason:\n" \
               "{msg}".format(msg=msg)
