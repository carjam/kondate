# kondate (献立)

A small, always-on household tool for planning the week's meals and shopping for them.

- **Plan**: A seven-day plan, dinner-first. Tap **+** on a day to open a quick-plan sheet: search recipes by name or ingredient, pick from "haven't had in a while" suggestions, or add a note ("leftovers", "eat out"). Breakfast, lunch, dessert and snack slots are there when you need them. You can copy last week's plan into an empty week.
- **Shop**: Built automatically from the week's meals plus your **weekly regulars** (milk, eggs, bread). Ingredients are merged across recipes, amounts with the same unit are added up ("1/2 cup + 1 1/2 cups" becomes "2 cups"), and everything is grouped by aisle in walk order. Tick items off on your phone. **Copy list**, **Email** or **Share** gives a plain-text version of what's left, ready to paste. **Start another trip** puts the regulars back on the list for a second shop that week. Things you usually have (salt, oil…) sit in a collapsed "check the pantry first" section.
- **Recipes**: Name, link, notes, and ingredients with free-text amounts. Ingredient names autocomplete, and new ones are created as you type them. Filter as you type, and sort by "not had in a while".
- **Ingredients**: Set each ingredient's aisle, how you buy it (*when a recipe needs it*, *every week*, *usually have it*) and a usual amount for weekly items.

All data is shared by every account on a deployment (one household). Every page requires sign-in.

