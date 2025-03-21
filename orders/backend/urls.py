from django.urls import path
from django_rest_passwordreset.views import reset_password_request_token, reset_password_confirm
from .views import RegisterAccount, ConfirmAccount, LoginAccount, PartnerUpdate

app_name = 'backend'
urlpatterns = [
    path('user/register', RegisterAccount.as_view(), name='user-register'),
    path('user/confirm', ConfirmAccount.as_view(), name='user-confirm'),
    path('user/login', LoginAccount.as_view(), name='user-login'),
    path('user/password_reset', reset_password_request_token, name='user-password-reset'),
    path('user/password_reset/confirm', reset_password_confirm, name='user-password-reset-confirm'),
    path('seller/update', PartnerUpdate.as_view(), name='seller-update'),
]
