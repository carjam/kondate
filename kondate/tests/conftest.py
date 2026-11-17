import datetime as dt

import pytest

from kondate.models import Ingredient, Meal, Recipe, RecipeIngredient

MONDAY = dt.date(2026, 11, 16)


@pytest.fixture(autouse=True)
def _test_env(settings, monkeypatch):
    settings.KONDATE_WEEK_START = 0
    # Tests run with production settings in CI; the test client speaks plain HTTP.
    settings.SECURE_SSL_REDIRECT = False
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user("cook", password="pw-for-tests-only")


@pytest.fixture
def client_in(client, user):
    client.force_login(user)
    return client


@pytest.fixture
def make_recipe(db):
    def _make(name, items=(), **kwargs):
        recipe = Recipe.objects.create(name=name, **kwargs)
        for ingredient_name, amount, *rest in items:
            category = rest[0] if rest else Ingredient.Category.OTHER
            staple = rest[1] if len(rest) > 1 else False
            ingredient, _ = Ingredient.objects.get_or_create(
                name__iexact=ingredient_name,
                defaults={"name": ingredient_name, "category": category, "is_staple": staple},
            )
            RecipeIngredient.objects.create(recipe=recipe, ingredient=ingredient, amount=amount)
        return recipe

    return _make


@pytest.fixture
def plan(db):
    def _plan(recipe, date, slot=Meal.Slot.DINNER, note=""):
        return Meal.objects.create(recipe=recipe, date=date, slot=slot, note=note)

    return _plan
