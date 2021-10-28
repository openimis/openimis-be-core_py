from django.db import transaction

from core import TimeUtils
from core.schema import OpenIMISMutation
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ValidationError
from core.gql.gql_mutations import ObjectNotExistException


class BaseMutation(OpenIMISMutation):

    @property
    def _mutation_class(self):
        raise NotImplementedError()

    @property
    def _model(self):
        raise NotImplementedError()

    @classmethod
    def async_mutate(cls, user, **data):
        try:
            cls._validate_mutation(user, **data)
            mutation_result = cls._mutate(user, **data)
            return mutation_result
        except Exception as exc:
            return [{
                'message': "Failed to process {} mutation".format(cls._mutation_class),
                'detail': str(exc)}]

    @classmethod
    def _validate_mutation(cls, user, **data):
        raise NotImplementedError()

    @classmethod
    def _mutate(cls, user, **data):
        raise NotImplementedError()


class BaseDeleteMutation(BaseMutation):

    class Input:
        pass

    @classmethod
    def async_mutate(cls, user, **data):
        output = []
        if "uuids" in data:
           for uuid in data["uuids"]:
               deletion_result = super(BaseDeleteMutation, cls)\
                   .async_mutate(user, uuid=uuid)
               deletion_result = [None] if deletion_result is None else ["error"]
               output += deletion_result
           return None if output == [None] * len(output) else output


class BaseReplaceMutation(BaseMutation):

    class Input:
        pass

    @classmethod
    def async_mutate(cls, user, **data):
        try:
            cls._validate_mutation(user, **data)
            mutation_result = cls._mutate(user, **data)
            return mutation_result
        except Exception as exc:
            return [{
                'message': "Failed to process {} mutation".format(cls._mutation_class),
                'detail': str(exc)}]


class BaseCreateMutationMixin:

    @property
    def _model(self):
        raise NotImplementedError()

    @classmethod
    def _validate_mutation(cls, user, **data):
        if type(user) is AnonymousUser or not user.id:
            raise ValidationError("mutation.authentication_required")

    @classmethod
    def _mutate(cls, user, **data):
        data['user_created'] = user.id_for_audit
        data['date_created'] = TimeUtils.now()

        if "client_mutation_id" in data:
            data.pop('client_mutation_id')
        if "client_mutation_label" in data:
            data.pop('client_mutation_label')
        cls.create_object(data)

    @classmethod
    def create_object(cls, object_data):
        obj = cls._model.objects.create(**object_data)
        obj.save()
        return obj


class BaseUpdateMutationMixin:

    @property
    def _model(self):
        raise NotImplementedError()

    @classmethod
    def _object_not_exist_exception(cls, obj_uuid):
        raise ObjectNotExistException(cls._model, obj_uuid)

    @classmethod
    def _validate_mutation(cls, user, **data):
        if type(user) is AnonymousUser or not user.id:
            raise ValidationError("mutation.authentication_required")

        obj_uuid = data['uuid']
        if cls._model.objects.filter(uuid=data['uuid']).first() is None:
            cls._object_not_exist_exception(obj_uuid=obj_uuid)

    @classmethod
    def _mutate(cls, user, **data):
        if "client_mutation_id" in data:
            data.pop('client_mutation_id')
        if "client_mutation_label" in data:
            data.pop('client_mutation_label')

        data['user_updated'] = user.id_for_audit
        data['date_updated'] = TimeUtils.now()
        updated_object = cls._model.objects.filter(uuid=data['uuid']).first()
        [setattr(updated_object, key, data[key]) for key in data]
        cls.update_object(updated_object)

    @classmethod
    def update_object(cls, object_to_update):
        object_to_update.save_history()
        object_to_update.save()
        return object_to_update


class BaseDeleteMutationMixin:
    @property
    def _model(self):
        raise NotImplementedError()

    @classmethod
    def _object_not_exist_exception(cls, obj_uuid):
        raise ObjectNotExistException(cls._model, obj_uuid)

    @classmethod
    def _validate_mutation(cls, user, **data):
        cls._validate_user(user)

    @classmethod
    def _validate_user(cls, user):
        if type(user) is AnonymousUser or not user.id:
            raise ValidationError("mutation.authentication_required")

    @classmethod
    def _mutate(cls, uuid):
        object_to_delete = cls._model.objects.filter(uuid=uuid).first()

        if object_to_delete is None:
            cls._object_not_exist_exception(uuid)
        else:
            object_to_delete.delete_history()


