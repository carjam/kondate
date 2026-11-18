"""Recipe data, November 2026 (kondate/seed/recipes_2026_11.json).

* Fills in the five 2021 recipes that had no ingredients.
* Adds the 12 recipes from the official Campfire Cooking in Another World
  Cookpad account, with ingredient names translated to match existing ones
  so they merge on the shopping list.

Safe to run against live data: a recipe is only filled if it still has no
ingredients, a new recipe is skipped if the name is already taken, and
existing ingredients keep their aisle and buy settings.
"""

import json
from pathlib import Path

from django.db import migrations

DATA = Path(__file__).resolve().parent.parent / "seed" / "recipes_2026_11.json"


def _load():
    return json.loads(DATA.read_text(encoding="utf-8"))


def forwards(apps, schema_editor):
    Ingredient = apps.get_model("kondate", "Ingredient")
    Recipe = apps.get_model("kondate", "Recipe")
    RecipeIngredient = apps.get_model("kondate", "RecipeIngredient")
    data = _load()

    def ingredient(name):
        category, stock = data["ingredients"].get(name, ("other", "as_needed"))
        obj, _ = Ingredient.objects.get_or_create(
            name__iexact=name, defaults={"name": name, "category": category, "stock": stock}
        )
        return obj

    def add_items(recipe, rows):
        RecipeIngredient.objects.bulk_create(
            RecipeIngredient(recipe=recipe, ingredient=ingredient(name), amount=amount)
            for name, amount in rows
        )

    for entry in data["fill"]:
        recipe = Recipe.objects.filter(name__iexact=entry["name"]).first()
        if recipe is None or recipe.items.exists():
            continue
        add_items(recipe, entry["ingredients"])
        changed = []
        for field in ("url", "notes"):
            if entry.get(field) and not getattr(recipe, field):
                setattr(recipe, field, entry[field])
                changed.append(field)
        if changed:
            recipe.save(update_fields=changed)

    for entry in data["add"]:
        if Recipe.objects.filter(name__iexact=entry["name"]).exists():
            continue
        recipe = Recipe.objects.create(name=entry["name"], url=entry["url"], notes=entry["notes"])
        add_items(recipe, entry["ingredients"])


def backwards(apps, schema_editor):
    """Remove the added recipes (unless they've been planned) and empty the
    filled ones again. Ingredients are kept: other recipes may use them."""
    Recipe = apps.get_model("kondate", "Recipe")
    RecipeIngredient = apps.get_model("kondate", "RecipeIngredient")
    data = _load()
    for entry in data["add"]:
        Recipe.objects.filter(name__iexact=entry["name"], meals__isnull=True).delete()
    for entry in data["fill"]:
        RecipeIngredient.objects.filter(recipe__name__iexact=entry["name"]).delete()


class Migration(migrations.Migration):
    dependencies = [("kondate", "0003_ingredient_stock")]

    operations = [migrations.RunPython(forwards, backwards)]
