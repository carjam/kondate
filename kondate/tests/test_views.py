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
    # session, user, meals JOIN recipe, recipe items, picker recipes, picker ingredients
    with django_assert_max_num_queries(6):
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
        data[f"form-{i}-stock"] = form.instance.stock
        data[f"form-{i}-usual_amount"] = form.instance.usual_amount
        if form.instance.name == "zucchini":
            target = i
            data[f"form-{i}-category"] = Ingredient.Category.FROZEN
            data[f"form-{i}-stock"] = Ingredient.Stock.WEEKLY
            data[f"form-{i}-usual_amount"] = "3"
    assert target is not None
    sections = [f.instance.category for f in formset.forms]
    ranks = [Ingredient.Category.values.index(c) for c in sections]
    assert ranks == sorted(ranks), "sections should follow store-walk order"
    response = client_in.post(reverse("kondate:ingredient_list"), data)
    assert response.status_code == 302
    zucchini = Ingredient.objects.get(name="zucchini")
    assert zucchini.category == Ingredient.Category.FROZEN
    assert zucchini.stock == Ingredient.Stock.WEEKLY and zucchini.usual_amount == "3"


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
        assert response.json()["checked"] is True
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


def test_tick_response_carries_refreshed_text(client_in, make_recipe, plan):
    plan(make_recipe("Txt1", [("Ginger1", "1 knob"), ("Garlic1", "2")]), MONDAY)
    ginger = Ingredient.objects.get(name="Ginger1")
    url = reverse("kondate:shopping_check", args=[DAY, ginger.pk])
    data = client_in.post(url, {"checked": "1"}, headers={"Accept": "application/json"}).json()
    assert data["checked"] is True
    assert "☐ Garlic1 — 2" in data["text"] and "Ginger1" not in data["text"]


def test_shopping_page_embeds_copyable_text(client_in, make_recipe, plan):
    plan(make_recipe("Txt2", [("Leek2", "2")]), MONDAY)
    response = client_in.get(reverse("kondate:shopping_week", args=[DAY]))
    assert "☐ Leek2 — 2" in response.context["shopping_text"]
    assert b"data-copy" in response.content and b"mailto:" in response.content


def test_add_every_week_item_makes_a_regular(client_in):
    Ingredient.objects.create(name="Eggs1", category=Ingredient.Category.DAIRY)
    url = reverse("kondate:shopping_extra_add", args=[DAY])
    client_in.post(url, {"name": " eggs1 ", "every_week": "on"})
    client_in.post(url, {"name": "Oat milk", "every_week": "on"})
    assert not ShoppingExtra.objects.exists()
    assert Ingredient.objects.get(name="Eggs1").stock == Ingredient.Stock.WEEKLY
    assert Ingredient.objects.get(name="Oat milk").stock == Ingredient.Stock.WEEKLY
    # ...and next week they're on the list without doing anything.
    next_week = (MONDAY + dt.timedelta(days=7)).isoformat()
    response = client_in.get(reverse("kondate:shopping_week", args=[next_week]))
    assert {i.name for i in response.context["shopping"].regulars} == {"Eggs1", "Oat milk"}


def test_stop_weekly(client_in):
    eggs = Ingredient.objects.create(name="Eggs2", stock=Ingredient.Stock.WEEKLY)
    response = client_in.post(reverse("kondate:ingredient_stop_weekly", args=[eggs.pk]), {"day": DAY})
    assert response["Location"] == reverse("kondate:shopping_week", args=[DAY])
    eggs.refresh_from_db()
    assert eggs.stock == Ingredient.Stock.AS_NEEDED


