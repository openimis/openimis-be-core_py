from rest_framework import serializers

from .apps import CoreConfig
from .models import User, InteractiveUser, TechnicalUser


class InteractiveUserSerializer(serializers.ModelSerializer):
    language = serializers.PrimaryKeyRelatedField(many=False, read_only=True)
    has_password = serializers.SerializerMethodField()

    def get_has_password(self, obj):
        return obj.stored_password != CoreConfig.locked_user_password_hash

    class Meta:
        model = InteractiveUser
        fields = ('id', 'language', 'last_name',
                  'other_names', 'health_facility_id', 'rights', 'has_password')


class TechnicalUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = TechnicalUser
        fields = ('id', 'language', 'username', 'email')


class UserSerializer(serializers.ModelSerializer):
    i_user = InteractiveUserSerializer(many=False, read_only=True)
    t_user = TechnicalUserSerializer(many=False, read_only=True)

    class Meta:
        model = User
        fields = ('id', 'username', 'i_user', 't_user')
