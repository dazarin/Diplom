from rest_framework import serializers
from .models import User, Shop, Category, Product


class UserSerializer(serializers.ModelSerializer):

    class Meta:
        model = User
        fields = ['id', 'first_name', 'last_name', 'username', 'email', 'type']
        read_only_fields = ['id']


class ShopSerializer(serializers.ModelSerializer):

    class Meta:
        model = Shop
        fields = ['is', 'name', 'opened', 'url']
        read_only_fields = ['id']


class CategorySerializer(serializers.ModelSerializer):

    class Meta:
        model = Category
        fields = ['id', 'name']
        read_only_fields = ['id']


class ProductSerializer(serializers.ModelSerializer):

    class Meta:
        model = Product
        fields = ['id', 'name']
        read_only_fields = ['id']



