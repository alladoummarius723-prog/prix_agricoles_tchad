from django.urls import path
from . import views

urlpatterns = [
    path('predict/',  views.api_predict,   name='api_predict'),
    path('tendances/',views.api_tendances,  name='api_tendances'),
    path('marches/',  views.api_marches,    name='api_marches'),
    path('produits/', views.api_produits,   name='api_produits'),
]
