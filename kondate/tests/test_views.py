import datetime as dt

import pytest
from django.core.management import call_command
from django.urls import reverse

from kondate.models import Ingredient, Meal, Recipe, ShoppingCheck, ShoppingExtra

from .conftest import MONDAY

pytestmark = pytest.mark.django_db

DAY = MONDAY.isoformat()


# --- access ---------------------------------------------------------------

@pytest.mark.parametrize(
    "url",
    [
        reverse("kondate:week"),
        reverse("kondate:recipe_list"),
        reverse("kondate:shopping"),
        reverse("kondate:ingredient_list"),
        reverse("kondate:meal_new"),
    ],
)
def test_pages_require_login(client, url):
    response = client.get(url)
    assert response.status_code == 302
    assert response["Location"].startswith(reverse("login"))


def test_writes_require_login(client, make_recipe):
    recipe = make_recipe("Locked")
    response = client.post(reverse("kondate:recipe_delete", args=[recipe.pk]))
    assert response.status_code == 302 and Recipe.objects.filter(pk=recipe.pk).exists()


def test_head_requests_allowed(client_in):
    assert client_in.head(reverse("kondate:week")).status_code == 200


def test_healthz_is_public(client):
    response = client.get(reverse("kondate:healthz"))
    assert response.status_code == 200 and response.content == b"ok"


def test_login_page_renders(client):
    assert client.get(reverse("login")).status_code == 200


# --- week planner ----------------------------------------------------------

def test_week_page_shows_planned_meals(client_in, make_recipe, plan):
    plan(make_recipe("Oyako1"), MONDAY + dt.timedelta(days=3))
    response = client_in.get(reverse("kondate:week_of", args=[DAY]))
    assert response.status_code == 200
    assert b"Oyako1" in response.content
    assert response.context["planned_count"] == 1


def test_week_page_bad_date_is_404(client_in):
    assert client_in.get("/week/not-a-date/").status_code == 404


def test_week_page_query_count(client_in, make_recipe, plan, django_assert_max_num_queries):
    for i in range(7):
        plan(make_recipe(f"W{i}", [(f"WI{i}", "1")]), MONDAY + dt.timedelta(days=i))
    # session + user + meals JOIN recipe + recipe items prefetch
    with django_assert_max_num_queries(4):
        assert client_in.get(reverse("kondate:week_of", args=[DAY])).status_code == 200


def test_create_meal(client_in, make_recipe):
    recipe = make_recipe("Lasagna1")
    response = client_in.post(
        reverse("kondate:meal_new"), {"date": DAY, "slot": Meal.Slot.DINNER, "recipe": recipe.pk, "note": ""}
    )
    assert response.status_code == 302
    assert response["Location"] == reverse("kondate:week_of", args=[DAY])
    assert Meal.objects.get().recipe == recipe


def test_create_note_only_meal(client_in):
    client_in.post(reverse("kondate:meal_new"), {"date": DAY, "slot": Meal.Slot.LUNCH, "note": "Eat out"})
    assert Meal.objects.get().title == "Eat out"


def test_meal_needs_recipe_or_note(client_in):
    response = client_in.post(reverse("kondate:meal_new"), {"date": DAY, "slot": Meal.Slot.DINNER, "note": "  "})
    assert response.status_code == 200
    assert "Pick a recipe or write a note." in response.content.decode()
    assert not Meal.objects.exists()


def test_new_meal_prefills_from_query(client_in, make_recipe):
    recipe = make_recipe("Prefill1")
    response = client_in.get(reverse("kondate:meal_new"), {"date": DAY, "slot": 1, "recipe": recipe.pk})
    form = response.context["form"]
    assert form.initial["date"] == DAY and str(form.initial["recipe"]) == str(recipe.pk)


def test_delete_meal_requires_post(client_in, make_recipe, plan):
    meal = plan(make_recipe("Del1"), MONDAY)
    assert client_in.get(reverse("kondate:meal_delete", args=[meal.pk])).status_code == 405
    client_in.post(reverse("kondate:meal_delete", args=[meal.pk]))
    assert not Meal.objects.filter(pk=meal.pk).exists()


def test_copy_previous_week(client_in, make_recipe, plan):
    recipe = make_recipe("Copy1")
    plan(recipe, MONDAY - dt.timedelta(days=5), slot=Meal.Slot.LUNCH)
    plan(None, MONDAY - dt.timedelta(days=1), note="leftovers")
    client_in.post(reverse("kondate:week_copy_previous", args=[DAY]))
    copied = Meal.objects.filter(date__gte=MONDAY).order_by("date")
    assert [(m.date, m.title) for m in copied] == [
        (MONDAY + dt.timedelta(days=2), "Copy1"),
        (MONDAY + dt.timedelta(days=6), "leftovers"),
    ]


