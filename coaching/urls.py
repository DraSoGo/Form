from django.urls import path
from . import views
app_name='coaching'
urlpatterns=[path('',views.home,name='home'),path('settings/',views.settings_view,name='settings'),path('request/<str:task>/',views.request_analysis,name='request'),path('retry/<uuid:pk>/',views.retry,name='retry'),path('decision/<uuid:pk>/',views.decision,name='decision'),path('food/<uuid:pk>/',views.food,name='food'),path('push/',views.subscribe,name='push')]
