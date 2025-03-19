from rest_framework import serializers
from .models import User, Shop, Category, Product, Contact


class ContactSerializer(serializers.ModelSerializer):

    class Meta:
        model = Contact
        fields = ['id', 'user', 'region', 'city', 'street', 'house', 'flat', 'comments']
        read_only_fields = ['id']


class UserSerializer(serializers.ModelSerializer):
    contacts = ContactSerializer(read_only=True, many=True)

    class Meta:
        model = User
        fields = ['id', 'first_name', 'last_name', 'username', 'email', 'type', 'phone']
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



