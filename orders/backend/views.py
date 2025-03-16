from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.http import JsonResponse
from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.authtoken.models import Token

from .models import ConfirmEmailToken
from .serializers import UserSerializer


class RegisterAccount(APIView):
    """
    Класс регистрации пользователей
    """

    def post(self, request):
        if {'first_name', 'last_name', 'username', 'email', 'password'}.issubset(request.data):
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
