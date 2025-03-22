from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db.models import Q
from django.http import JsonResponse
from rest_framework.response import Response
from django.shortcuts import render
from rest_framework.generics import ListAPIView
from rest_framework.views import APIView
from rest_framework.authtoken.models import Token
from requests import get
from yaml import load, Loader

from .models import ConfirmEmailToken, Category, Shop, ProductInfo, Product, Parameter, ProductParameter
from .serializers import UserSerializer, CategorySerializer, ShopSerializer, ProductInfoSerializer


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
