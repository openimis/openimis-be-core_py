from rest_framework import serializers

from .apps import CoreConfig
from .models import User, InteractiveUser, TechnicalUser
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.core.cache import cache

class CachedModelSerializer(serializers.ModelSerializer):
    cache_ttl = None  # Default cache TTL (infinites)

    def to_representation(self, instance):
        cache_key = self.get_cache_key(instance)
        cached_data = cache.get(cache_key)

        if cached_data is not None:
            return cached_data

        representation = super().to_representation(instance)
        cache.set(cache_key, representation, self.cache_ttl)
        return representation

    def get_cache_key(self, instance):
        return f"cs_{self.__class__.__name__}_{instance.id}"


class InteractiveUserSerializer(CachedModelSerializer):
    language = serializers.PrimaryKeyRelatedField(many=False, read_only=True)
    has_password = serializers.SerializerMethodField()

    def get_has_password(self, obj):
        return obj.stored_password != CoreConfig.locked_user_password_hash

    class Meta:
        model = InteractiveUser
        fields = ('id', 'language', 'last_name',
                  'other_names', 'health_facility_id', 'rights', 'has_password')


class TechnicalUserSerializer(CachedModelSerializer):
    cache_ttl = 60 * 60
    
    class Meta:
        model = TechnicalUser
        fields = ('id', 'language', 'username', 'email')


class UserSerializer(serializers.ModelSerializer):
    i_user = InteractiveUserSerializer(many=False, read_only=True)
    t_user = TechnicalUserSerializer(many=False, read_only=True)

    class Meta:
        model = User
        fields = ('id', 'username', 'i_user', 't_user')
