from django.conf.urls import url
from . import views

app_name = 'kondate'
urlpatterns = [
    url(r'^index/$', views.index, name='index'),
    url(r'^calendar/$', views.CalendarView.as_view(), name='calendar'),
    url(r'^meal/new/$', views.meal, name='meal_new'),
	url(r'^meal/edit/(?P<meal_id>\d+)/$', views.meal, name='meal_edit'),
    # get list of ingredients per recipe
    # get list of ingredients for date range
]
