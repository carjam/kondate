from django.contrib import admin

from .models import *


class RecipeAdmin(admin.ModelAdmin):
    fieldsets = [
        (None, {'fields': ['name_text']}),
        ('URL', {'fields': ['url_text'], 'classes': ['collapse']}),
    ]
    list_display = ('name_text', 'url_text')
    list_filter = ['name_text']
    search_fields = ['name_text']


admin.site.register(Recipe, RecipeAdmin)
admin.site.register(Ingredient)
admin.site.register(Variety)
admin.site.register(Meal)
