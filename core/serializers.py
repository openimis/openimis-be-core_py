from rest_framework import serializers
from .models import User, InteractiveUser, TechnicalUser, UserRole, Role


class InteractiveUserSerializer(serializers.ModelSerializer):
    language = serializers.PrimaryKeyRelatedField(many=False, read_only=True)

    class Meta:
        model = InteractiveUser
        fields = ('id', 'language', 'last_name',
                  'other_names', 'health_facility_id', 'rights')


class TechnicalUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = TechnicalUser
        fields = ('id', 'language', 'username', 'email')


from rest_framework import serializers


class UserSerializer(serializers.ModelSerializer):
    i_user = InteractiveUserSerializer(many=False, read_only=True)
    t_user = TechnicalUserSerializer(many=False, read_only=True)
    user_roles = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ('id', 'username', 'i_user', 't_user', 'user_roles')

    def get_user_roles(self, obj):
        user_roles = UserRole.objects.filter(user=obj.i_user)
        role_names = [user_role.role.name for user_role in user_roles]
        return role_names
