from django.core.cache import cache
from rest_framework import serializers

from .apps import CoreConfig
from .models import User, InteractiveUser, TechnicalUser
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


class LocationSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    uuid = serializers.UUIDField()
    code = serializers.CharField()
    name = serializers.CharField()
    type = serializers.CharField()
    parent = serializers.SerializerMethodField()

    def get_parent(self, obj):
        if not obj or not getattr(obj, "parent", None):
            return None
        return LocationSerializer(obj.parent).data


class PricelistSummarySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    uuid = serializers.CharField()


class HealthFacilitySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    uuid = serializers.UUIDField()
    code = serializers.CharField()
    name = serializers.CharField()
    level = serializers.CharField()
    servicesPricelist = PricelistSummarySerializer(source="services_pricelist")
    itemsPricelist = PricelistSummarySerializer(source="items_pricelist")
    contractStartDate = serializers.DateField(source="contract_start_date")
    contractEndDate = serializers.DateField(source="contract_end_date")
    location = LocationSerializer(many=False, read_only=True)


class OfficerSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    uuid = serializers.UUIDField()
    code = serializers.CharField()
    dob = serializers.DateField()
    address = serializers.CharField()
    lastName = serializers.CharField(source="last_name")
    otherNames = serializers.CharField(source="other_names")
    location = LocationSerializer(read_only=True)


class ClaimAdminSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    uuid = serializers.UUIDField()
    code = serializers.CharField()
    emailId = serializers.CharField(source="email_id")
    phone = serializers.CharField()
    dob = serializers.DateField()
    lastName = serializers.CharField(source="last_name")
    otherNames = serializers.CharField(source="other_names")
    healthFacility = HealthFacilitySerializer(source="health_facility")


class InteractiveUserSerializer(serializers.ModelSerializer):
    language = serializers.PrimaryKeyRelatedField(many=False, read_only=True)
    has_password = serializers.SerializerMethodField()
    default_rows_per_page = serializers.SerializerMethodField()

    def get_has_password(self, obj):
        return obj.stored_password != CoreConfig.locked_user_password_hash

    def get_default_rows_per_page(self, obj):
        if not isinstance(obj.json_ext, dict):
            return None
        return obj.json_ext.get("default_rows_per_page")

    class Meta:
        model = InteractiveUser
        fields = (
            "id",
            "language",
            "last_name",
            "other_names",
            "health_facility_id",
            "rights",
            "email",
            "phone",
            "has_password",
            "default_rows_per_page",
        )


class TechnicalUserSerializer(serializers.ModelSerializer):
    cache_ttl = 60 * 60

    class Meta:
        model = TechnicalUser
        fields = ("id", "language", "username", "email")


class UserSerializer(serializers.ModelSerializer):
    i_user = InteractiveUserSerializer(many=False, read_only=True)
    t_user = TechnicalUserSerializer(many=False, read_only=True)
    claim_admin = ClaimAdminSerializer(many=False, read_only=True)
    officer = OfficerSerializer(many=False, read_only=True)

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "is_superuser",
            "i_user",
            "t_user",
            "claim_admin",
            "officer",
        )