class BaseHistoryModelCreateMutationMixin:

    @property
    def _model(self):
        raise NotImplementedError()

    @classmethod
    def _validate_mutation(cls, user, **data):
        if type(user) is AnonymousUser or not user.id:
            raise ValidationError("mutation.authentication_required")

    @classmethod
    def _mutate(cls, user, **data):
        if "client_mutation_id" in data:
            data.pop('client_mutation_id')
        if "client_mutation_label" in data:
            data.pop('client_mutation_label')
        cls.create_object(user=user, object_data=data)

    @classmethod
    def create_object(cls, user, object_data):
        obj = cls._model(**object_data)
        obj.save(username=user.username)
        return obj


class BaseHistoryModelUpdateMutationMixin:

    @property
    def _model(self):
        raise NotImplementedError()

    @classmethod
    def _object_not_exist_exception(cls, obj_uuid):
        raise ObjectNotExistException(cls._model, obj_uuid)

    @classmethod
    def _validate_mutation(cls, user, **data):
        if type(user) is AnonymousUser or not user.id:
            raise ValidationError("mutation.authentication_required")
        obj_uuid = data['id']
        if cls._model.objects.filter(id=data['id']).first() is None:
            cls._object_not_exist_exception(obj_uuid=obj_uuid)

    @classmethod
    def _mutate(cls, user, **data):
        if "client_mutation_id" in data:
            data.pop('client_mutation_id')
        if "client_mutation_label" in data:
            data.pop('client_mutation_label')
        updated_object = cls._model.objects.filter(id=data['id']).first()
        [setattr(updated_object, key, data[key]) for key in data]
        cls.update_object(user=user, object_to_update=updated_object)

    @classmethod
    def update_object(cls, user, object_to_update):
        object_to_update.save(username=user.username)
        return object_to_update


class BaseHistoryModelDeleteMutationMixin:
    @property
    def _model(self):
        raise NotImplementedError()

    @classmethod
    def _object_not_exist_exception(cls, obj_uuid):
        raise ObjectNotExistException(cls._model, obj_uuid)

    @classmethod
    def _validate_mutation(cls, user, **data):
        cls._validate_user(user)

    @classmethod
    def _validate_user(cls, user):
        if type(user) is AnonymousUser or not user.id:
            raise ValidationError("mutation.authentication_required")

    @classmethod
    def _mutate(cls, user, **data):
        if "client_mutation_id" in data:
            data.pop('client_mutation_id')
        if "client_mutation_label" in data:
            data.pop('client_mutation_label')

        id_ = data.get('uuid', None) or data.get('id', None)
        ids = data.get('uuids', None) or data.get('ids', None)
        if id_:
            cls.__delete_single_obj(user=user, id_=id_)
        elif ids:
            with transaction.atomic():
                for id_ in ids:
                    cls.__delete_single_obj(user, id_)

    @classmethod
    def __delete_single_obj(cls, user, id_):
        object_to_delete = cls._model.objects.filter(id=id_).first()
        if object_to_delete is None:
            cls._object_not_exist_exception(id_)
        else:
            object_to_delete.delete(username=user.username)


class BaseHistoryModelReplaceMutationMixin:
    @property
    def _model(self):
        raise NotImplementedError()

    @classmethod
    def _object_not_exist_exception(cls, obj_uuid):
        raise ObjectNotExistException(cls._model, obj_uuid)

    @classmethod
    def _validate_mutation(cls, user, **data):
        cls._validate_user(user)

    @classmethod
    def _validate_user(cls, user):
        if type(user) is AnonymousUser or not user.id:
            raise ValidationError("mutation.authentication_required")

    @classmethod
    def _mutate(cls, user, **data):
        if "client_mutation_id" in data:
            data.pop('client_mutation_id')
        if "client_mutation_label" in data:
            data.pop('client_mutation_label')
        object_to_replace = cls._model.objects.filter(id=data['uuid']).first()
        if object_to_replace is None:
            cls._object_not_exist_exception(data['uuid'])
        else:
            object_to_replace.replace_object(data=data, username=user.username)
