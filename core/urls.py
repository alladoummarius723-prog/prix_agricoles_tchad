from django.urls import path
from . import views

urlpatterns = [
    path('',           views.home,           name='home'),
    path('prevision/', views.predict_view,   name='predict'),
    path('historique/',views.historique_view,name='historique'),
    path('aide-sms/',  views.aide_sms_view,  name='aide_sms'),
]
