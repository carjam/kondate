# kondate (献立)

A small, always-on household tool for planning the week's meals and shopping for them.

- **Week** – Seven-day plan with breakfast, lunch, dinner, dessert, and snack slots. A meal is a recipe or a free-text note ("eat out", "leftovers"). You can copy last week's plan into an empty week.
- **Shopping** – Built automatically from the week's meals. Ingredients are merged across recipes, grouped by store section in walk order, and show which meals need them. You tick items off on your phone as you shop, and two phones stay in sync. Staples (salt, oil…) sit in a collapsed "probably have" section. You can add one-off extras (coffee, paper towels).
- **Recipes** – Name, link, notes, and ingredients with free-text amounts. Ingredient names autocomplete, and new ones are created as you type them. You can search by ingredient and sort by "not had in a while".
- **Ingredients** – Bulk-edit each ingredient's store section and staple flag.

All data is shared by every account on a deployment (one household). Every page requires sign-in.

Ships with the original 2021 collection: 33 recipes, 122 ingredients, and 213 recipe–ingredient amounts, loaded by migration `0002_seed_recipes` from `kondate/seed/recipes_2021.json`.

## Stack

Django 5.2 LTS · server-rendered templates with a small inline script (no build step) · SQLite locally, Postgres in production · gunicorn + whitenoise · pytest-django.

## Run locally

```bash
uv venv .venv && uv pip install -p .venv -r requirements-dev.txt   # or python -m venv + pip
export DJANGO_DEBUG=1
.venv/bin/python manage.py migrate
.venv/bin/python manage.py createsuperuser
.venv/bin/python manage.py runserver
```

Open http://localhost:8000. Run the tests with `DJANGO_DEBUG=1 .venv/bin/python -m pytest`.

## Deploy (Render + Supabase)

The full runbook is **[docs/DEPLOY.md](docs/DEPLOY.md)**. It covers current status, Supabase setup (including locking down its auto-exposed REST API), the Render blueprint, verification, free-tier caveats, backups, a custom domain, and troubleshooting.

In short:
1. Merge to `master`.
2. Create a Supabase project, turn off its Data API, and copy the **Session pooler** connection string.
3. In Render, choose New → Blueprint for this repo, and set `DATABASE_URL` and `DJANGO_SUPERUSER_USERNAME`/`_PASSWORD`.
4. Each boot runs `migrate` (which loads the seed recipes on a fresh database), creates the first account, and starts gunicorn. `/healthz` is the health check.

Render's free service sleeps after about 15 minutes idle (cold start 30–60 seconds), and a free Supabase project pauses after about a week without use. The runbook explains what to do about each.

### Settings (env vars)

| Variable | Default | Purpose |
|---|---|---|
| `DJANGO_SECRET_KEY` | — (required unless debug) | Signing key |
| `DJANGO_DEBUG` | off | Local development only |
| `DATABASE_URL` | `sqlite:///db.sqlite3` | Database |
| `DJANGO_ALLOWED_HOSTS` | Render hostname | Comma-separated extra hosts, e.g. a custom domain |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Render URL | Comma-separated, with scheme |
| `TIME_ZONE` | `America/Los_Angeles` | Decides what "today" and "this week" mean |
| `KONDATE_WEEK_START` | `0` (Monday) | `6` = Sunday-start weeks |

## Layout

```
kondate/
  models.py      Ingredient, Recipe, RecipeIngredient, Meal, ShoppingCheck, ShoppingExtra
  planning.py    week arithmetic + shopping-list aggregation (fixed query count)
  views.py       function views; all POSTs for writes
  seed/          original recipe data
  management/commands/ensure_superuser.py
  tests/         pytest-django suite (CI runs it on Postgres)
mysite/          settings, urls, wsgi
render.yaml      Render blueprint
```
