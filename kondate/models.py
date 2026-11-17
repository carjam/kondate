"""Kondate domain: recipes, their ingredients, a dated meal plan, and the
per-week shopping list state derived from it.

Data is shared by every signed-in account (one household per deployment).
"""

from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower
from django.urls import reverse


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

    name = models.CharField(max_length=200)
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.OTHER)
    is_staple = models.BooleanField(
        default=False,
        help_text="Usually on hand (salt, oil...). Listed separately on the shopping list.",
    )

    class Meta:
        ordering = [Lower("name")]
        constraints = [
            models.UniqueConstraint(Lower("name"), name="ingredient_name_ci_unique"),
        ]

    def __str__(self) -> str:
        return self.name

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