Ships with 45 recipes. The original 2021 collection (33 recipes) is loaded by migration `0002_seed_recipes` from `kondate/seed/recipes_2021.json`. Migration `0004_recipe_data` (`kondate/seed/recipes_2026_11.json`) fills in the five 2021 recipes that had no ingredients and adds 12 recipes from the official [Campfire Cooking in Another World Cookpad account](https://cookpad.com/jp/users/114280341), with ingredient names translated to match existing ones so they merge on the shopping list.

## Stack

Django 5.2 LTS · server-rendered templates, one hand-written stylesheet and one progressive-enhancement script (no build step; every action works without JavaScript) · SQLite locally, Postgres in production · gunicorn + whitenoise · pytest-django.

## Run locally

```bash
uv venv .venv && uv pip install -p .venv -r requirements-dev.txt   # or python -m venv + pip
export DJANGO_DEBUG=1
.venv/bin/python manage.py migrate
.venv/bin/python manage.py createsuperuser
.venv/bin/python manage.py runserver
```

Open http://localhost:8000. Run the tests with `DJANGO_DEBUG=1 .venv/bin/python -m pytest`.

## Production (Render + Supabase)

Live at **https://kondate-xxxx.onrender.com**. The step-by-step setup runbook and troubleshooting table are in **[docs/DEPLOY.md](docs/DEPLOY.md)**.

```
browser ──HTTPS──▶ Render web service "kondate"  ──▶ Supabase project "kondate"
                   (free, Oregon)                     (free, West US / Oregon, Postgres)
                   gunicorn + Django + whitenoise     reached via the Session pooler
```

### How a deploy happens

- **Every push to `master` deploys automatically.** Render builds from `render.yaml`. Merging a PR is shipping it, so keep `master` green (CI runs the tests on Postgres).
- **Build:** `pip install -r requirements.txt` + `collectstatic`.
- **Boot:** `migrate --noinput` → `ensure_superuser` → gunicorn. The free plan has no pre-deploy hook and no shell, so migrations run at boot.
- **Health check:** `/healthz` returns `ok` without touching the database.

### What this means when you change code

- **Migrations run against live data on the next deploy.** If one fails, the boot fails and Render keeps the previous version running. Test new migrations on a copy of real data first (see *Backups*). Keep them backward compatible, because the old code is still serving requests while the new instance starts.
- **No shell on the free plan.** One-off fixes go in a data migration or a management command run from your machine (below), not a console session.
- **Changing dependencies:** edit `requirements.txt`, which is what Render installs. Python is pinned by `PYTHON_VERSION` in `render.yaml`.
- **Static files:** whitenoise serves them, and they're collected at build time. Reference them with `{% static %}`.
- **Don't add Supabase client libraries, Supabase Auth or Supabase's GitHub schema sync.** Supabase is used only as plain Postgres. Django owns the schema through its migrations.

### Supabase settings worth knowing

- **Data API (PostgREST) is off, and new tables are not auto-exposed.** Django keeps every table, including `auth_user`, in the `public` schema. Leave the API off.
- **Automatic RLS is on.** New tables get Row Level Security turned on. Django isn't affected, because it connects as the table owner and Postgres doesn't apply RLS to a table's owner. Don't add `FORCE ROW LEVEL SECURITY`.
- **Connect through the Session pooler** (`postgres.<project-ref>@aws-1-us-west-2.pooler.supabase.com:5432`, `?sslmode=require`):
  - The direct host (`db.<ref>.supabase.co`) is IPv6-only, and Render can't reach it.
  - The transaction pooler (port 6543) doesn't work well with Django's persistent connections (`conn_max_age=600`).
- **The database password** is in Settings → Database. Reset it there, then update `DATABASE_URL` in Render.

### Render environment

| Variable | Source |
|---|---|
| `DATABASE_URL` | Set by hand in the dashboard: the Supabase Session pooler URI |
| `DJANGO_SECRET_KEY` | Generated by Render. Changing it logs everyone out. |
| `DJANGO_SUPERUSER_USERNAME` | Set by hand. Used only to create the first account. |
| `DJANGO_SUPERUSER_PASSWORD` | Set by hand for the first boot only, then delete it. `ensure_superuser` never changes an existing password, so manage users in `/admin/`. |
| `PYTHON_VERSION`, `TIME_ZONE`, `KONDATE_WEEK_START` | `render.yaml` |
| `RENDER_EXTERNAL_HOSTNAME` | Set by Render. Added to `ALLOWED_HOSTS` and CSRF trusted origins automatically. |

Secrets never go in the repo. `render.yaml` marks them `sync: false`, and their values live only in the Render dashboard.

### Running commands against production from your machine

Read the URI without echoing it, so it stays out of your shell history:

```bash
read -rsp 'DATABASE_URL: ' DATABASE_URL && echo && export DATABASE_URL
DJANGO_DEBUG=1 .venv/bin/python manage.py showmigrations   # or dumpdata, etc.
unset DATABASE_URL                                         # don't leave the shell pointed at prod
```

Never run the test suite with a production `DATABASE_URL` exported.

### Free-tier behavior

- **Render sleeps after about 15 minutes idle.** The first request afterwards takes 30–60 seconds.
- **Supabase pauses after about a week without use.** Symptoms: server errors in the app, and connection failures in the Render logs. Fix it with **Restore project** in the Supabase dashboard; the data is kept. An uptime monitor on `/healthz` won't prevent the pause, because that endpoint doesn't query the database.
- **No managed backups.** Take them yourself:
  ```bash
  DJANGO_DEBUG=1 .venv/bin/python manage.py dumpdata kondate auth.user --indent 1 > backup-$(date +%F).json
  ```
  Keep backups out of git, since they contain password hashes.

### Logs

*Render → kondate → Logs.* The app logs to stdout at INFO. Set `LOG_LEVEL=DEBUG` temporarily for more detail.

### Security

- **Every page requires sign-in** (`LoginRequiredMiddleware`); only `/healthz` is public.
- **Sign-in rate limiting** (django-axes): 10 wrong passwords for a username pause sign-in for that username for an hour, on both the app's sign-in and the admin's. A successful sign-in resets the count. To unlock early, delete the username's entries under *Admin → Axes → Access attempts*. Lockouts are by username only, because behind Render's proxy the client IP can't be trusted (see `mysite/settings.py`).
- **Content-Security-Policy** on every response (`mysite/middleware.py`): scripts, styles and requests from this origin only, no inline script or style. A test fails if a template adds an inline one.

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
| `LOG_LEVEL` | `INFO` | Root log level (stdout) |
| `CSP_REPORT_ONLY` | off | Report CSP violations in the browser console instead of blocking them |

## Layout

```
kondate/
  models.py      Ingredient, Recipe, RecipeIngredient, Meal, ShoppingCheck, ShoppingExtra
  planning.py    week arithmetic + shopping-list aggregation (fixed query count) + plain-text export
  quantities.py  adding up free-text amounts ("1/2 cup" + "1 1/2 cups" = "2 cups")
  views.py       function views; all POSTs for writes
  seed/          recipe data loaded by data migrations
  static/kondate/  styles.css and app.js (progressive enhancement, no build step)
  management/commands/ensure_superuser.py
  tests/         pytest-django suite (CI runs it on Postgres)
mysite/          settings, urls, wsgi, CSP middleware
render.yaml      Render blueprint
```

## Pending schema cleanup

Migration `0003_ingredient_stock` replaced `Ingredient.is_staple` with `Ingredient.stock` using expand/contract. Django no longer knows about the `is_staple` column, but the column stays in the database (with a database default) so the previous release keeps working while a deploy overlaps old and new instances. Once 0003 is live, a follow-up migration can drop it with `SeparateDatabaseAndState(database_operations=[RunSQL("ALTER TABLE kondate_ingredient DROP COLUMN is_staple")])`.
