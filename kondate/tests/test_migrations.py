"""What the data migrations leave behind (pytest-django runs them all
before the suite), plus the merge branch of 0005 called directly."""

import importlib
import json
from pathlib import Path

import pytest
from django.apps import apps

from kondate.models import Ingredient, Recipe, ShoppingCheck

from .conftest import MONDAY

pytestmark = pytest.mark.django_db

fix_spellings = importlib.import_module("kondate.migrations.0005_fix_spellings").fix_spellings


def test_seed_migration_loaded_original_recipes():

    assert Recipe.objects.count() >= 33
    kabob = Recipe.objects.get(name="chicken kabob")
    amounts = {i.ingredient.name: i.amount for i in kabob.items.select_related("ingredient")}
    assert amounts["chicken breast"] == "4 breast halves"
    # 0002 seeded is_staple=True; 0003 turned that into "usually have it".
    assert Ingredient.objects.get(name="salt").stock == Ingredient.Stock.PANTRY

    seed = json.loads((Path(__file__).parents[1] / "seed" / "recipes_2021.json").read_text())
    staples = [i["name"] for i in seed["ingredients"] if i["is_staple"]]
    assert set(
        Ingredient.objects.filter(name__in=staples).values_list("stock", flat=True)
    ) == {Ingredient.Stock.PANTRY}


def test_recipe_data_migration_filled_empty_recipes_and_added_cookpad():

    assert not Recipe.objects.filter(items__isnull=True).exists(), "every recipe has ingredients"
    hot_dogs = {i.ingredient.name: i.amount for i in Recipe.objects.get(name="hot dogs").items.all()}
    assert hot_dogs["sauerkraut"] == "" and hot_dogs["mustard"] == "good mustard"

    assert Recipe.objects.filter(notes__contains="Campfire Cooking in Another World").count() == 12
    gyoza = Recipe.objects.get(name__startswith="Gyoza")
    assert gyoza.items.count() == 14
    # Translated names reuse the 2021 ingredients, so the shopping list merges them.
    assert Ingredient.objects.filter(name__iexact="jasmine rice").count() == 1
    assert Ingredient.objects.get(name="jasmine rice").recipes.filter(name__startswith="Hayashi").exists()
    assert Ingredient.objects.get(name="nutmeg").stock == Ingredient.Stock.PANTRY


def test_spelling_migration_renamed_seed_names():

    assert Recipe.objects.filter(name="pimento cheese sandwich").exists()
    assert Ingredient.objects.filter(name="mayonnaise").exists()
    assert not Ingredient.objects.filter(name__in=["mayonaise", "sour krout", "taragon"]).exists()


def test_spelling_migration_merges_into_an_existing_correct_name(make_recipe):
    """If both spellings exist, recipes and ticks move to the correct one."""

    wrong = Ingredient.objects.create(name="tumeric")
    right = Ingredient.objects.get(name="turmeric")
    both = make_recipe("Uses both1")
    both.items.create(ingredient=wrong, amount="1 tsp")
    both.items.create(ingredient=right, amount="2 tsp")
    only_wrong = make_recipe("Uses wrong1")
    only_wrong.items.create(ingredient=wrong, amount="1/2 tsp")
    ShoppingCheck.objects.create(week_start=MONDAY, ingredient=wrong)

    fix_spellings(apps, None)

    assert not Ingredient.objects.filter(pk=wrong.pk).exists()
    assert [(i.ingredient_id, i.amount) for i in both.items.all()] == [(right.pk, "2 tsp")]
    assert [(i.ingredient_id, i.amount) for i in only_wrong.items.all()] == [(right.pk, "1/2 tsp")]
    assert ShoppingCheck.objects.get().ingredient_id == right.pk
