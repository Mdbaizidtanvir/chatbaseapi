from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from . import views

urlpatterns = [
    path('register/', views.register_user),
    path('login/', views.login_user),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('bots/', views.BotListCreateView.as_view()),
]
