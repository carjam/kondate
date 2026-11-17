"""Week arithmetic and shopping-list aggregation (no HTTP concerns here)."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from itertools import groupby

from django.conf import settings
from django.db.models import Prefetch
from django.utils import timezone

from .models import Ingredient, Meal, RecipeIngredient, ShoppingCheck


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
    def amounts(self) -> str:
        """Amounts are free text, so list them rather than pretend to sum them."""
        return " + ".join(n.amount for n in self.needs if n.amount)


@dataclass
class ShoppingSection:
    label: str
    lines: list[ShoppingLine]

    @property
    def remaining(self) -> int:
        return sum(1 for line in self.lines if not line.checked)


@dataclass
class ShoppingList:
    week_start: dt.date
    sections: list[ShoppingSection]
    staples: list[ShoppingLine]

    @property
    def remaining(self) -> int:
        return sum(s.remaining for s in self.sections)


def build_shopping_list(start: dt.date) -> ShoppingList:
    lines: dict[int, ShoppingLine] = {}
    for meal in meals_in_week(start):
        if meal.recipe is None:
            continue
        for item in meal.recipe.items.all():
            line = lines.setdefault(item.ingredient_id, ShoppingLine(item.ingredient))
            line.needs.append(Need(item.amount, meal.recipe.name, meal.date))

    checked_ids = set(
        ShoppingCheck.objects.filter(week_start=start, ingredient_id__in=lines).values_list(
            "ingredient_id", flat=True
        )
    )
    for ingredient_id, line in lines.items():
        line.checked = ingredient_id in checked_ids

    def sort_key(line: ShoppingLine):
        return (Ingredient.category_rank(line.ingredient.category), line.ingredient.name.lower())

    regular = sorted((ln for ln in lines.values() if not ln.ingredient.is_staple), key=sort_key)
    staples = sorted((ln for ln in lines.values() if ln.ingredient.is_staple), key=sort_key)
    labels = dict(Ingredient.Category.choices)
    sections = [
        ShoppingSection(labels.get(category, category), list(group))
        for category, group in groupby(regular, key=lambda ln: ln.ingredient.category)
    ]
    return ShoppingList(week_start=start, sections=sections, staples=staples)
