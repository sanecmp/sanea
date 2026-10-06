"""Sanea URL configuration."""

from django.contrib import admin
from django.urls import include, path


app_name = "sanea"

urlpatterns = [
    path("", include("sanea.core.urls")),
    path("admin/", admin.site.urls),
]
