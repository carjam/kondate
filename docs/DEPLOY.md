# Deploying kondate: Render + Supabase

A step-by-step runbook for getting kondate online. Expect it to take about 30 minutes the first time.

> Render and Supabase change their dashboards and free-tier terms from time to time. If a menu name below doesn't match, look for the nearest equivalent, and check current plan limits before relying on them.

## Where things stand (as of 2026-11-17)

| Item | Status |
|---|---|
| Code | Done on branch `modernize`, in PR #1 (https://github.com/carjam/kondate/pull/1) |
| CI | Passing: migration check, `check --deploy`, 49 tests on Postgres 17 |
| Merged to `master` | **No.** This is step 0 below |
| Supabase project | Not created |
| Render service | Not created |

## How it fits together

```
phone / laptop ──HTTPS──▶ Render web service (free)          Supabase (free)
                          gunicorn + Django + whitenoise ──▶ Postgres, reached via the
                          on boot: migrate → ensure_superuser   Session pooler (IPv4, port 5432)
```

- Render builds from `render.yaml` on every push to `master`.
- Each boot runs `migrate`, which creates the tables. On a fresh database it also loads the 33 seed recipes. The boot then runs `ensure_superuser` and starts gunicorn.
- No Supabase features are used except plain Postgres: no Supabase Auth and no client libraries.

---

## 0. Merge the PR

`render.yaml` deploys the `master` branch, so merge PR #1 first.

```bash
gh pr merge 1 --squash --delete-branch   # or merge in the GitHub UI
git checkout master && git pull
```

## 1. Supabase: create the database

1. Go to https://supabase.com/dashboard and create a **New project**.
   - **Name:** `kondate`
   - **Database password:** click *Generate*, then **save it in your password manager now**. You need it for the connection string, and Supabase won't show it again. (You can reset it later.)
   - **Region:** pick the one closest to the Render region. `render.yaml` pins Render to **Oregon**, so choose **West US (Oregon)** if it's offered, otherwise **West US (North California)**. Being close keeps every page load fast, because each query crosses this link.
   - **Plan:** Free.
2. Wait for the project to finish provisioning (a minute or two).

### 1a. Lock down the auto-generated REST API (important)

Supabase automatically publishes the tables in the `public` schema through its Data API (PostgREST). Django creates all of its tables in `public`, including `auth_user` with your password hashes. Supabase only guards those tables if Row Level Security is on, and Django doesn't turn it on. kondate never uses the Data API, so switch it off:

- **Project Settings → Data API** (sometimes under *API*): **disable the Data API**. If there's no on/off switch, remove `public` from **Exposed schemas** instead.

Afterwards, **Advisors → Security Advisor** may still warn "RLS disabled in public". That warning is harmless once the Data API no longer exposes `public`, because Django is the only client and it connects as the database owner.

### 1b. Get the connection string

1. Click **Connect** at the top of the project dashboard.
2. Choose **Session pooler**, not "Direct connection" and not "Transaction pooler".
   - Direct connection (`db.<ref>.supabase.co`) is IPv6-only, and Render can't reach it. You'll get "Network is unreachable" errors.
   - Transaction pooler (port 6543) doesn't work well with Django's persistent connections.
3. Copy the URI. It looks like:

   ```
   postgresql://postgres.<project-ref>:[YOUR-PASSWORD]@aws-0-<region>.pooler.supabase.com:5432/postgres
   ```

4. Replace `[YOUR-PASSWORD]` with the password from step 1, and append `?sslmode=require`:

   ```
   postgresql://postgres.abcdefghijkl:s3cret%21pass@aws-0-us-west-2.pooler.supabase.com:5432/postgres?sslmode=require
   ```

   **URL-encode the password** if it has special characters (`!` → `%21`, `@` → `%40`, `#` → `%23`, `/` → `%2F`, `:` → `%3A`). Encode it with:

   ```bash
   python3 -c "import urllib.parse,getpass; print(urllib.parse.quote(getpass.getpass('pw: '), safe=''))"
   ```

5. Optional: test the string from your machine before involving Render.

   ```bash
   cd ~/Workspace/kondate
   DATABASE_URL='postgresql://…?sslmode=require' DJANGO_DEBUG=1 .venv/bin/python manage.py showmigrations kondate
   ```

   Success is a list of migrations marked `[ ]`, meaning the connection works and nothing has run yet. Don't run `migrate` here; Render will do it on first boot. (It's harmless if you do, since migrate is idempotent.)

## 2. Render: create the web service

1. Go to https://dashboard.render.com and sign in with GitHub. If Render can't see the private `carjam/kondate` repo, grant access under **Account Settings → GitHub → Configure**.
2. Choose **New → Blueprint**, select `carjam/kondate`, and use branch `master`. Render reads `render.yaml` and proposes one web service, **kondate** (free plan, Oregon).
3. Render prompts for the variables marked `sync: false`:

   | Variable | Value |
   |---|---|
   | `DATABASE_URL` | The full Session pooler URI from step 1b, including `?sslmode=require` |
   | `DJANGO_SUPERUSER_USERNAME` | Your login name, e.g. `james` |
   | `DJANGO_SUPERUSER_PASSWORD` | A strong password, which becomes your login password |

   These are set for you:
   - `DJANGO_SECRET_KEY` is generated by Render.
   - `PYTHON_VERSION`, `TIME_ZONE` (America/Los_Angeles) and `KONDATE_WEEK_START` (0 = Monday) come from `render.yaml`.