def test_copy_previous_week_refuses_non_empty_week(client_in, make_recipe, plan):
    plan(make_recipe("Prev1"), MONDAY - dt.timedelta(days=7))
    plan(make_recipe("Already1"), MONDAY)
    client_in.post(reverse("kondate:week_copy_previous", args=[DAY]))
    assert Meal.objects.filter(date__gte=MONDAY).count() == 1


# --- recipes ---------------------------------------------------------------

def _recipe_post(name, rows, **extra):
    data = {"name": name, "url": "", "notes": "", "items-TOTAL_FORMS": str(len(rows)), "items-INITIAL_FORMS": "0"}
    for i, (ingredient, amount, *delete) in enumerate(rows):
        data[f"items-{i}-ingredient"] = ingredient
        data[f"items-{i}-amount"] = amount
        if delete:
            data[f"items-{i}-DELETE"] = "on"
    data.update(extra)
    return data


def test_create_recipe_reuses_and_creates_ingredients(client_in):
    Ingredient.objects.create(name="Mirin1")
    response = client_in.post(
        reverse("kondate:recipe_new"),
        _recipe_post("Teriyaki1", [("mirin1", "2 tbsp"), ("  Brand  New  Thing ", "1"), ("", ""), ("Dropme1", "1", True)]),
    )
    recipe = Recipe.objects.get(name="Teriyaki1")
    assert response["Location"] == recipe.get_absolute_url()
    items = {i.ingredient.name: i.amount for i in recipe.items.select_related("ingredient")}
    assert items == {"Mirin1": "2 tbsp", "Brand New Thing": "1"}
    assert Ingredient.objects.filter(name__iexact="mirin1").count() == 1
    assert not Ingredient.objects.filter(name="Dropme1").exists()


def test_edit_recipe_replaces_items(client_in, make_recipe):
    recipe = make_recipe("Edit1", [("EA1", "1"), ("EB1", "2")])
    client_in.post(reverse("kondate:recipe_edit", args=[recipe.pk]), _recipe_post("Edit1 v2", [("EB1", "3")]))
    recipe.refresh_from_db()
    assert recipe.name == "Edit1 v2"
    assert [(i.ingredient.name, i.amount) for i in recipe.items.all()] == [("EB1", "3")]


def test_recipe_rejects_duplicate_ingredient_rows(client_in):
    response = client_in.post(reverse("kondate:recipe_new"), _recipe_post("Dup1", [("Egg1", "1"), ("egg1", "2")]))
    assert response.status_code == 200
    assert not Recipe.objects.filter(name="Dup1").exists()


def test_recipe_name_unique_case_insensitive(client_in, make_recipe):
    make_recipe("Curry1")
    response = client_in.post(reverse("kondate:recipe_new"), _recipe_post("CURRY1", []))
    assert response.status_code == 200
    assert Recipe.objects.filter(name__iexact="curry1").count() == 1


def test_recipe_edit_page_renders(client_in, make_recipe):
    recipe = make_recipe("Render1", [("RI1", "1")])
    response = client_in.get(reverse("kondate:recipe_edit", args=[recipe.pk]))
    assert response.status_code == 200 and b'value="RI1"' in response.content


def test_recipe_list_search_and_stale_sort(client_in, make_recipe, plan):
    old = make_recipe("Qxstale Old", [("Fennel1", "1")])
    recent = make_recipe("Qxstale Recent")
    plan(old, MONDAY - dt.timedelta(days=60))
    plan(recent, MONDAY)
    response = client_in.get(reverse("kondate:recipe_list"), {"q": "fennel1"})
    assert [r.name for r in response.context["recipes"]] == ["Qxstale Old"]
    response = client_in.get(reverse("kondate:recipe_list"), {"q": "qxstale", "sort": "stale"})
    assert [r.name for r in response.context["recipes"]] == ["Qxstale Old", "Qxstale Recent"]


def test_recipe_detail(client_in, make_recipe):
    recipe = make_recipe("Detail1", [("DI1", "3 cloves")], url="https://example.com/r")
    response = client_in.get(recipe.get_absolute_url())
    assert b"3 cloves" in response.content and b"https://example.com/r" in response.content


def test_recipe_delete_blocked_when_planned(client_in, make_recipe, plan):
    recipe = make_recipe("Planned1")
    plan(recipe, MONDAY)
    client_in.post(reverse("kondate:recipe_delete", args=[recipe.pk]))
    assert Recipe.objects.filter(pk=recipe.pk).exists()


