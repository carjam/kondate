from django.forms import ModelForm, DateInput
from kondate.models import Meal

class MealForm(ModelForm):
  class Meta:
    model = Meal
    widgets = {
      'start_date': DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
    }
    fields = '__all__'

  def __init__(self, *args, **kwargs):
    super(MealForm, self).__init__(*args, **kwargs)
    self.fields['start_date'].input_formats = ('%Y-%m-%d',)

