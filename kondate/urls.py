from django.urls import path

from . import views

app_name = "kondate"

urlpatterns = [
    path("", views.week, name="week"),
    path("healthz", views.healthz, name="healthz"),
    path("week/<str:day>/", views.week, name="week_of"),
    path("week/<str:day>/copy-previous/", views.week_copy_previous, name="week_copy_previous"),
    path("meals/new/", views.meal_edit, name="meal_new"),
    path("meals/<int:pk>/edit/", views.meal_edit, name="meal_edit"),
    path("meals/<int:pk>/delete/", views.meal_delete, name="meal_delete"),
    path("recipes/", views.recipe_list, name="recipe_list"),
    path("recipes/new/", views.recipe_edit, name="recipe_new"),
    path("recipes/<int:pk>/", views.recipe_detail, name="recipe_detail"),
    path("recipes/<int:pk>/edit/", views.recipe_edit, name="recipe_edit"),
    path("recipes/<int:pk>/delete/", views.recipe_delete, name="recipe_delete"),
    path("ingredients/", views.ingredient_list, name="ingredient_list"),
    path("ingredients/<int:pk>/stop-weekly/", views.ingredient_stop_weekly, name="ingredient_stop_weekly"),
    path("shopping/", views.shopping, name="shopping"),
    path("shopping/<str:day>/", views.shopping, name="shopping_week"),
    path("shopping/<str:day>/check/<int:ingredient_id>/", views.shopping_check, name="shopping_check"),
    path("shopping/<str:day>/reset/", views.shopping_reset, name="shopping_reset"),
    path("shopping/<str:day>/new-trip/", views.shopping_new_trip, name="shopping_new_trip"),
    path("shopping/<str:day>/extras/", views.shopping_extra_add, name="shopping_extra_add"),
    path("shopping/extras/<int:pk>/check/", views.shopping_extra_check, name="shopping_extra_check"),
    path("shopping/extras/<int:pk>/delete/", views.shopping_extra_delete, name="shopping_extra_delete"),
]
