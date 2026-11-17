import datetime as dt

from django.contrib import messages
from django.contrib.auth.decorators import login_not_required
from django.db import transaction
from django.db.models import Case, Count, F, Max, ProtectedError, Q, Value, When
from django.db.models.functions import Lower
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_safe, require_POST

from .forms import (
    IngredientFormSet,
    MealForm,
    RecipeForm,
    RecipeItemFormSet,
    ShoppingExtraForm,
)
from .models import Ingredient, Meal, Recipe, RecipeIngredient, ShoppingCheck, ShoppingExtra
from .planning import (
    build_shopping_list,
    current_week_start,
    meals_in_week,
    week_days,
    week_start_for,
)


def _parse_day(value: str) -> dt.date:
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        raise Http404("Not a valid date") from None


def _week_nav(start: dt.date) -> dict:
    return {
        "week_start": start,
        "week_end": start + dt.timedelta(days=6),
        "prev_week": start - dt.timedelta(days=7),
        "next_week": start + dt.timedelta(days=7),
        "this_week": current_week_start(),
    }


def _wants_json(request) -> bool:
    return "application/json" in request.headers.get("Accept", "")


@login_not_required
@require_safe
def healthz(request):
    return HttpResponse("ok", content_type="text/plain")


# --- Week planner -----------------------------------------------------------


@require_safe
def week(request, day: str | None = None):
    start = week_start_for(_parse_day(day)) if day else current_week_start()
    meals = list(meals_in_week(start))
    days = [{"date": d, "meals": [m for m in meals if m.date == d]} for d in week_days(start)]
    context = {
        **_week_nav(start),
        "days": days,
        "today": timezone.localdate(),
        "planned_count": len(meals),
        "slots": Meal.Slot.choices,
    }
    return render(request, "kondate/week.html", context)


def meal_edit(request, pk: int | None = None):
    meal = get_object_or_404(Meal, pk=pk) if pk else None
    if request.method == "POST":
        form = MealForm(request.POST, instance=meal)
        if form.is_valid():
            meal = form.save()
            messages.success(request, f"Planned {meal.title} for {meal.date:%a %b} {meal.date.day}.")
            return redirect("kondate:week_of", day=week_start_for(meal.date).isoformat())
    else:
        initial = {}
        if meal is None:
            initial["date"] = request.GET.get("date") or timezone.localdate().isoformat()
            initial["slot"] = request.GET.get("slot") or Meal.Slot.DINNER
            if recipe_id := request.GET.get("recipe"):
                initial["recipe"] = recipe_id
        form = MealForm(instance=meal, initial=initial)
    return render(request, "kondate/meal_form.html", {"form": form, "meal": meal})


@require_POST
def meal_delete(request, pk: int):
    meal = get_object_or_404(Meal, pk=pk)
    week_of = week_start_for(meal.date)
    meal.delete()
    messages.success(request, f"Removed {meal.title}.")
    return redirect("kondate:week_of", day=week_of.isoformat())


@require_POST
def week_copy_previous(request, day: str):
    """Copy last week's plan into this week (only into an empty week)."""
    start = week_start_for(_parse_day(day))
    with transaction.atomic():
        if Meal.objects.filter(date__gte=start, date__lt=start + dt.timedelta(days=7)).exists():
            messages.error(request, "This week already has meals; clear it first.")
        else:
            previous = Meal.objects.filter(
                date__gte=start - dt.timedelta(days=7), date__lt=start
            )
            copies = [
                Meal(date=m.date + dt.timedelta(days=7), slot=m.slot, recipe_id=m.recipe_id, note=m.note)
                for m in previous
            ]
            Meal.objects.bulk_create(copies)
            messages.success(request, f"Copied {len(copies)} meals from last week.")
    return redirect("kondate:week_of", day=start.isoformat())


# --- Recipes ----------------------------------------------------------------


@require_safe
def recipe_list(request):
    q = request.GET.get("q", "").strip()
    sort = request.GET.get("sort", "name")
    recipes = Recipe.objects.annotate(
        item_count=Count("items", distinct=True),
        last_planned=Max("meals__date"),
    )
    if q:
        recipes = recipes.filter(
            Q(name__icontains=q) | Q(notes__icontains=q) | Q(items__ingredient__name__icontains=q)
        ).distinct()
    if sort == "stale":
        # Longest since last planned first; never-planned recipes lead.
        recipes = recipes.order_by(F("last_planned").asc(nulls_first=True), Lower("name"))
    else:
        sort = "name"
        recipes = recipes.order_by(Lower("name"))
    return render(request, "kondate/recipe_list.html", {"recipes": recipes, "q": q, "sort": sort})


@require_safe
def recipe_detail(request, pk: int):
    recipe = get_object_or_404(
        Recipe.objects.prefetch_related("items__ingredient"), pk=pk
    )
    upcoming = recipe.meals.filter(date__gte=timezone.localdate()).order_by("date")[:5]
    return render(request, "kondate/recipe_detail.html", {"recipe": recipe, "upcoming": upcoming})


