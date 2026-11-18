"""Replace Ingredient.is_staple with a three-way ``stock`` setting.

"Staple" used to mean "probably have it at home". The household's word for
that is "pantry", and "staples" are the things bought every trip, so the
model now says which of the three an ingredient is.

Expand/contract, because Render runs the old release while the new one boots:

* ``stock`` and ``usual_amount`` get database defaults, so the old release can
  still insert ingredients without knowing about them.
* ``is_staple`` leaves Django's model state but stays in the database with a
  database default of false, so the old release can still read and write it.
  A later migration drops the column once this release is live.
"""

from django.db import migrations, models


def staple_to_pantry(apps, schema_editor):
    Ingredient = apps.get_model("kondate", "Ingredient")
    Ingredient.objects.filter(is_staple=True).update(stock="pantry")


def pantry_to_staple(apps, schema_editor):
    Ingredient = apps.get_model("kondate", "Ingredient")
    Ingredient.objects.filter(stock="pantry").update(is_staple=True)


STOCK_CHOICES = [
    ("as_needed", "When a recipe needs it"),
    ("weekly", "Every week"),
    ("pantry", "Usually have it"),
]


class Migration(migrations.Migration):
    dependencies = [("kondate", "0002_seed_recipes")]

    operations = [
        migrations.AddField(
            model_name="ingredient",
            name="stock",
            field=models.CharField(
                choices=STOCK_CHOICES,
                db_default="as_needed",
                default="as_needed",
                help_text="Every week: always on the list. Usually have it: listed under “check the pantry”.",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="ingredient",
            name="usual_amount",
            field=models.CharField(
                blank=True, db_default="", help_text="For weekly items, e.g. “1 gallon”.", max_length=100
            ),
        ),
        migrations.RunPython(staple_to_pantry, pantry_to_staple),
        migrations.AlterField(
            model_name="ingredient",
            name="is_staple",
            field=models.BooleanField(default=False, db_default=False),
        ),
        migrations.SeparateDatabaseAndState(
            state_operations=[migrations.RemoveField(model_name="ingredient", name="is_staple")],
        ),
    ]
