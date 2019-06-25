from rest_framework import serializers
from .models import User, TechnicalUser, Language

# class TechnicalUserSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = TechnicalUser
#         fields = ('id', 'username', 'email')

class UserSerializer(serializers.ModelSerializer):
    language = serializers.CharField(source='language_id')
    class Meta:
        model = User
        fields = ('id', 'username', 'language')