def _ingredient_for(name: str) -> Ingredient:
    ingredient, _ = Ingredient.objects.get_or_create(name__iexact=name, defaults={"name": name})
    return ingredient


def recipe_edit(request, pk: int | None = None):
    recipe = get_object_or_404(Recipe, pk=pk) if pk else None
    if request.method == "POST":
        form = RecipeForm(request.POST, instance=recipe)
        formset = RecipeItemFormSet(request.POST, prefix="items")
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                recipe = form.save()
                recipe.items.all().delete()
                RecipeIngredient.objects.bulk_create(
                    RecipeIngredient(recipe=recipe, ingredient=_ingredient_for(name), amount=amount)
                    for name, amount in formset.rows()
                )
            messages.success(request, f"Saved {recipe.name}.")
            return redirect(recipe)
    else:
        form = RecipeForm(instance=recipe)
        initial = (
            [{"ingredient": i.ingredient.name, "amount": i.amount}
             for i in recipe.items.select_related("ingredient")]
            if recipe
            else []
        )
        formset = RecipeItemFormSet(initial=initial, prefix="items")
    context = {
        "form": form,
        "formset": formset,
        "recipe": recipe,
        "ingredient_names": Ingredient.objects.values_list("name", flat=True),
    }
    return render(request, "kondate/recipe_form.html", context)


@require_POST
def recipe_delete(request, pk: int):
    recipe = get_object_or_404(Recipe, pk=pk)
    try:
        recipe.delete()
    except ProtectedError:
        count = recipe.meals.count()
        messages.error(
            request, f"{recipe.name} is used by {count} planned meal(s); remove those first."
        )
        return redirect(recipe)
    messages.success(request, f"Deleted {recipe.name}.")
    return redirect("kondate:recipe_list")


# --- Ingredients ------------------------------------------------------------


def ingredient_list(request):
    store_order = Case(
        *(When(category=value, then=Value(rank)) for rank, value in enumerate(Ingredient.Category.values)),
        default=Value(len(Ingredient.Category.values)),
    )
    queryset = Ingredient.objects.annotate(recipe_count=Count("recipe_items")).order_by(
        store_order, Lower("name")
    )
    if request.method == "POST":
        formset = IngredientFormSet(request.POST, queryset=queryset)
        if formset.is_valid():
            formset.save()
            messages.success(request, "Ingredients updated.")
            return redirect("kondate:ingredient_list")
    else:
        formset = IngredientFormSet(queryset=queryset)
    return render(request, "kondate/ingredient_list.html", {"formset": formset})


# --- Shopping list ----------------------------------------------------------


@require_safe
def shopping(request, day: str | None = None):
    start = week_start_for(_parse_day(day)) if day else current_week_start()
    context = {
        **_week_nav(start),
        "shopping": build_shopping_list(start),
        "extras": ShoppingExtra.objects.filter(week_start=start),
        "extra_form": ShoppingExtraForm(),
    }
    return render(request, "kondate/shopping.html", context)


def _back_to_list(request, start: dt.date, payload: dict):
    if _wants_json(request):
        return JsonResponse(payload)
    return redirect("kondate:shopping_week", day=start.isoformat())


@require_POST
def shopping_check(request, day: str, ingredient_id: int):
    """Set (not toggle) the checked state, so two phones can't flip-flop it."""
    start = week_start_for(_parse_day(day))
    ingredient = get_object_or_404(Ingredient, pk=ingredient_id)
    checked = request.POST.get("checked") == "1"
    if checked:
        ShoppingCheck.objects.get_or_create(week_start=start, ingredient=ingredient)
    else:
        ShoppingCheck.objects.filter(week_start=start, ingredient=ingredient).delete()
    return _back_to_list(request, start, {"checked": checked})


@require_POST
def shopping_reset(request, day: str):
    start = week_start_for(_parse_day(day))
    ShoppingCheck.objects.filter(week_start=start).delete()
    ShoppingExtra.objects.filter(week_start=start).update(checked=False)
    messages.success(request, "Unchecked everything.")
    return redirect("kondate:shopping_week", day=start.isoformat())


@require_POST
def shopping_extra_add(request, day: str):
    start = week_start_for(_parse_day(day))
    form = ShoppingExtraForm(request.POST)
    if form.is_valid():
        extra = form.save(commit=False)
        extra.week_start = start
        extra.save()
    else:
        messages.error(request, "Item name can't be empty.")
    return redirect(reverse("kondate:shopping_week", kwargs={"day": start.isoformat()}) + "#extras")


@require_POST
def shopping_extra_check(request, pk: int):
    extra = get_object_or_404(ShoppingExtra, pk=pk)
    extra.checked = request.POST.get("checked") == "1"
    extra.save(update_fields=["checked"])
    return _back_to_list(request, extra.week_start, {"checked": extra.checked})


@require_POST
def shopping_extra_delete(request, pk: int):
    extra = get_object_or_404(ShoppingExtra, pk=pk)
    extra.delete()
    return redirect(reverse("kondate:shopping_week", kwargs={"day": extra.week_start.isoformat()}) + "#extras")