4. Click **Apply**. The first deploy:
   - **Build:** `pip install` + `collectstatic` (about 1–2 minutes).
   - **Start:** `migrate` creates the tables and loads the seed recipes, `ensure_superuser` prints `created '<you>'`, then gunicorn starts.
   - The health check on `/healthz` turns green, and the service shows **Live**.
5. Note the URL: `https://kondate-xxxx.onrender.com`. Render adds a suffix if the name is taken. The app trusts this hostname automatically through `RENDER_EXTERNAL_HOSTNAME`, so no host settings are needed.

## 3. Verify

1. Open `https://<your-app>.onrender.com/healthz`. It should return `ok`.
2. Open the root URL. It should redirect to the sign-in page; log in with the superuser credentials.
3. Check that **Recipes** lists 33 recipes and **Ingredients** shows store sections.
4. Plan a couple of meals, open **Shopping**, and tick an item.
5. In Supabase, **Table Editor** should now show the `kondate_*` tables.

## 4. After the first deploy

- **Remove `DJANGO_SUPERUSER_PASSWORD`** from the Render environment (*Service → Environment*). The account already exists, the command never changes an existing password, and leaving a plaintext password in the dashboard doesn't help.
- **Change your password** at `/admin/` → Users → *your user* → "Change password". Editing the env var does nothing once the account exists.
- **Add a household member:** go to `/admin/` → Users → *Add user*. Staff and superuser flags aren't needed for normal use; any signed-in user can use the app.
- **Put it on your phone's home screen:** open the site in your phone's browser, then use *Share → Add to Home Screen* (iOS) or *⋮ → Add to Home screen* (Android). Sessions last 90 days.

## 5. Living with the free tiers

**Render free web service: sleeps after about 15 minutes idle.** The first request after a sleep takes roughly 30–60 seconds; after that it's fast. Options:
- Accept it, which is fine for a once-a-day check.
- Use a free uptime monitor (e.g. UptimeRobot) that requests `https://<app>.onrender.com/healthz` every 10 minutes. One always-on service fits within the free instance hours Render gives each month.
- Upgrade the service to **Starter** (about $7/month) for always-on, with no other changes.

**Supabase free project: pauses after about a week of inactivity.** If that happens, the app shows a server error, Render logs show connection failures, and Supabase emails you. To fix it, open the dashboard and click **Restore project** (it takes a few minutes); your data is kept. Using the app every week normally prevents the pause. Note that the `/healthz` endpoint doesn't touch the database, so an uptime monitor won't keep Supabase awake. If pausing becomes a nuisance, possible fixes are a DB-touching health URL for the monitor, moving to Neon (which wakes automatically), or a paid Supabase plan.

**Backups: the free tier gives you no backups of your own.** Take one occasionally, especially before big edits:

```bash
cd ~/Workspace/kondate
# Portable JSON (works with any database Django supports)
DATABASE_URL='postgresql://…?sslmode=require' DJANGO_DEBUG=1 \
  .venv/bin/python manage.py dumpdata kondate auth.user --indent 1 > backup-$(date +%F).json
# Or plain SQL, if you have the Postgres client tools installed
pg_dump 'postgresql://…?sslmode=require' > backup-$(date +%F).sql
```

To restore the JSON into a fresh database: `migrate`, then `loaddata backup-YYYY-MM-DD.json`. Delete the seed rows first if they collide.

Keep backups out of git. They contain password hashes.

## 6. Optional: custom domain

1. In Render, go to *Service → Settings → Custom Domains → Add*, e.g. `kondate.example.com`, and create the DNS record it shows you.
2. Add these environment variables to the service:
   - `DJANGO_ALLOWED_HOSTS=kondate.example.com`
   - `DJANGO_CSRF_TRUSTED_ORIGINS=https://kondate.example.com`
3. Redeploy. The `onrender.com` URL keeps working.

## Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| Deploy fails: `ImproperlyConfigured: DJANGO_SECRET_KEY must be set` | The variable was deleted. Add `DJANGO_SECRET_KEY` back (choose *Generate*). |
| Boot log: `Network is unreachable` / `could not translate host name` | You used the **Direct connection** string. Switch to the **Session pooler** URI (step 1b). |
| Boot log: `password authentication failed` | Wrong password, or special characters not URL-encoded. Re-encode it, or reset the DB password in Supabase (*Project Settings → Database*). |
| Boot log: `Tenant or user not found` | The username in the URI must be `postgres.<project-ref>` for the pooler, not plain `postgres`. |
| Connection errors after days of working fine | The Supabase project was paused. Restore it (section 5). |
| `Bad Request (400)` in the browser | The host isn't allowed. Set `DJANGO_ALLOWED_HOSTS` for any custom domain. |
| `CSRF verification failed` on login with a custom domain | Set `DJANGO_CSRF_TRUSTED_ORIGINS=https://your.domain`. |
| Page unstyled | Check that the build log shows `collectstatic` running; the build command is in `render.yaml`. |
| Can't log in and no user exists | `DJANGO_SUPERUSER_USERNAME`/`_PASSWORD` weren't set on first boot. Set them and redeploy (*Manual Deploy → Deploy latest commit*). |

Logs are under *Render → Service → Logs*. The app logs to stdout at INFO; set `LOG_LEVEL=DEBUG` temporarily for more detail.

## Housekeeping (one-time)

- **Old MySQL password:** the original `mysite/settings.py` committed a MySQL password, and it's still in git history. If that password is used anywhere else, change it there.
- **Old local `db.sqlite3`:** no longer tracked by git. It still works for local development, since it migrates cleanly to the new schema.
