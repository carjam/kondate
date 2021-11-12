from datetime import datetime, date, timedelta
from calendar import HTMLCalendar
import calendar
from .models import Meal


class Calendar(HTMLCalendar):
    def __init__(self, year=None, month=None):
        self.year = year
        self.month = month
        super(Calendar, self).__init__()

    # formats a day as a td
    # filter meals by day
    def formatday(self, day, meals):
        d = ''
        for meal in meals:
            if meal.start_date.day == day:
                d += f'<li> {meal.get_html_url} </li>'

        if day != 0:
            return f"<td><span class='date'>{day}</span><ul> {d} </ul></td>"
        return '<td></td>'

    # formats a week as a tr
    def formatweek(self, theweek, meals):
        week = ''
        for d, weekday in theweek:
            week += self.formatday(d, meals)
        return f'<tr> {week} </tr>'

    # formats a month as a table
    # filter meals by year and month
    def formatmonth(self, withyear=True):
        meals = Meal.objects.filter(
            start_date__gte=date(
                self.year, self.month, 1), start_date__lte=date(
                self.year, self.month, calendar.monthrange(
                    self.year, self.month)[1]))

        cal = f'<table border="0" cellpadding="0" cellspacing="0" class="calendar">\n'
        cal += f'{self.formatmonthname(self.year, self.month, withyear=withyear)}\n'
        cal += f'{self.formatweekheader()}\n'
        for week in self.monthdays2calendar(self.year, self.month):
            cal += f'{self.formatweek(week, meals)}\n'
        return cal
