from django import forms
from django.db.models.functions import Lower

from .models import Ingredient, Meal, Recipe, ShoppingExtra


class MealForm(forms.ModelForm):
    class Meta:
        model = Meal
        fields = ["date", "slot", "recipe", "note"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "slot": forms.RadioSelect,
            "note": forms.TextInput(attrs={"placeholder": "e.g. double batch, or “eat out”"}),
        }
        labels = {"note": "Note"}
        help_texts = {"note": 'Optional with a recipe; on its own for things like "leftovers" or "eat out".'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["recipe"].queryset = Recipe.objects.order_by(Lower("name"))
        self.fields["recipe"].required = False
        self.fields["recipe"].empty_label = "None, just a note"

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("recipe") and not cleaned.get("note", "").strip():
            raise forms.ValidationError("Pick a recipe or write a note.")
        return cleaned


class RecipeForm(forms.ModelForm):
    url = forms.URLField(label="Link", max_length=500, required=False, assume_scheme="https")

    class Meta:
        model = Recipe
        fields = ["name", "url", "notes"]
        widgets = {"notes": forms.Textarea(attrs={"rows": 4})}


class RecipeItemForm(forms.Form):
    """One ingredient row. The ingredient is typed by name (with autocomplete);
    unknown names become new ingredients on save."""

    ingredient = forms.CharField(max_length=200, required=False)
    amount = forms.CharField(max_length=100, required=False)

    def clean_ingredient(self):
        return " ".join(self.cleaned_data["ingredient"].split())


class BaseRecipeItemFormSet(forms.BaseFormSet):
    def clean(self):
        if any(self.errors):
            return
        seen = set()
        for form in self.forms:
            if self.can_delete and self._should_delete_form(form):
                continue
            name = form.cleaned_data.get("ingredient", "")
            if not name:
                continue
            if name.lower() in seen:
                raise forms.ValidationError(f'"{name}" is listed twice.')
            seen.add(name.lower())

    def rows(self) -> list[tuple[str, str]]:
        """(ingredient name, amount) for every non-empty, non-deleted row."""
        out = []
        for form in self.forms:
            if self.can_delete and self._should_delete_form(form):
                continue
            name = form.cleaned_data.get("ingredient", "")
            if name:
                out.append((name, form.cleaned_data.get("amount", "").strip()))
        return out


RecipeItemFormSet = forms.formset_factory(
    RecipeItemForm, formset=BaseRecipeItemFormSet, extra=3, can_delete=True, max_num=100, validate_max=True
)


class IngredientForm(forms.ModelForm):
    class Meta:
        model = Ingredient
        fields = ["category", "stock", "usual_amount"]
        labels = {"category": "Store section", "stock": "Buy", "usual_amount": "Usual amount"}
        widgets = {"usual_amount": forms.TextInput(attrs={"placeholder": "e.g. 1 gallon"})}


IngredientFormSet = forms.modelformset_factory(Ingredient, form=IngredientForm, extra=0, edit_only=True)


class ShoppingExtraForm(forms.ModelForm):
    every_week = forms.BooleanField(required=False, label="Every week")

    class Meta:
        model = ShoppingExtra
        fields = ["name"]
        widgets = {
            "name": forms.TextInput(
                attrs={"placeholder": "Add an item: coffee, paper towels…", "autocomplete": "off"}
            )
        }
        labels = {"name": "Item"}

    def clean_name(self):
        return " ".join(self.cleaned_data["name"].split())
