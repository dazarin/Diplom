from django.conf import settings
from django.core.mail import send_mail
from django.db.models.signals import post_save
from django.dispatch import receiver, Signal
from django_rest_passwordreset.signals import reset_password_token_created

from .models import User, ConfirmEmailToken


new_user_registered = Signal()

@receiver(post_save, sender=User)
def new_user_registered_signal(instance: User, created: bool, **kwargs):
    """
    Отправляем письмо с подтверждением адреса электронной почты
    """

    if created and not instance.is_active:
        token, _ = ConfirmEmailToken.objects.get_or_create(user_id=instance.pk)
        send_mail(f'Token for {instance.email}', token.key, settings.EMAIL_HOST_USER, [instance.email])

@receiver(reset_password_token_created)
def password_reset_token_created(reset_password_token, **kwargs):
    """
    Отправляем токен сброса пароля
    """

    send_mail(f'Password reset token for {reset_password_token.user}', reset_password_token.key,
              settings.EMAIL_HOST_USER, [reset_password_token.user.email])
