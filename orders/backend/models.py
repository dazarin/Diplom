from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django_rest_passwordreset.tokens import get_token_generator


USER_TYPE_CHOISES = (
    ('seller', 'Продавец'),
    ('byer', 'Покупатель'),
)

class UserManager(BaseUserManager):
    """
    Кастомный пользовательский менеджер
    """
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError('Не передан email')
        email = self.normalize_email(email) # для исключения нескольких регистраций на один почтовый ящик
        user = self.model(email=email, **extra_fields)
        user.set_password(password) # для безопасности прячем пароль
        user.save(using=self._db)
        return user

    # предустанавливаем по умолчанию статусные поля для обычных юзеров и админов
    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)

        if extra_fields.get('is_staff') is not True or extra_fields.get('is_superuser') is not True:
            raise ValueError('Для админов параметры is_staff и is_superuser должны быть активны')

        return self._create_user(email, password, **extra_fields)


class User(AbstractUser):
    """
    Переопределение стандартной пользовательской модели
    """
    REQUIRED_FIELDS = [] # при необходимости указываются обязательные поля, например ник username
    objects = UserManager()
    USERNAME_FIELD = 'email' # аутентификация по почте вместо имени пользователя
    email = models.EmailField(max_length=127, unique=True)
    type = models.CharField(choices=USER_TYPE_CHOISES, max_length=6, default='buyer')
    is_active = models.BooleanField(default=False)
    # активация юзера через проверку почты, вместо физического удаления юзера из базы он будет деактивирован
    # Остальные непереопределяемые поля (имя, фамилия, никнейм) наследуются от базового класса

    def __str__(self):
        return f'{self.first_name} {self.last_name} {self.email}'

    class Meta:
        ordering = ['email']


class ConfirmEmailToken(models.Model):
    objects = models.manager.Manager()

    @staticmethod
    def generate_key():
        return get_token_generator().generate_token()

    user = models.ForeignKey(User, related_name='confirm_email_token', on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    key = models.CharField(max_length=64, unique=True)

    def save(self, *args, **kwargs):
        if not self.key:
            self.key = self.generate_key()
        return super(ConfirmEmailToken, self).save(*args, **kwargs)

    def __str__(self):
        return 'Token for user {user}'.format(user=self.user)