def test_new_trip_brings_back_regulars_only(client_in, make_recipe, plan):
    milk = Ingredient.objects.create(name="Milk3", stock=Ingredient.Stock.WEEKLY)
    plan(make_recipe("Trip1", [("Basil3", "1")]), MONDAY)
    basil = Ingredient.objects.get(name="Basil3")
    for ingredient in (milk, basil):
        ShoppingCheck.objects.create(week_start=MONDAY, ingredient=ingredient)
    ShoppingExtra.objects.create(week_start=MONDAY, name="Bought1", checked=True)
    ShoppingExtra.objects.create(week_start=MONDAY, name="Still need1")

    client_in.post(reverse("kondate:shopping_new_trip", args=[DAY]))

    assert list(ShoppingCheck.objects.values_list("ingredient__name", flat=True)) == ["Basil3"]
    assert list(ShoppingExtra.objects.values_list("name", flat=True)) == ["Still need1"]


def test_week_page_offers_quick_plan_picker(client_in, make_recipe, plan):
    old = make_recipe("Pick old", [("Pk1", "1")])
    make_recipe("Pick never")
    this_week = make_recipe("Pick this week")
    plan(old, MONDAY - dt.timedelta(days=30))
    plan(this_week, MONDAY)
    response = client_in.get(reverse("kondate:week_of", args=[DAY]))
    suggestions = [r.name for r in response.context["suggestions"]]
    assert suggestions[0] == "Pick old"  # longest-ago first
    assert "Pick this week" not in suggestions
    assert b'id="planner"' in response.content
    assert b'data-search="pick old pk1"' in response.content


def test_meal_form_uses_slot_radios(client_in):
    response = client_in.get(reverse("kondate:meal_new"), {"date": DAY})
    assert b'type="radio" name="slot"' in response.content


def test_edit_meal_moves_it_and_says_updated(client_in, make_recipe, plan):
    meal = plan(make_recipe("Move1"), MONDAY)
    next_week = MONDAY + dt.timedelta(days=9)
    response = client_in.post(
        reverse("kondate:meal_edit", args=[meal.pk]),
        {"date": next_week.isoformat(), "slot": Meal.Slot.LUNCH, "recipe": meal.recipe_id, "note": ""},
        follow=True,
    )
    meal.refresh_from_db()
    assert (meal.date, meal.slot) == (next_week, Meal.Slot.LUNCH)
    assert response.redirect_chain[-1][0] == reverse("kondate:week_of", args=[(MONDAY + dt.timedelta(days=7)).isoformat()])
    assert "Updated Move1" in response.content.decode()


def test_admin_link_only_for_staff(client_in, user):
    url = reverse("kondate:ingredient_list")
    assert b"/admin/" not in client_in.get(url).content
    user.is_staff = True
    user.save()
    assert b"/admin/" in client_in.get(url).content


def test_pages_send_a_strict_content_security_policy(client_in):
    policy = client_in.get(reverse("kondate:week"))["Content-Security-Policy"]
    assert "script-src 'self'" in policy and "style-src 'self'" in policy
    assert "unsafe-inline" not in policy


def test_templates_have_no_inline_styles_or_scripts():
    """The CSP forbids them, so they'd silently break in the browser."""
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    offenders = [
        str(path.relative_to(root))
        for path in [*root.glob("kondate/templates/**/*.html"), *root.glob("templates/**/*.html")]
        if re.search(r'style="|<script(?![^>]*\bsrc=)|\son[a-z]+="', path.read_text())
    ]
    assert offenders == []


# --- ops --------------------------------------------------------------------

def test_ensure_superuser(monkeypatch, django_user_model):
    monkeypatch.setenv("DJANGO_SUPERUSER_USERNAME", "admin1")
    monkeypatch.setenv("DJANGO_SUPERUSER_PASSWORD", "first-password-123")
    call_command("ensure_superuser")
    monkeypatch.setenv("DJANGO_SUPERUSER_PASSWORD", "changed-password-456")
    call_command("ensure_superuser")  # no-op: never overwrites
    admin = django_user_model.objects.get(username="admin1")
    assert admin.is_superuser and admin.check_password("first-password-123")
