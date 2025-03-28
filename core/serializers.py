from rest_framework import serializers

from .apps import CoreConfig
from .models import User, InteractiveUser, TechnicalUser
from django.core.cache import cache
from core.utils import get_cache_key


class CachedModelSerializer(serializers.ModelSerializer):
    cache_ttl = None  # Default cache TTL (infinites)

    def to_representation(self, instance):
        cache_key = get_cache_key(instance.__class__, instance.id)
        cached_data = cache.get(cache_key)

        if cached_data is not None:
            instance = cached_data

        representation = super().to_representation(instance)
        cache.set(cache_key, representation, self.cache_ttl)
        return representation


class InteractiveUserSerializer(serializers.ModelSerializer):
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
