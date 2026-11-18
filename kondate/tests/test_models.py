import pytest
from django.db import IntegrityError

from kondate.models import Ingredient, Meal, Recipe

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


@pytest.mark.parametrize(
    ("name", "parts"),
    [
        ("Gyoza (オークジェネラルのしっかり味付け餃子)", ("Gyoza", "オークジェネラルのしっかり味付け餃子")),
        ("Hayashi rice（ハヤシライス）", ("Hayashi rice", "ハヤシライス")),
        ("Deluxe okonomiyaki with oysters (デラックスお好み焼き\u3000カーキ入り)", ("Deluxe okonomiyaki with oysters", "デラックスお好み焼き\u3000カーキ入り")),
        ("chili (mild)", ("chili (mild)", "")),  # not Japanese: left whole
        ("omu rice", ("omu rice", "")),
    ],
)
def test_recipe_name_parts(name, parts):
    assert Recipe(name=name).name_parts == parts


def test_meal_title_parts():
    recipe = Recipe(pk=1, name="Gyoza (餃子)")
    assert Meal(recipe=recipe).title_parts == ("Gyoza", "餃子")
    assert Meal(note="eat out").title_parts == ("eat out", "")
