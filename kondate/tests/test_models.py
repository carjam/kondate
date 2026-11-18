import pytest
from django.db import IntegrityError

from kondate.models import Ingredient, Meal

from .conftest import MONDAY

pytestmark = pytest.mark.django_db


def test_meal_requires_recipe_or_note_at_db_level():

    with pytest.raises(IntegrityError):
        Meal.objects.create(date=MONDAY, recipe=None, note="")


def test_ingredients_in_store_order():
    names = ["Zz frozen1", "Aa produce1", "Mm other1"]
    Ingredient.objects.create(name=names[0], category=Ingredient.Category.FROZEN)
    Ingredient.objects.create(name=names[1], category=Ingredient.Category.PRODUCE)
    Ingredient.objects.create(name=names[2], category=Ingredient.Category.OTHER)
    ordered = [i.name for i in Ingredient.objects.filter(name__in=names).in_store_order()]
    assert ordered == ["Aa produce1", "Zz frozen1", "Mm other1"]
