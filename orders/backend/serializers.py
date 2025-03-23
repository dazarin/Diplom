from rest_framework import serializers
from .models import User, Shop, Category, Product, Contact, ProductParameter, ProductInfo, OrderItem, Order


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
        fields = ['id', 'name', 'opened', 'url']
        read_only_fields = ['id']


class CategorySerializer(serializers.ModelSerializer):

    class Meta:
        model = Category
        fields = ['id', 'name']
        read_only_fields = ['id']


class ProductSerializer(serializers.ModelSerializer):
    category = serializers.StringRelatedField()

    class Meta:
        model = Product
        fields = ['id', 'name', 'category']
        read_only_fields = ['id']


class ProductParameterSerializer(serializers.ModelSerializer):
    parameter = serializers.StringRelatedField()

    class Meta:
        model = ProductParameter
        fields = ['parameter', 'value']


class ProductInfoSerializer(serializers.ModelSerializer):
    product = ProductSerializer(read_only=True)
    product_parameters = ProductParameterSerializer(read_only=True, many=True)

    class Meta:
        model = ProductInfo
        fields = ['id', 'model', 'product', 'shop', 'quantity', 'price', 'price_rrc', 'product_parameters']
        read_only_fields = ['id']


class OrderItemSerializer(serializers.ModelSerializer):

    class Meta:
        model = OrderItem
        fields = ['id', 'order', 'product_info', 'quantity']
        read_only_fields = ['id']
        extra_kwargs = {'order': {'write_only': True}}


class OrderItemCreateSerializer(OrderItemSerializer):
    product_info = ProductInfoSerializer(read_only=True)


class OrderSerializer(serializers.ModelSerializer):
    ordered_items = OrderItemCreateSerializer(read_only=True, many=True)
    total_sum = serializers.IntegerField()

    class Meta:
        model = Order
        fields = ['id', 'dt', 'status', 'ordered_items', 'total_sum', 'address']
        read_only_fields = ['id']
