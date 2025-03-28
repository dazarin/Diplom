from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.signals import request_started
from django.core.validators import URLValidator
from django.db import IntegrityError
from django.db.models import Q, Sum, F
from django.http import JsonResponse
from rest_framework.response import Response
from django.shortcuts import render
from rest_framework.generics import ListAPIView
from rest_framework.views import APIView
from rest_framework.authtoken.models import Token
from requests import get
from yaml import load, Loader
from ujson import loads as load_json

from .models import ConfirmEmailToken, Category, Shop, ProductInfo, Product, Parameter, ProductParameter, Order, \
    OrderItem, Contact
from .serializers import UserSerializer, CategorySerializer, ShopSerializer, ProductInfoSerializer, OrderSerializer, \
    OrderItemSerializer, ContactSerializer
from .signals import new_order


class RegisterAccount(APIView):
    """
    Класс регистрации пользователей
    """

    def post(self, request):
        if {'first_name', 'last_name', 'username', 'email', 'password', 'phone'}.issubset(request.data):
            try:
                validate_password(request.data['password']) # проверяем пароль на сложность
            except Exception as err: # формируем ошибки валидации пароля
                errors = list()
                # noinspection PyTypeChecker
                for item in err:
                    errors.append(item)
                return JsonResponse({'Status': False, 'Errors': {'password': errors}}) # и возвращаем их
            else:
                user_serializer = UserSerializer(data=request.data)
                if user_serializer.is_valid():
                    user = user_serializer.save()
                    user.set_password(request.data['password']) # солим и прячем пароль
                    user.save()
                    return JsonResponse({'Status': 'Аккаунт зарегистрирован. Пожалуйста, подтвердите Вашу почту'})
                else:
                    return JsonResponse({'Status': False, 'Errors': user_serializer.errors})

        return JsonResponse({'Status': False, 'Errors': 'Не переданы все необходимые аргументы'})


class ConfirmAccount(APIView):
    """
    Класс для подтверждения электронной почты
    """

    def post(self, request):
        if {'email', 'token'}.issubset(request.data):
            token = ConfirmEmailToken.objects.filter(user__email=request.data['email'],
                                                     key=request.data['token']).first()
            if token:
                token.user.is_active = True
                token.user.save()
                token.delete() # Токен для почты больше не нужен, при входе юзера по паролю ему будет выдан новый токен
                return JsonResponse({'Status': 'Email подтверждён'})
            else:
                return JsonResponse({'Status': False, 'Errors': 'Неверно указан токен или email'})

        return JsonResponse({'Status': False, 'Errors': 'Не переданы токен и/или email'})


class LoginAccount(APIView):
    """
    Класс для аутентификации пользователей
    """

    def post(self, request):
        if {'email', 'password'}.issubset(request.data):
            user = authenticate(request, username=request.data['email'], password=request.data['password'])
            if user:
                if user.is_active:
                    token, _ = Token.objects.get_or_create(user=user)
                    return JsonResponse({'Status': True, 'Token': token.key})
                return JsonResponse({'Status': False, 'Error': 'Требуется подтверждение электронной почты'})
            return JsonResponse({'Status': False, 'Error': 'Аутентификация неуспешна. Проверьте вводимые данные'})
        return JsonResponse({'Status': False, 'Error': 'Не переданы email и/или пароль'})


