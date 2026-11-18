"""Week arithmetic and shopping-list aggregation (no HTTP concerns here)."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from itertools import groupby

from django.conf import settings
from django.db.models import Prefetch
from django.utils import timezone

from .models import Ingredient, Meal, RecipeIngredient, ShoppingCheck, ShoppingExtra
from .quantities import combine_amounts


def week_start_for(day: dt.date) -> dt.date:
    """The first day of the planning week containing ``day``."""
    offset = (day.weekday() - settings.KONDATE_WEEK_START) % 7
    return day - dt.timedelta(days=offset)


def current_week_start() -> dt.date:
    return week_start_for(timezone.localdate())


def week_days(start: dt.date) -> list[dt.date]:
    return [start + dt.timedelta(days=i) for i in range(7)]


def meals_in_week(start: dt.date):
    """Meals for the 7 days from ``start``, with recipes and ingredients loaded
    in a fixed number of queries (1 meals+recipe join, 1 items+ingredient join)."""
    items = RecipeIngredient.objects.select_related("ingredient")
    return (
        Meal.objects.filter(date__gte=start, date__lt=start + dt.timedelta(days=7))
        .select_related("recipe")
        .prefetch_related(Prefetch("recipe__items", queryset=items))
    )


@dataclass
class Need:
    amount: str
    recipe: str
    date: dt.date


@dataclass
class ShoppingLine:
    ingredient: Ingredient
    needs: list[Need] = field(default_factory=list)
    checked: bool = False

    @property
    def weekly(self) -> bool:
        return self.ingredient.is_weekly

    @property
    def amounts(self) -> str:
        """Same-unit amounts are added up; anything else is listed as typed."""
        raw = [self.ingredient.usual_amount] if self.weekly else []
        return combine_amounts(raw + [n.amount for n in self.needs])


@dataclass
class ShoppingSection:
    label: str
    lines: list[ShoppingLine]

    @property
    def remaining(self) -> int:
        return sum(1 for line in self.lines if not line.checked)


@dataclass
class ShoppingList:
    """Everything to buy for one planning week.

    ``sections`` holds what recipes need plus the weekly regulars, in store-walk
    order. ``pantry`` holds things recipes need that the household usually has
    (check before leaving). ``extras`` are one-offs typed in for this week.
    """

    week_start: dt.date
    sections: list[ShoppingSection]
    pantry: list[ShoppingLine]
    extras: list[ShoppingExtra]
    meals: list[Meal]

    @property
    def week_end(self) -> dt.date:
        return self.week_start + dt.timedelta(days=6)

    @property
    def total(self) -> int:
        return sum(len(s.lines) for s in self.sections) + len(self.extras)

    @property
    def remaining(self) -> int:
        return sum(s.remaining for s in self.sections) + sum(1 for e in self.extras if not e.checked)

    @property
    def done(self) -> int:
        return self.total - self.remaining

    @property
    def regulars(self) -> list[Ingredient]:
        lines = [ln for s in self.sections for ln in s.lines if ln.weekly]
        return sorted((ln.ingredient for ln in lines), key=lambda i: i.name.lower())

    @property
    def is_empty(self) -> bool:
        return not (self.sections or self.pantry or self.extras)


def build_shopping_list(start: dt.date) -> ShoppingList:
    """Five queries regardless of size: meals+recipes, recipe items, weekly
    regulars, this week's checks, this week's extras."""
    meals = list(meals_in_week(start))
    lines: dict[int, ShoppingLine] = {}
    for meal in meals:
        if meal.recipe is None:
            continue
        for item in meal.recipe.items.all():
            line = lines.setdefault(item.ingredient_id, ShoppingLine(item.ingredient))
            line.needs.append(Need(item.amount, meal.recipe.name, meal.date))
    for ingredient in Ingredient.objects.filter(stock=Ingredient.Stock.WEEKLY):
        lines.setdefault(ingredient.pk, ShoppingLine(ingredient))

    checked_ids = set(
        ShoppingCheck.objects.filter(week_start=start, ingredient_id__in=lines).values_list(
            "ingredient_id", flat=True
        )
    )
    for ingredient_id, line in lines.items():
        line.checked = ingredient_id in checked_ids

    def sort_key(line: ShoppingLine):
        return (Ingredient.category_rank(line.ingredient.category), line.ingredient.name.lower())

    to_buy = sorted((ln for ln in lines.values() if not ln.ingredient.is_pantry), key=sort_key)
    pantry = sorted((ln for ln in lines.values() if ln.ingredient.is_pantry), key=sort_key)
    labels = dict(Ingredient.Category.choices)
    sections = [
        ShoppingSection(labels.get(category, category), list(group))
        for category, group in groupby(to_buy, key=lambda ln: ln.ingredient.category)
    ]
    extras = list(ShoppingExtra.objects.filter(week_start=start))
    return ShoppingList(start, sections, pantry, extras, meals)


def day_range(start: dt.date, end: dt.date) -> str:
    """ "Nov 16–22", or "Nov 30 – Dec 6" across a month boundary."""
    if start.month == end.month:
        return f"{start:%b} {start.day}–{end.day}"
    return f"{start:%b} {start.day} – {end:%b} {end.day}"


def shopping_list_text(shopping: ShoppingList) -> str:
    """A plain-text version to paste into an email or notes app.

    Only what's still left to buy is included, so copying after a first trip
    gives the list for the second one.
    """
    out = [f"Shopping list · {day_range(shopping.week_start, shopping.week_end)}"]

    def block(title: str, rows: list[str]) -> None:
        if rows:
            out.extend(["", title.upper(), *rows])

    def row(line: ShoppingLine) -> str:
        return f"☐ {line.ingredient.name}" + (f" — {line.amounts}" if line.amounts else "")

    for section in shopping.sections:
        block(section.label, [row(ln) for ln in section.lines if not ln.checked])
    block("Extras", [f"☐ {e.name}" for e in shopping.extras if not e.checked])
    block("Check the pantry first", [row(ln) for ln in shopping.pantry if not ln.checked])

    def meal_row(meal: Meal) -> str:
        slot = "" if meal.slot == Meal.Slot.DINNER else f" ({meal.get_slot_display().lower()})"
        return f"{meal.date:%a}  {meal.title}{slot}"

    block("Meals this week", [meal_row(m) for m in shopping.meals])
    if shopping.remaining == 0 and shopping.total:
        out.extend(["", "Everything's ticked off."])
    return "\n".join(out) + "\n"
