from django.urls import include, path
from lizenzen import views

urlpatterns = [
    path("", views.startseite, name="home"),
    path("", include("lizenzen.urls")),
]
