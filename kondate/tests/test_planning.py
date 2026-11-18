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
    tacos = make_recipe("T1", [("Onion1", "1", P), ("Cheese1", "1 cup", D), ("Salt1", "", S, Ingredient.Stock.PANTRY)])
    soup = make_recipe("S1", [("onion1", "2", P)])  # same ingredient, different case
    plan(tacos, MONDAY)
    plan(soup, MONDAY + dt.timedelta(days=2))
    plan(soup, MONDAY + dt.timedelta(days=7))  # next week: excluded
    plan(None, MONDAY, note="eat out")  # note-only meal: ignored

    shopping = build_shopping_list(MONDAY)

    assert [s.label for s in shopping.sections] == ["Produce", "Dairy & eggs"]
    onion = shopping.sections[0].lines[0]
    assert onion.ingredient.name == "Onion1"
    assert onion.amounts == "3"  # same unit (none), so added up
    assert [n.recipe for n in onion.needs] == ["T1", "S1"]
    assert [ln.ingredient.name for ln in shopping.pantry] == ["Salt1"]
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
    # meals JOIN recipe, recipe items JOIN ingredient, weekly regulars, checks, extras
    with django_assert_num_queries(5):
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
    # 0002 seeded is_staple=True; 0003 turned that into "usually have it".
    assert Ingredient.objects.get(name="salt").stock == Ingredient.Stock.PANTRY
    import json
    from pathlib import Path

    seed = json.loads((Path(__file__).parents[1] / "seed" / "recipes_2021.json").read_text())
    staples = [i["name"] for i in seed["ingredients"] if i["is_staple"]]
    assert set(
        Ingredient.objects.filter(name__in=staples).values_list("stock", flat=True)
    ) == {Ingredient.Stock.PANTRY}


@pytest.mark.django_db
def test_weekly_regulars_are_always_on_the_list(make_recipe, plan):
    P, D = Ingredient.Category.PRODUCE, Ingredient.Category.DAIRY
    milk = Ingredient.objects.create(
        name="Milk1", category=D, stock=Ingredient.Stock.WEEKLY, usual_amount="1 gallon"
    )
    Ingredient.objects.create(name="Bananas1", category=P, stock=Ingredient.Stock.WEEKLY)

    # No meals planned: regulars alone make a list.
    shopping = build_shopping_list(MONDAY)
    assert [ln.ingredient.name for s in shopping.sections for ln in s.lines] == ["Bananas1", "Milk1"]
    assert [i.name for i in shopping.regulars] == ["Bananas1", "Milk1"]

    # A recipe that also needs milk merges into the same line.
    plan(make_recipe("Pancakes1", [("milk1", "1 cup", D)]), MONDAY)
    shopping = build_shopping_list(MONDAY)
    line = next(ln for s in shopping.sections for ln in s.lines if ln.ingredient == milk)
    assert line.weekly and line.amounts == "1 gallon + 1 cup"
    assert [n.recipe for n in line.needs] == ["Pancakes1"]


@pytest.mark.django_db
def test_shopping_list_text_lists_what_is_left(make_recipe, plan):
    from kondate.models import ShoppingExtra
    from kondate.planning import shopping_list_text

    P, S = Ingredient.Category.PRODUCE, Ingredient.Category.SPICES
    plan(make_recipe("Tacos1", [("Lime1", "2", P), ("Cilantro1", "1 bunch", P), ("Cumin1", "1 tsp", S, Ingredient.Stock.PANTRY)]), MONDAY)
    plan(None, MONDAY + dt.timedelta(days=1), note="leftovers", slot=Meal.Slot.LUNCH)
    ShoppingCheck.objects.create(week_start=MONDAY, ingredient=Ingredient.objects.get(name="Cilantro1"))
    ShoppingExtra.objects.create(week_start=MONDAY, name="Coffee")
    ShoppingExtra.objects.create(week_start=MONDAY, name="Foil", checked=True)

    text = shopping_list_text(build_shopping_list(MONDAY))

    assert text == (
        "Shopping list · Nov 16–22\n"
        "\n"
        "PRODUCE\n"
        "☐ Lime1 — 2\n"
        "\n"
        "EXTRAS\n"
        "☐ Coffee\n"
        "\n"
        "CHECK THE PANTRY FIRST\n"
        "☐ Cumin1 — 1 tsp\n"
        "\n"
        "MEALS THIS WEEK\n"
        "Mon  Tacos1\n"
        "Tue  leftovers (lunch)\n"
    )


@pytest.mark.django_db
def test_recipe_data_migration_filled_empty_recipes_and_added_cookpad():
    from kondate.models import Recipe

    assert not Recipe.objects.filter(items__isnull=True).exists(), "every recipe has ingredients"
    hot_dogs = {i.ingredient.name: i.amount for i in Recipe.objects.get(name="hot dogs").items.all()}
    assert hot_dogs["sour krout"] == "" and hot_dogs["mustard"] == "good mustard"

    assert Recipe.objects.filter(notes__contains="Campfire Cooking in Another World").count() == 12
    gyoza = Recipe.objects.get(name__startswith="Gyoza")
    assert gyoza.items.count() == 14
    # Translated names reuse the 2021 ingredients, so the shopping list merges them.
    assert Ingredient.objects.filter(name__iexact="jasmine rice").count() == 1
    assert Ingredient.objects.get(name="jasmine rice").recipes.filter(name__startswith="Hayashi").exists()
    assert Ingredient.objects.get(name="nutmeg").stock == Ingredient.Stock.PANTRY
