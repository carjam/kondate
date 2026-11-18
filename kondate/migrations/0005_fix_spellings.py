"""Fix misspelled recipe and ingredient names carried over from the 2021 data.

Matching is case-insensitive. If production already has an ingredient under
the corrected name (someone typed it right in a later recipe), the misspelled
one is merged into it instead of colliding with the unique-name constraint.
"""

from django.db import migrations

RECIPES = {
    "bahn mi sandwich": "banh mi sandwich",
    "basmatti rice & butter": "basmati rice & butter",
    "Emmas gourment breakfast": "Emma's gourmet breakfast",
    "nan": "naan",
    "picapeppa & cream cheese crackers": "pickapeppa & cream cheese crackers",
    "piminto cheese sandwich": "pimento cheese sandwich",
    "taragon scrambled eggs": "tarragon scrambled eggs",
}

INGREDIENTS = {
    "basmatti rice": "basmati rice",
    "camanbert cheese": "camembert cheese",
    "gargonzalla cheese": "gorgonzola cheese",
    "hot dog weiner": "hot dog wieners",
    "mayonaise": "mayonnaise",
    "monterrey cheese": "monterey jack cheese",
    "mozerella cheese": "mozzarella cheese",
    "picapeppa sauce": "pickapeppa sauce",
    "shredded mozerella cheese": "shredded mozzarella cheese",
    "sour krout": "sauerkraut",
    "taragon": "tarragon",
    "tumeric": "turmeric",
}


def _merge_ingredient(apps, old, new):
    """Point everything at ``new``, then delete ``old``."""
    RecipeIngredient = apps.get_model("kondate", "RecipeIngredient")
    ShoppingCheck = apps.get_model("kondate", "ShoppingCheck")
    for item in RecipeIngredient.objects.filter(ingredient=old):
        if RecipeIngredient.objects.filter(recipe_id=item.recipe_id, ingredient=new).exists():
            item.delete()  # the recipe already lists the correct spelling
        else:
            item.ingredient = new
            item.save(update_fields=["ingredient"])
    for check in ShoppingCheck.objects.filter(ingredient=old):
        if ShoppingCheck.objects.filter(week_start=check.week_start, ingredient=new).exists():
            check.delete()
        else:
            check.ingredient = new
            check.save(update_fields=["ingredient"])
    old.delete()


def _rename(apps, model_name, mapping, merge=None):
    Model = apps.get_model("kondate", model_name)
    for wrong, right in mapping.items():
        obj = Model.objects.filter(name__iexact=wrong).first()
        if obj is None:
            continue
        existing = Model.objects.filter(name__iexact=right).exclude(pk=obj.pk).first()
        if existing is None:
            obj.name = right
            obj.save(update_fields=["name"])
        elif merge:
            merge(apps, obj, existing)
        # A recipe whose corrected name is already taken is left as it is.


def forwards(apps, schema_editor):
    _rename(apps, "Recipe", RECIPES)
    _rename(apps, "Ingredient", INGREDIENTS, merge=_merge_ingredient)


def backwards(apps, schema_editor):
    # Restore the old names where nothing was merged; merges aren't undone.
    _rename(apps, "Recipe", {v: k for k, v in RECIPES.items()})
    _rename(apps, "Ingredient", {v: k for k, v in INGREDIENTS.items()})


class Migration(migrations.Migration):
    dependencies = [("kondate", "0004_recipe_data")]

    operations = [migrations.RunPython(forwards, backwards)]