def test_recipe_delete(client_in, make_recipe):
    recipe = make_recipe("Gone1", [("GI1", "1")])
    response = client_in.post(reverse("kondate:recipe_delete", args=[recipe.pk]))
    assert response["Location"] == reverse("kondate:recipe_list")
    assert not Recipe.objects.filter(pk=recipe.pk).exists()


# --- ingredients -----------------------------------------------------------

def test_ingredient_bulk_edit(client_in):
    response = client_in.get(reverse("kondate:ingredient_list"))
    formset = response.context["formset"]
    data = {
        "form-TOTAL_FORMS": str(formset.total_form_count()),
        "form-INITIAL_FORMS": str(formset.initial_form_count()),
    }
    target = None
    for i, form in enumerate(formset.forms):
        data[f"form-{i}-id"] = form.instance.pk
        data[f"form-{i}-category"] = form.instance.category
        if form.instance.is_staple:
            data[f"form-{i}-is_staple"] = "on"
        if form.instance.name == "zucchini":
            target = i
            data[f"form-{i}-category"] = Ingredient.Category.FROZEN
            data[f"form-{i}-is_staple"] = "on"
    assert target is not None
    sections = [f.instance.category for f in formset.forms]
    ranks = [Ingredient.Category.values.index(c) for c in sections]
    assert ranks == sorted(ranks), "sections should follow store-walk order"
    response = client_in.post(reverse("kondate:ingredient_list"), data)
    assert response.status_code == 302
    zucchini = Ingredient.objects.get(name="zucchini")
    assert zucchini.category == Ingredient.Category.FROZEN and zucchini.is_staple


# --- shopping ---------------------------------------------------------------

def test_shopping_page(client_in, make_recipe, plan):
    plan(make_recipe("Shop1", [("Basil1", "1 bunch", Ingredient.Category.PRODUCE)]), MONDAY)
    response = client_in.get(reverse("kondate:shopping_week", args=[DAY]))
    assert response.status_code == 200
    assert b"Basil1" in response.content and b"1 bunch" in response.content


def test_shopping_check_sets_state_idempotently(client_in, make_recipe):
    make_recipe("Chk1", [("Chive1", "1")])
    chive = Ingredient.objects.get(name="Chive1")
    url = reverse("kondate:shopping_check", args=[(MONDAY + dt.timedelta(days=3)).isoformat(), chive.pk])
    for _ in range(2):
        response = client_in.post(url, {"checked": "1"}, headers={"Accept": "application/json"})
        assert response.json() == {"checked": True}
    # keyed on the week start, whichever day of the week was in the URL
    assert ShoppingCheck.objects.filter(week_start=MONDAY, ingredient=chive).count() == 1
    response = client_in.post(url, {"checked": "0"})
    assert response.status_code == 302
    assert not ShoppingCheck.objects.exists()


def test_shopping_check_unknown_ingredient_404(client_in):
    url = reverse("kondate:shopping_check", args=[DAY, 999999])
    assert client_in.post(url, {"checked": "1"}).status_code == 404


def test_shopping_extras_lifecycle(client_in):
    client_in.post(reverse("kondate:shopping_extra_add", args=[(MONDAY + dt.timedelta(days=1)).isoformat()]), {"name": "Coffee"})
    extra = ShoppingExtra.objects.get()
    assert extra.week_start == MONDAY
    client_in.post(reverse("kondate:shopping_extra_check", args=[extra.pk]), {"checked": "1"})
    extra.refresh_from_db()
    assert extra.checked
    client_in.post(reverse("kondate:shopping_reset", args=[DAY]))
    extra.refresh_from_db()
    assert not extra.checked
    client_in.post(reverse("kondate:shopping_extra_delete", args=[extra.pk]))
    assert not ShoppingExtra.objects.exists()


def test_shopping_extra_rejects_blank(client_in):
    client_in.post(reverse("kondate:shopping_extra_add", args=[DAY]), {"name": ""})
    assert not ShoppingExtra.objects.exists()


# --- ops --------------------------------------------------------------------

def test_ensure_superuser(monkeypatch, django_user_model):
    monkeypatch.setenv("DJANGO_SUPERUSER_USERNAME", "admin1")
    monkeypatch.setenv("DJANGO_SUPERUSER_PASSWORD", "first-password-123")
    call_command("ensure_superuser")
    monkeypatch.setenv("DJANGO_SUPERUSER_PASSWORD", "changed-password-456")
    call_command("ensure_superuser")  # no-op: never overwrites
    admin = django_user_model.objects.get(username="admin1")
    assert admin.is_superuser and admin.check_password("first-password-123")
