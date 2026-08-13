from django.urls import path

from . import views


urlpatterns = [
    path("authorize/", views.authorize, name="oauth-authorize"),
    path("token/", views.token, name="oauth-token"),
    path("revoke/", views.revoke, name="oauth-revoke"),
    path("register/", views.register, name="oauth-register"),
]
