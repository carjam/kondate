from django.contrib import admin

from .models import Ingredient, Meal, Recipe, RecipeIngredient, ShoppingExtra


class RecipeIngredientInline(admin.TabularInline):
    model = RecipeIngredient
    autocomplete_fields = ["ingredient"]
    extra = 1


@admin.register(Recipe)
class RecipeAdmin(admin.ModelAdmin):
    inlines = [RecipeIngredientInline]
    list_display = ["name", "url"]
    search_fields = ["name", "notes"]


@admin.register(Ingredient)
class IngredientAdmin(admin.ModelAdmin):
    list_display = ["name", "category", "is_staple"]
    list_editable = ["category", "is_staple"]
    list_filter = ["category", "is_staple"]
    search_fields = ["name"]


@admin.register(Meal)
class MealAdmin(admin.ModelAdmin):
    list_display = ["date", "slot", "recipe", "note"]
    list_filter = ["slot"]
    date_hierarchy = "date"
    list_select_related = ["recipe"]
    autocomplete_fields = ["recipe"]


@admin.register(ShoppingExtra)
class ShoppingExtraAdmin(admin.ModelAdmin):
    list_display = ["week_start", "name", "checked"]
