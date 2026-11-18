import datetime as dt

from django.contrib import messages
from django.contrib.auth.decorators import login_not_required
from django.db import transaction
from django.db.models import Count, F, ProtectedError, Q
from django.db.models.functions import Lower
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.text import capfirst
from django.views.decorators.http import require_POST, require_safe

from .forms import (
    IngredientFormSet,
    MealForm,
    RecipeForm,
    RecipeItemFormSet,
    ShoppingExtraForm,
)
from .models import (
    Ingredient,
    Meal,
    Recipe,
    RecipeIngredient,
    ShoppingCheck,
    ShoppingExtra,
)
from .planning import (
    build_shopping_list,
    current_week_start,
    day_range,
    meals_in_week,
    shopping_list_text,
    week_days,
    week_start_for,
)


def _parse_day(value: str) -> dt.date:
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        raise Http404("Not a valid date") from None


def _week_of(day: str | None) -> dt.date:
    """Start of the planning week containing ``day`` (any ISO date), or of this week."""
    return week_start_for(_parse_day(day)) if day else current_week_start()


def _to_week(start: dt.date):
    return redirect("kondate:week_of", day=start.isoformat())


def _to_shopping(start: dt.date, anchor: str = ""):
    url = reverse("kondate:shopping_of", kwargs={"day": start.isoformat()})
    return redirect(url + (f"#{anchor}" if anchor else ""))


