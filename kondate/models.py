"""Kondate domain: recipes, their ingredients, a dated meal plan, and the
per-week shopping list state derived from it.

Data is shared by every signed-in account (one household per deployment).
"""

from urllib.parse import urlsplit

from django.db import models
from django.db.models import Case, Q, Value, When
from django.db.models.functions import Lower
from django.urls import reverse


class IngredientQuerySet(models.QuerySet):
    def in_store_order(self):
        """Aisle in store-walk order (the order ``Category`` is declared in), then name."""
        categories = Ingredient.Category.values
        rank = Case(
            *(When(category=value, then=Value(i)) for i, value in enumerate(categories)),
            default=Value(len(categories)),
        )
        return self.order_by(rank, Lower("name"))


class Ingredient(models.Model):
    class Category(models.TextChoices):
        # Declared in rough store-walk order; the shopping list sorts by this.
        PRODUCE = "produce", "Produce"
        BAKERY = "bakery", "Bakery"
        MEAT = "meat", "Meat & seafood"
        DAIRY = "dairy", "Dairy & eggs"
        PANTRY = "pantry", "Pantry"
        CONDIMENTS = "condiments", "Oils, sauces & condiments"
        SPICES = "spices", "Spices & baking"
        FROZEN = "frozen", "Frozen"
        OTHER = "other", "Other"

    class Stock(models.TextChoices):
        """How the household buys it, which decides where it lands on the list."""

        AS_NEEDED = "as_needed", "When a recipe needs it"
        WEEKLY = "weekly", "Every week"
        PANTRY = "pantry", "Usually have it"

    name = models.CharField(max_length=200)
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.OTHER)
    # db_default keeps inserts from the previous release working while a deploy
    # overlaps old and new instances (see migration 0003).
    stock = models.CharField(
        max_length=10,
        choices=Stock.choices,
        default=Stock.AS_NEEDED,
        db_default=Stock.AS_NEEDED,
        help_text="Every week: always on the list. Usually have it: listed under “check the pantry”.",
    )
    usual_amount = models.CharField(
        max_length=100, blank=True, db_default="", help_text="For weekly items, e.g. “1 gallon”."
    )

    objects = IngredientQuerySet.as_manager()

    class Meta:
        ordering = [Lower("name")]
        constraints = [
            models.UniqueConstraint(Lower("name"), name="ingredient_name_ci_unique"),
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def is_weekly(self) -> bool:
        return self.stock == self.Stock.WEEKLY

    @property
    def is_pantry(self) -> bool:
        return self.stock == self.Stock.PANTRY

    @classmethod
    def category_rank(cls, category: str) -> int:
        return cls.Category.values.index(category) if category in cls.Category.values else len(cls.Category.values)


class Recipe(models.Model):
    name = models.CharField(max_length=200)
    url = models.URLField(max_length=500, blank=True)
    notes = models.TextField(blank=True)
    ingredients = models.ManyToManyField(Ingredient, through="RecipeIngredient", related_name="recipes")

    class Meta:
        ordering = [Lower("name")]
        constraints = [
            models.UniqueConstraint(Lower("name"), name="recipe_name_ci_unique"),
        ]

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self) -> str:
        return reverse("kondate:recipe_detail", args=[self.pk])

    @property
    def source(self) -> str:
        """The link's site, e.g. "tasteofhome.com"."""
        host = urlsplit(self.url).hostname or ""
        return host.removeprefix("www.")


class RecipeIngredient(models.Model):
    recipe = models.ForeignKey(Recipe, on_delete=models.CASCADE, related_name="items")
    ingredient = models.ForeignKey(Ingredient, on_delete=models.PROTECT, related_name="recipe_items")
    # Free text on purpose: "1/2 cup", "2 medium", "to taste".
    amount = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ["pk"]
        constraints = [
            models.UniqueConstraint(fields=["recipe", "ingredient"], name="recipe_ingredient_unique"),
        ]

    def __str__(self) -> str:
        return f"{self.amount} {self.ingredient}".strip()


class Meal(models.Model):
    """One planned dish (or a free-text note such as "eat out") on a day."""

    class Slot(models.IntegerChoices):
        BREAKFAST = 1, "Breakfast"
        LUNCH = 2, "Lunch"
        DINNER = 3, "Dinner"
        DESSERT = 4, "Dessert"
        SNACK = 5, "Snack"

    date = models.DateField()
    slot = models.PositiveSmallIntegerField(choices=Slot.choices, default=Slot.DINNER)
    recipe = models.ForeignKey(
        Recipe, on_delete=models.PROTECT, null=True, blank=True, related_name="meals"
    )
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["date", "slot", "pk"]
        indexes = [models.Index(fields=["date"])]
        constraints = [
            models.CheckConstraint(
                condition=Q(recipe__isnull=False) | ~Q(note=""),
                name="meal_has_recipe_or_note",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.date} {self.get_slot_display()}: {self.title}"

    @property
    def title(self) -> str:
        return self.recipe.name if self.recipe_id else self.note


class ShoppingCheck(models.Model):
    """An ingredient ticked off on a given week's shopping list."""

    week_start = models.DateField()
    ingredient = models.ForeignKey(Ingredient, on_delete=models.CASCADE, related_name="+")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["week_start", "ingredient"], name="shopping_check_unique"),
        ]

    def __str__(self) -> str:
        return f"{self.week_start}: {self.ingredient_id} ticked"


class ShoppingExtra(models.Model):
    """A one-off item added by hand to a week's list (paper towels, coffee...)."""

    week_start = models.DateField()
    name = models.CharField(max_length=200)
    checked = models.BooleanField(default=False)

    class Meta:
        ordering = ["checked", "pk"]
        indexes = [models.Index(fields=["week_start"])]

    def __str__(self) -> str:
        return self.name
