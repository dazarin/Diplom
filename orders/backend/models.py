from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django_rest_passwordreset.tokens import get_token_generator


USER_TYPE_CHOICES = (
    ('seller', 'Продавец'),
    ('byer', 'Покупатель'),
)

STATUS_CHOICES = (
    ('basket', 'Корзина'),
    ('new', 'Новый заказ'),
    ('delivery', 'Доставка'),
    ('finish', 'Исполнен'),
    ('canceled', 'Отменён'),
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
    type = models.CharField(choices=USER_TYPE_CHOICES, max_length=6, default='buyer')
    is_active = models.BooleanField(default=False)
    # активация юзера через проверку почты, вместо физического удаления юзера из базы он будет деактивирован
    # Остальные непереопределяемые поля (имя, фамилия, никнейм) наследуются от базового класса
    phone = models.CharField(max_length=12, verbose_name='Телефон', unique=True)

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


class Contact(models.Model):
    """
    Контакты пользователя.
    В связи со стартом нового локального бизнеса, а также с учётом санкционной политики и нестабильной конъюнктуры на
    внешних рынках доставка заказов пока предполагается по территории РФ. После разговора Путина с Трампом, защиты
    диплома и роста бизнеса возможно расширение модели за счёт снятия заглушки.
    Числовые поля (дом, квартира) в БД также записываются текстом, т.к. необходимости переводидть строковые инпуты в
    числа для работы с ними математически нет, к тому же например номера домов могут содержать корпуса, строения, буквы
    и т.д.
    В поле комментариев можно вносить любую информацию для данного адреса доставки, например код домофона или указания
    для курьера.
    """
    objects = models.manager.Manager()
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='contacts', verbose_name='Пользователь',
                             blank=True)
    # country = models.CharField(max_length=30, verbose_name='Страна')
    region = models.CharField(max_length=30, verbose_name='Регион')
    city = models.CharField(max_length=30, verbose_name='Город / населённый пункт')
    street = models.CharField(max_length=30, verbose_name='Улица')
    house = models.CharField(max_length=5, verbose_name='Дом')
    flat = models.CharField(max_length=5, verbose_name='Квартира', blank=True, null=True)
    comments = models.CharField(verbose_name='Комментарии', blank=True, null=True)

    def __str__(self):
        return f'{self.city} {self.street} {self.house} {self.flat}'


class Shop(models.Model):
    objects = models.manager.Manager()
    name = models.CharField(max_length=50, verbose_name='Название магазина')
    user = models.OneToOneField(User, on_delete=models.CASCADE, verbose_name='Продавец', blank=True, null=True)
    opened = models.BooleanField(verbose_name='Статус работы магазина', default=True)
    url = models.URLField(verbose_name='Ссылка на сайт магазина', blank=True, null=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Category(models.Model):
    objects = models.manager.Manager()
    name = models.CharField(max_length=50, verbose_name='Название категориии')
    shops = models.ManyToManyField(Shop, related_name='categories', verbose_name='Магазины', blank=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Product(models.Model):
    objects = models.manager.Manager()
    name = models.CharField(max_length=100, verbose_name='Название товара')
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='category', verbose_name='Категория',
                                 blank=True, null=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class ProductInfo(models.Model):
    objects = models.manager.Manager()
    model = models.CharField(max_length=80, verbose_name='Модель', blank=True, null=True)
    external_id = models.PositiveIntegerField(verbose_name='Внешний ИД')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='product_info', verbose_name='Товар',
                                blank=True)
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name='product_info', verbose_name='Магазин',
                             blank=True)
    quantity = models.PositiveIntegerField(verbose_name='Количество')
    price = models.PositiveIntegerField(verbose_name='Цена')
    price_rrc = models.PositiveIntegerField(verbose_name='Рекомендуемая розничная цена')

    class Meta: # для корректного учёта одного и того же товара в разных магазинах
        constraints = [
            models.UniqueConstraint(fields=['product', 'shop', 'external_id'], name='unique_product_info')
        ]


class Parameter(models.Model):
    objects = models.manager.Manager()
    name = models.CharField(max_length=50, verbose_name='Название параметра')

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class ProductParameter(models.Model):
    objects = models.manager.Manager()
    product_info = models.ForeignKey(ProductInfo, on_delete=models.CASCADE, related_name='product_parameters',
                                     verbose_name='Информация о товаре', blank=True)
    parameter = models.ForeignKey(Parameter, on_delete=models.CASCADE, related_name='product_parameters',
                                  verbose_name='Параметр', blank=True)
    value = models.CharField(max_length=100, verbose_name='Значение параметра')

    class Meta: # Связка товаров и их характеристик
        constraints = [
            models.UniqueConstraint(fields=['product_info', 'parameter'], name='unique_product_parameter')
        ]


class Order(models.Model):
    objects = models.manager.Manager()
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='orders', verbose_name='Покупатель')
    address = models.ForeignKey(Contact, on_delete=models.CASCADE, related_name='orders', verbose_name='Адрес')
    dt = models.DateTimeField(auto_now_add=True)
    status = models.CharField(choices=STATUS_CHOICES, max_length=15, verbose_name='Статус заказа')

    class Meta:
        ordering = ['-dt']

    def __str__(self):
        return f'Заказ № {self.pk} от {self.dt}'


class OrderItem(models.Model):
    objects = models.manager.Manager()
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='ordered_items', verbose_name='Заказ')
    product_info = models.ForeignKey(ProductInfo, on_delete=models.CASCADE, related_name='ordered_items',
                                     verbose_name='Информация о продукте')
    quantity = models.PositiveIntegerField(verbose_name='Количество')

    class Meta:
        constraints = [models.UniqueConstraint(fields=['order_id', 'product_info'], name='unique_order_item')]