def _week_nav(start: dt.date) -> dict:
    end = start + dt.timedelta(days=6)
    return {
        "week_start": start,
        "week_end": end,
        "week_label": day_range(start, end),
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


def _picker_recipes(exclude_ids: set[int]) -> tuple[list[Recipe], list[Recipe]]:
    """All recipes for the quick-plan sheet, plus a few "haven't had in a while"
    suggestions: longest-ago first, then never-planned, skipping this week's."""
    recipes = list(Recipe.objects.for_browsing().order_by(Lower("name")))
    candidates = [r for r in recipes if r.pk not in exclude_ids]
    candidates.sort(key=lambda r: (r.last_planned is None, r.last_planned or dt.date.min))
    return recipes, candidates[:5]


@require_safe
def week(request, day: str | None = None):
    start = _week_of(day)
    meals = list(meals_in_week(start))
    days = [{"date": d, "meals": [m for m in meals if m.date == d]} for d in week_days(start)]
    recipes, suggestions = _picker_recipes({m.recipe_id for m in meals if m.recipe_id})
    dinners = sum(1 for m in meals if m.slot == Meal.Slot.DINNER)
    context = {
        **_week_nav(start),
        "days": days,
        "today": timezone.localdate(),
        "planned_count": len(meals),
        "dinner_count": dinners,
        "other_count": len(meals) - dinners,
        "slots": Meal.Slot.choices,
        "default_slot": Meal.Slot.DINNER,
        "recipes": recipes,
        "suggestions": suggestions,
    }
    return render(request, "kondate/week.html", context)


def meal_edit(request, pk: int | None = None):
    meal = get_object_or_404(Meal, pk=pk) if pk else None
    if request.method == "POST":
        form = MealForm(request.POST, instance=meal)
        if form.is_valid():
            meal = form.save()
            verb = "Updated" if pk else "Planned"
            messages.success(request, f"{verb} {meal.title} for {meal.date:%A}.")
            return _to_week(week_start_for(meal.date))
    else:
        initial = {}
        if meal is None:
            initial["date"] = request.GET.get("date") or timezone.localdate().isoformat()
            initial["slot"] = request.GET.get("slot") or Meal.Slot.DINNER
            if recipe_id := request.GET.get("recipe"):
                initial["recipe"] = recipe_id
        form = MealForm(instance=meal, initial=initial)
    back_url = (
        reverse("kondate:week_of", args=[week_start_for(meal.date).isoformat()])
        if meal
        else reverse("kondate:week")
    )
    return render(request, "kondate/meal_form.html", {"form": form, "meal": meal, "back_url": back_url})


@require_POST
def meal_delete(request, pk: int):
    meal = get_object_or_404(Meal, pk=pk)
    week_of = week_start_for(meal.date)
    meal.delete()
    messages.success(request, f"Removed {meal.title} from {meal.date:%A}.")
    return _to_week(week_of)


@require_POST
def week_copy_previous(request, day: str):
    """Copy last week's plan into this week (only into an empty week)."""
    start = _week_of(day)
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
    return _to_week(start)


# --- Recipes ----------------------------------------------------------------


@require_safe
def recipe_list(request):
    q = request.GET.get("q", "").strip()
    sort = request.GET.get("sort", "name")
    recipes = Recipe.objects.for_browsing().annotate(item_count=Count("items", distinct=True))
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
    context = {"recipes": recipes, "q": q, "sort": sort, "today": timezone.localdate()}
    return render(request, "kondate/recipe_list.html", context)


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
        "back_url": recipe.get_absolute_url() if recipe else reverse("kondate:recipe_list"),
        "back_label": capfirst(recipe.name) if recipe else "Recipes",
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
    queryset = Ingredient.objects.in_store_order().annotate(recipe_count=Count("recipe_items"))
    if request.method == "POST":
        formset = IngredientFormSet(request.POST, queryset=queryset)
        if formset.is_valid():
            formset.save()
            messages.success(request, "Saved ingredients.")
            return redirect("kondate:ingredient_list")
    else:
        formset = IngredientFormSet(queryset=queryset)
    context = {
        "formset": formset,
        "stock_choices": Ingredient.Stock.choices,
        "buy": request.GET.get("buy", ""),
    }
    return render(request, "kondate/ingredient_list.html", context)


@require_POST
def ingredient_stop_weekly(request, pk: int):
    ingredient = get_object_or_404(Ingredient, pk=pk)
    ingredient.stock = Ingredient.Stock.AS_NEEDED
    ingredient.save(update_fields=["stock"])
    messages.success(request, f"{ingredient.name} is no longer a weekly regular.")
    return _to_shopping(_week_of(request.POST.get("day")))



# --- Shopping list ----------------------------------------------------------


@require_safe
def shopping(request, day: str | None = None):
    start = _week_of(day)
    shopping_list = build_shopping_list(start)
    context = {
        **_week_nav(start),
        "shopping": shopping_list,
        "shopping_text": shopping_list_text(shopping_list),
        "extra_form": ShoppingExtraForm(),
        "email": request.user.email,
    }
    return render(request, "kondate/shopping.html", context)


def _tick_response(request, start: dt.date, checked: bool):
    """JSON for the page's fetch (with the refreshed copy-paste text, so it
    needs no second request), or a redirect for a plain form post."""
    if _wants_json(request):
        text = shopping_list_text(build_shopping_list(start))
        return JsonResponse({"checked": checked, "text": text})
    return _to_shopping(start)


@require_POST
def shopping_check(request, day: str, pk: int):
    """Set (not toggle) the checked state, so two phones can't flip-flop it."""
    start = _week_of(day)
    ingredient = get_object_or_404(Ingredient, pk=pk)
    checked = request.POST.get("checked") == "1"
    if checked:
        ShoppingCheck.objects.get_or_create(week_start=start, ingredient=ingredient)
    else:
        ShoppingCheck.objects.filter(week_start=start, ingredient=ingredient).delete()
    return _tick_response(request, start, checked)


@require_POST
def shopping_reset(request, day: str):
    start = _week_of(day)
    ShoppingCheck.objects.filter(week_start=start).delete()
    ShoppingExtra.objects.filter(week_start=start).update(checked=False)
    messages.success(request, "Unchecked everything.")
    return _to_shopping(start)


@require_POST
def shopping_new_trip(request, day: str):
    """Second trip of the week: weekly regulars come back, while recipe
    ingredients already bought stay ticked and bought extras are cleared."""
    start = _week_of(day)
    with transaction.atomic():
        ShoppingCheck.objects.filter(
            week_start=start, ingredient__stock=Ingredient.Stock.WEEKLY
        ).delete()
        ShoppingExtra.objects.filter(week_start=start, checked=True).delete()
    messages.success(request, "Ready for the next trip. Your regulars are back on the list.")
    return _to_shopping(start)


@require_POST
def shopping_extra_new(request, day: str):
    start = _week_of(day)
    form = ShoppingExtraForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Item name can't be empty.")
    elif form.cleaned_data["every_week"]:
        ingredient = _ingredient_for(form.cleaned_data["name"])
        if not ingredient.is_weekly:
            ingredient.stock = Ingredient.Stock.WEEKLY
            ingredient.save(update_fields=["stock"])
        messages.success(request, f"{ingredient.name} is now on the list every week.")
    else:
        extra = form.save(commit=False)
        extra.week_start = start
        extra.save()
    return _to_shopping(start, "extras")


@require_POST
def shopping_extra_check(request, pk: int):
    extra = get_object_or_404(ShoppingExtra, pk=pk)
    extra.checked = request.POST.get("checked") == "1"
    extra.save(update_fields=["checked"])
    return _tick_response(request, extra.week_start, extra.checked)


@require_POST
def shopping_extra_delete(request, pk: int):
    extra = get_object_or_404(ShoppingExtra, pk=pk)
    extra.delete()
    return _to_shopping(extra.week_start, "extras")
