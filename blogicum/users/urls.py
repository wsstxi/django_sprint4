from django.urls import path
from . import views

app_name = 'users'

urlpatterns = [
    # Профиль пользователя
    path(
        'profile/<str:username>/',
        views.UserProfileView.as_view(),
        name='profile'
    ),
    
    # Редактирование профиля
    path(
        'profile/<str:username>/edit/',
        views.EditProfileView.as_view(),
        name='edit_profile'
    ),
]