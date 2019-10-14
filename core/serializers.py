from rest_framework import serializers
from .models import User, Role, RoleRight, InteractiveUser, TechnicalUser, Language


# class LanguageSerializer(serializers.ModelSerializer):

#     class Meta:
#         model = Language
#         fields = ('code',)


class RoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = ('id', 'name')


class InteractiveUserSerializer(serializers.ModelSerializer):
    language = serializers.PrimaryKeyRelatedField(many=False, read_only=True)
    role = RoleSerializer(many=False, read_only=True)

    class Meta:
        model = InteractiveUser
        fields = ('id', 'language', 'last_name',
                  'other_names', 'health_facility_id', 'role', 'rights')


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
