import datetime as dt

import pytest

from kondate.models import Ingredient, Meal, ShoppingCheck
from kondate.planning import build_shopping_list, week_days, week_start_for

from .conftest import MONDAY


@pytest.mark.parametrize("offset", range(7))
def test_week_starts_on_monday_by_default(offset):
    assert week_start_for(MONDAY + dt.timedelta(days=offset)) == MONDAY


def test_week_start_is_configurable(settings):
    settings.KONDATE_WEEK_START = 6  # Sunday
    sunday = MONDAY - dt.timedelta(days=1)
    assert week_start_for(MONDAY) == sunday
    assert week_start_for(sunday) == sunday
    assert week_start_for(sunday + dt.timedelta(days=6)) == sunday


def test_week_days_has_seven_consecutive_days():
    days = week_days(MONDAY)
    assert len(days) == 7 and days[0] == MONDAY and days[-1] == MONDAY + dt.timedelta(days=6)


@pytest.mark.django_db
def test_shopping_list_merges_ingredients_across_meals(make_recipe, plan):
    P, D, S = Ingredient.Category.PRODUCE, Ingredient.Category.DAIRY, Ingredient.Category.SPICES
    tacos = make_recipe("T1", [("Onion1", "1", P), ("Cheese1", "1 cup", D), ("Salt1", "", S, True)])
    soup = make_recipe("S1", [("onion1", "2", P)])  # same ingredient, different case
    plan(tacos, MONDAY)
    plan(soup, MONDAY + dt.timedelta(days=2))
    plan(soup, MONDAY + dt.timedelta(days=7))  # next week: excluded
    plan(None, MONDAY, note="eat out")  # note-only meal: ignored

    shopping = build_shopping_list(MONDAY)

    assert [s.label for s in shopping.sections] == ["Produce", "Dairy & eggs"]
    onion = shopping.sections[0].lines[0]
    assert onion.ingredient.name == "Onion1"
    assert onion.amounts == "1 + 2"
    assert [n.recipe for n in onion.needs] == ["T1", "S1"]
    assert [ln.ingredient.name for ln in shopping.staples] == ["Salt1"]
    assert shopping.remaining == 2


@pytest.mark.django_db
def test_shopping_list_reflects_checks_for_that_week_only(make_recipe, plan):
    recipe = make_recipe("R1", [("Leek1", "1")])
    plan(recipe, MONDAY)
    leek = Ingredient.objects.get(name="Leek1")
    ShoppingCheck.objects.create(week_start=MONDAY, ingredient=leek)
    ShoppingCheck.objects.create(week_start=MONDAY - dt.timedelta(days=7), ingredient=leek)

    shopping = build_shopping_list(MONDAY)
    assert shopping.sections[0].lines[0].checked is True
    assert shopping.remaining == 0


@pytest.mark.django_db
def test_shopping_list_query_count_is_constant(make_recipe, plan, django_assert_num_queries):
    for i in range(6):
        recipe = make_recipe(f"Q{i}", [(f"QI{i}a", "1"), (f"QI{i}b", "2")])
        plan(recipe, MONDAY + dt.timedelta(days=i))
    # 1: meals JOIN recipe, 2: recipe items JOIN ingredient (prefetch), 3: checks
    with django_assert_num_queries(3):
        shopping = build_shopping_list(MONDAY)
    assert sum(len(s.lines) for s in shopping.sections) == 12


@pytest.mark.django_db
def test_meal_requires_recipe_or_note_at_db_level():
    from django.db import IntegrityError

    with pytest.raises(IntegrityError):
        Meal.objects.create(date=MONDAY, recipe=None, note="")


@pytest.mark.django_db
def test_seed_migration_loaded_original_recipes():
    from kondate.models import Recipe

    assert Recipe.objects.count() >= 33
    kabob = Recipe.objects.get(name="chicken kabob")
    amounts = {i.ingredient.name: i.amount for i in kabob.items.select_related("ingredient")}
    assert amounts["chicken breast"] == "4 breast halves"
    assert Ingredient.objects.get(name="salt").is_staple
