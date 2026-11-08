from . import views
from django.urls import path, include

urlpatterns = [
    path('', views.snow_report, name='snow_report'),
]