from django.db import models
from django.urls import reverse
import datetime
from django.utils import timezone
from django.contrib import admin


class Variety(models.Model):
    name_text = models.CharField(max_length=200)

    def __str__(self):
        return self.name_text


class Ingredient(models.Model):
    name_text = models.CharField(max_length=200)

    def __str__(self):
        return self.name_text


class Recipe(models.Model):
    name_text = models.CharField(max_length=200)
    steps_text = models.CharField(max_length=10000)
    url_text = models.CharField(max_length=200)
    ingredients = models.ManyToManyField(Ingredient, through='RecipeIngredients')

    def __str__(self):
        return self.name_text + "\n" + self.steps_text


class Meal(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField()
    start_date = models.DateField()
    recipe = models.ForeignKey(Recipe, on_delete=models.CASCADE)
    #variety = models.ForeignKey(Variety, on_delete=models.CASCADE)

    @property
    def get_html_url(self):
        url = reverse('kondate:meal_edit', args=(self.id,))
        return f'<a href="{url}"> {self.title} </a>'


class RecipeIngredients(models.Model):
    recipe = models.ForeignKey(Recipe, on_delete=models.CASCADE, null=True)
    ingredient = models.ForeignKey(Ingredient, on_delete=models.CASCADE, null=True)
    amount = models.CharField(max_length=50, null=True)