class PartnerUpdate(APIView):
    """
    Класс для актуализации цен, обновления информации о товарах и добавления новых товаров в каталог
    """

    def post(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            if request.user.type == 'seller':
                url = request.data.get('url')
                if url:
                    validate_url = URLValidator()
                    try:
                        validate_url(url)
                    except ValidationError as err:
                        return JsonResponse({'Status': False, 'Error': str(err)})
                    else:
                        stream = get(url).content
                        data = load(stream, Loader=Loader)
                        shop, _ = Shop.objects.get_or_create(name=data['shop'], user_id=request.user.id)
                        for category in data['categories']:
                            cat, _ = Category.objects.get_or_create(id=category['id'], name=category['name'])
                            cat.shops.add(shop.id)
                            cat.save()
                        ProductInfo.objects.filter(shop_id=shop.id).delete()
                        for item in data['goods']:
                            product, _ = Product.objects.get_or_create(name=item['name'], category_id=item['category'])
                            product_info = ProductInfo.objects.create(product_id=product.id,
                                                                      external_id=item['id'],
                                                                      model=item['model'],
                                                                      price=item['price'],
                                                                      price_rrc=item['price_rrc'],
                                                                      quantity=item['quantity'],
                                                                      shop_id=shop.id)
                            for name, value in item['parameters'].items():
                                param, _ = Parameter.objects.get_or_create(name=name)
                                ProductParameter.objects.create(product_info_id=product_info.id,
                                                                parameter_id=param.id,
                                                                value=value)
                        return JsonResponse({'Status': 'Каталог обновлён'})
                return JsonResponse({'Status': False, 'Error': 'Не передана ссылка на файл обновления'},
                                    status=400)
            return JsonResponse({'Status': False, 'Error': 'Обновление прайса доступно только для продавцов'},
                                status=403)
        return JsonResponse({'Status': False, 'Error': 'Не пройдена аутентификация. Пожалуйста, представьтесь'},
                            status=401)


class CategoryView(ListAPIView):
    """
    Класс для просмотра категорий
    """

    queryset = Category.objects.all()
    serializer_class = CategorySerializer


class ShopView(ListAPIView):
    """
    Класс для просмотра магазинов
    """

    queryset = Shop.objects.filter(opened=True)
    serializer_class = ShopSerializer


class ProductInfoView(APIView):
    """
    Класс для поиска товаров по категории и/или магазину. Если пользователем передан конкретный магазин или категория,
    последовательно сужаем поле поиска, иначе отдаём все товары, доступные к заказу из открытых магазинов.
    Информацию о товарах отдаём со всеми их характеристиками.
    """

    def get(self, request):
        shop_id = request.query_params.get('shop_id')
        category_id = request.query_params.get('category_id')
        # Подгатавливам фильтры
        query = Q(shop__opened=True)
        if shop_id:
            query = query & Q(shop_id=shop_id)
        if category_id:
            query = query & Q(product__category_id=category_id)
        # Фильтруем и отбрасываем дубликаты
        queryset = ProductInfo.objects.filter(query).select_related('shop', 'product__category').prefetch_related(
            'product_parameters__parameter').distinct()
        serializer = ProductInfoSerializer(queryset, many=True)
        return Response(serializer.data)


class OpenCloseShop(APIView):
    """
    Класс для закрытия и открытия продавцами магазина
    """

    def get(self, request):
        """Проверка работы магазина и возможности приёма заказов"""
        if request.user.is_authenticated:
            if request.user.type == 'seller':
                shop = request.user.shop
                serializer = ShopSerializer(shop)
                return JsonResponse({serializer.data['name']: 'Открыт' if serializer.data['opened'] else 'Закрыт'})
            return JsonResponse({'Status': False, 'Error': 'Управление работой магазина доступно только для '
                                                           'продавцов'}, status=403)
        return JsonResponse({'Status': False, 'Error': 'Не пройдена аутентификация. Пожалуйста, представьтесь'},
                            status=401)

    def post(self, request):
        """Закрытие/открытие магазина"""
        if request.user.is_authenticated:
            if request.user.type == 'seller':
                switch = request.data.get('shop closed/opened')
                if switch:
                    if switch in ['0', '1']:
                        switch = bool(int(switch))
                        Shop.objects.filter(user_id=request.user.id).update(opened=switch)
                        return JsonResponse({'Status': 'Магазин открыт для приёма заказов' if switch else 'Магазин закрыт'})
                    return JsonResponse({'Status': False, 'Error': 'Для открытия магазина и возможности приёма '
                                                                   'заказов введите 1, для закрытия - 0'}, status=400)
                return JsonResponse({'Status': False, 'Error': 'Данные о работе магазина не переданы'}, status=400)
            return JsonResponse({'Status': False, 'Error': 'Управление работой магазина доступно только для '
                                                           'продавцов'}, status=403)
        return JsonResponse({'Status': False, 'Error': 'Не пройдена аутентификация. Пожалуйста, представьтесь'},
                            status=401)


class BasketView(APIView):
    """Класс для работы с корзиной (добавление/удаление товаров, просмотр корзины и редактирование"""

    def get(self, request):
        """Просмотр корзины"""
        if request.user.is_authenticated:
            basket = Order.objects.filter(user_id=request.user.id, status='basket').prefetch_related(
                'ordered_items__product_info__product__category',
                'ordered_items__product_info__product_parameters__parameter').annotate(
                total_sum=Sum(F('ordered_items__quantity') * F('ordered_items__product_info__price'))).distinct()
            serializer = OrderSerializer(basket, many=True)
            return Response(serializer.data)
        return JsonResponse({'Status': False, 'Error': 'Не пройдена аутентификация. Пожалуйста, представьтесь'},
                            status=401)

    def post(self, request, *args, **kwargs):
        """Добавление товаров в корзину"""
        if request.user.is_authenticated:
            items_string = request.data.get('items')
            if items_string:
                try:
                    items_dict = load_json(items_string)
                except ValueError:
                    return JsonResponse({'Status': False, 'Error': 'Неверный формат запроса. Передайте список с '
                                                                   'данными о товарах и их количестве'}, status=400)
                else:
                    basket, _ = Order.objects.get_or_create(user_id=request.user.id, status='basket')
                    positions = 0
                    for item in items_dict:
                        item.update({'order': basket.id})
                        serializer = OrderItemSerializer(data=item)
                        if serializer.is_valid():
                            try:
                                serializer.save()
                            except IntegrityError as err:
                                return JsonResponse({'Status': False, 'Errors': str(err)})
                            else:
                                positions += 1
                        else:
                            return JsonResponse({'Status': False, 'Errors': serializer.errors})
                    return JsonResponse({'Status': True, 'В корзину добавлено позиций': positions})
            return JsonResponse({'Status': False, 'Error': 'Информация о товарах для добавления в корзину '
                                                           'не передана'}, status=403)
        return JsonResponse({'Status': False, 'Error': 'Не пройдена аутентификация. Пожалуйста, представьтесь'},
                            status=401)

    def patch(self, request, *args, **kwargs):
        """Обновление количества товаров в корзине"""
        if request.user.is_authenticated:
            items_string = request.data.get('items')
            if items_string:
                try:
                    items_dict = load_json(items_string)
                except ValueError:
                    return JsonResponse({'Status': False, 'Error': 'Неверный формат запроса. Передайте список с '
                                                                   'данными о товарах и их количестве'}, status=400)
                else:
                    basket = Order.objects.get(user_id=request.user.id, status='basket')
                    positions = 0
                    for item in items_dict:
                        OrderItem.objects.filter(order_id=basket.id, id=item['id']).update(quantity=item['quantity'])
                        positions += 1
                    return JsonResponse({'Status': True, 'Обновлено количество товара по числу позиций': positions})
            return JsonResponse({'Status': False, 'Error': 'Информация о товарах для уточнения количества '
                                                           'не передана'}, status=403)
        return JsonResponse({'Status': False, 'Error': 'Не пройдена аутентификация. Пожалуйста, представьтесь'},
                            status=401)

    def delete(self, request, *args, **kwargs):
        """Удаление товаров в корзине"""
        if request.user.is_authenticated:
            item = request.data.get('item')
            if item.isdigit():
                basket = Order.objects.get(user_id=request.user.id, status='basket')
                OrderItem.objects.get(order_id=basket.id, id=item).delete()
                return JsonResponse({'Status': 'Товар удалён'})
            return JsonResponse({'Status': False, 'Error': 'Для удаления товара передайте его id'}, status=403)
        return JsonResponse({'Status': False, 'Error': 'Не пройдена аутентификация. Пожалуйста, представьтесь'},
                            status=401)

class ContactView(APIView):
    """Класс для управления контактами для доставки"""

    def get(self, request):
        '''Получение контактов (адресов доставки)'''
        if request.user.is_authenticated:
            contacts = Contact.objects.filter(user_id=request.user.id)
            serializer = ContactSerializer(contacts, many=True)
            return Response(serializer.data)

    def post(self, request):
        '''Добавление нового адреса доставки'''
        if request.user.is_authenticated:
            if {'region', 'city', 'street', 'house'}.issubset(request.data):
                request.data._mutable = True
                request.data['user'] = request.user.id
                serializer = ContactSerializer(data=request.data)
                if serializer.is_valid():
                    serializer.save()
                    return Response(serializer.data)
                else:
                    return JsonResponse({'Status': False, 'Errors': serializer.errors})
            return JsonResponse({'Status': False, 'Error': 'Не переданы обязательные элементы адреса'}, status=400)
        return JsonResponse({'Status': False, 'Error': 'Не пройдена аутентификация. Пожалуйста, представьтесь'},
                            status=401)

    def patch(self, request):
        '''Уточнение адреса доставки (редактирование комментария, исправление ошибок'''
        if request.user.is_authenticated:
            if request.data['contact_id'].isdigit():
                contact = Contact.objects.filter(user_id=request.user.id, id=request.data['contact_id']).first()
                if contact:
                    serializer = ContactSerializer(contact, data=request.data, partial=True)
                    if serializer.is_valid():
                        serializer.save()
                        return JsonResponse({'Status: Контакт обновлён': serializer.data})
                    else:
                        return JsonResponse({'Status': False, 'Errors': serializer.errors})
                return JsonResponse({'Status': False, 'Error': 'Контакт не найден'}, status=404)
            return JsonResponse({'Status': False, 'Error': 'Неверный формат запроса. Не передан id контакта'},
                                status=400)
        return JsonResponse({'Status': False, 'Error': 'Не пройдена аутентификация. Пожалуйста, представьтесь'},
                            status=401)

    def delete(self, request, *args, **kwargs):
        """Удаление контакта"""
        if request.user.is_authenticated:
            contact_id = request.data.get('contact_id')
            Contact.objects.filter(user_id=request.user.id, id=contact_id).delete()
            return JsonResponse({'Status': 'Контакт удалён'})
        return JsonResponse({'Status': False, 'Error': 'Не пройдена аутентификация. Пожалуйста, представьтесь'},
                            status=401)

class OrderView(APIView):
    '''
    Класс для оформления и просмотра своих заказов
    '''

    def get(self, request):
        if request.user.is_authenticated:
            order = Order.objects.filter(user_id=request.user.id).exclude(status='basket').select_related(
                'address').prefetch_related('ordered_items__product_info__product_parameters__parameter').annotate(
                total_sum=Sum(F('ordered_items__quantity') * F('ordered_items__product_info__price'))).distinct()
            serializer = OrderSerializer(order, many=True)
            return Response(serializer.data)
        return JsonResponse({'Status': False, 'Error': 'Не пройдена аутентификация. Пожалуйста, представьтесь'},
                            status=401)

    def post(self, request):
        if request.user.is_authenticated:
            if 'contact_id' in request.data:
                Order.objects.filter(user_id=request.user.id, status='basket').update(
                    address_id=request.data['contact_id'], status='new')
                order = Order.objects.filter(user_id=request.user.id, status='new').first()
                new_order.send(sender=self.__class__, order=order)
                return JsonResponse({'Status': 'Заказ принят'})
            return JsonResponse({'Status': False, 'Error': 'Неверный формат запроса. Не передана информация об '
                                                           'адресе для доставки'}, status=400)
        return JsonResponse({'Status': False, 'Error': 'Не пройдена аутентификация. Пожалуйста, представьтесь'},
                            status=401)


class SellerOrdersView(APIView):
    ''' Класс для получения заказов продавцами'''

    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            if request.user.type == 'seller':
                orders = Order.objects.filter(ordered_items__product_info__shop__user_id=request.user.id).exclude(
                    status='basket').select_related('address').prefetch_related('ordered_items__product_info').annotate(
                    total_sum=Sum(F('ordered_items__quantity') * F('ordered_items__product_info__price'))).distinct()
                serializer = OrderSerializer(orders, many=True)
                return Response(serializer.data)
            return JsonResponse({'Status': False, 'Error': 'Получение заказов доступно для продавцов'}, status=403)
        return JsonResponse({'Status': False, 'Error': 'Не пройдена аутентификация. Пожалуйста, представьтесь'},
                            status=401)
