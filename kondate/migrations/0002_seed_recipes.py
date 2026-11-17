"""Load the original 2021 recipe collection (recovered from the legacy
data migrations) into a fresh database. Runs once per database."""

import json
from pathlib import Path

from django.db import migrations

SEED_FILE = Path(__file__).resolve().parent.parent / "seed" / "recipes_2021.json"


def load_seed(apps, schema_editor):
    Ingredient = apps.get_model("kondate", "Ingredient")
    Recipe = apps.get_model("kondate", "Recipe")
    RecipeIngredient = apps.get_model("kondate", "RecipeIngredient")

    data = json.loads(SEED_FILE.read_text(encoding="utf-8"))
    ingredients = {}
    for row in data["ingredients"]:
        ingredient, _ = Ingredient.objects.get_or_create(
            name__iexact=row["name"],
            defaults={"name": row["name"], "category": row["category"], "is_staple": row["is_staple"]},
        )
        ingredients[row["name"]] = ingredient

    for row in data["recipes"]:
        recipe, created = Recipe.objects.get_or_create(
            name__iexact=row["name"],
            defaults={"name": row["name"], "url": row["url"], "notes": row["notes"]},
        )
        if not created:
            continue
        RecipeIngredient.objects.bulk_create(
            RecipeIngredient(recipe=recipe, ingredient=ingredients[item["ingredient"]], amount=item["amount"])
            for item in row["ingredients"]
        )


def unload_seed(apps, schema_editor):
    Recipe = apps.get_model("kondate", "Recipe")
    Ingredient = apps.get_model("kondate", "Ingredient")
    data = json.loads(SEED_FILE.read_text(encoding="utf-8"))
    Recipe.objects.filter(name__in=[r["name"] for r in data["recipes"]], meals__isnull=True).delete()
    Ingredient.objects.filter(
        name__in=[i["name"] for i in data["ingredients"]], recipe_items__isnull=True
    ).delete()


class Migration(migrations.Migration):
    dependencies = [("kondate", "0001_initial")]

    operations = [migrations.RunPython(load_seed, unload_seed)]
