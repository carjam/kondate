# Deploying kondate: Render + Supabase

A step-by-step guide to running your own copy of kondate on free tiers: a Render web service and a Supabase Postgres database. Expect it to take about 30 minutes the first time. The second half covers day-to-day operation, the settings reference and troubleshooting.

> Render and Supabase change their dashboards and free-tier terms from time to time. If a menu name below doesn't match, look for the nearest equivalent, and check current plan limits before relying on them.

## How it fits together

```
phone / laptop ──HTTPS──▶ Render web service (free)          Supabase (free)
                          gunicorn + Django + whitenoise ──▶ Postgres, reached via the
                          on boot: migrate → ensure_superuser   Session pooler (IPv4, port 5432)
```

- Render builds from `render.yaml` on every push to `master`.
- Each boot runs `migrate`, which creates the tables. On a fresh database it also loads the 45 seed recipes. The boot then runs `ensure_superuser` and starts gunicorn.
- No Supabase features are used except plain Postgres: no Supabase Auth and no client libraries.

---

## 0. Code on `master`

`render.yaml` deploys the `master` branch, so whatever you want live must be merged there first.

## 1. Supabase: create the database

Go to https://supabase.com/dashboard and create a **New project**. Fill in the form like this:

| Field | Choose | Why |
|---|---|---|
| **Organization** | Your org, on the Free plan | |
| **GitHub** | Leave it unconnected | Django's migrations own the schema. Supabase's GitHub schema sync would conflict with them. |
| **Project name** | `kondate` | |
| **Database password** | **Generate a password**, then save it in your password manager right away | You need it for the connection string, and Supabase won't show it again. |
| **Region** | Click **"Need a specific region?"** and choose **West US (Oregon)** (`us-west-2`). If that's missing, choose North California. | The plain "Americas" choice lets Supabase pick, and it may pick the East Coast. Render runs in Oregon, and every query crosses this link. |
| **Enable Data API** | **Off** | See 1a. |
| **Automatically expose new tables** | **Off** | Tables stay private even if the Data API is turned on later. |
| **Enable automatic RLS** | **On** | Extra protection. It doesn't affect Django, which connects as the table owner, and Postgres doesn't apply RLS to a table's owner. |
| **Postgres Type** | **Postgres (Default)** | OrioleDB is beta, and this can't be changed after the project is created. |

Wait a minute or two for the project to finish provisioning.

### 1a. Why the Data API must stay off

Supabase can publish every table in the `public` schema through its Data API (PostgREST). Django creates all of its tables in `public`, including `auth_user` with the password hashes. kondate never uses the Data API, so it's turned off when the project is created (above).

If the API ever got turned on, turn it off again under **Project Settings → Data API**, or remove `public` from **Exposed schemas**. Automatic RLS is a second layer of protection, but the API being off is the main one.

### 1b. Get the connection string

1. Click **Connect** at the top of the project dashboard.
2. Choose **Session pooler**, not "Direct connection" and not "Transaction pooler".
   - Direct connection (`db.<ref>.supabase.co`) is IPv6-only, and Render can't reach it. You'll get "Network is unreachable" errors.
   - Transaction pooler (port 6543) doesn't work well with Django's persistent connections.
3. Copy the URI. It looks like:

   ```
   postgresql://postgres.<project-ref>:[YOUR-PASSWORD]@aws-1-us-west-2.pooler.supabase.com:5432/postgres
   ```

   The host prefix (`aws-0-`, `aws-1-`, …) varies by project. Use exactly what Supabase shows. Check two things: the username is `postgres.<project-ref>`, not plain `postgres`, and the port is `5432`.

4. Replace `[YOUR-PASSWORD]` (brackets included) with the password from step 1, and append `?sslmode=require`:

   ```
   postgresql://postgres.abcdefghijkl:PASSWORD@aws-1-us-west-2.pooler.supabase.com:5432/postgres?sslmode=require
   ```

   Build it in a text editor and paste it as plain text. Some editors and terminals turn a pasted URL into a Markdown link (`[…](…)`), and Django then fails with `UnknownSchemeError: Scheme '://' is unknown`.

   Supabase's generated passwords are letters and digits only. If you set your own, **URL-encode it** when it has special characters (`!` → `%21`, `@` → `%40`, `#` → `%23`, `/` → `%2F`, `:` → `%3A`). Encode it with:

   ```bash
   python3 -c "import urllib.parse,getpass; print(urllib.parse.quote(getpass.getpass('pw: '), safe=''))"
   ```

5. Optional: test the string from your machine before involving Render. Run this from the repo root. `read -s` keeps the URI out of your shell history and off the screen; paste it at the prompt and press Enter (nothing is shown while you paste).

   ```bash
   read -rsp 'DATABASE_URL: ' DATABASE_URL && echo && export DATABASE_URL
   DJANGO_DEBUG=1 .venv/bin/python manage.py showmigrations kondate
   unset DATABASE_URL
   ```

   Success is a list of migrations marked `[ ]`, meaning the connection works and nothing has run yet. Don't run `migrate` here; Render will do it on first boot. (It's harmless if you do, since migrate is idempotent.)

   Never paste the URI (with its password) into chat, tickets or commands typed on the command line. If it leaks, reset the password (below) before anything depends on it.

### 1c. Resetting the database password

The password is under **Database → Settings** (`https://supabase.com/dashboard/project/<project-ref>/database/settings`) → *Database password* → **Reset database password**. It is no longer under *Project Settings*. After a reset, update `DATABASE_URL` in Render (*Service → Environment*), which redeploys the service.

## 2. Render: create the web service

1. Go to https://dashboard.render.com and sign in with GitHub.
2. Choose **New → Blueprint**, select your fork of `kondate`, and use branch `master`. If you enter a Blueprint name, use `kondate`. Render reads `render.yaml` and proposes one web service, **kondate** (free plan, Oregon).
   - **Repo not listed?** Render's GitHub app only sees the repos you've granted it. Go to https://github.com/settings/installations → **Render** → **Configure** → *Repository access*, add `kondate` (*Only select repositories* keeps access narrow), click **Save**, then refresh the Render page.
3. Render prompts for the variables marked `sync: false`:

   | Variable | Value |
   |---|---|
   | `DATABASE_URL` | The full Session pooler URI from step 1b, including `?sslmode=require` |
   | `DJANGO_SUPERUSER_USERNAME` | Your login name. Avoid one that's easy to guess: sign-in lockouts are per username (see *Security*). |
   | `DJANGO_SUPERUSER_PASSWORD` | A strong password, which becomes your login password |

   These are set for you:
   - `DJANGO_SECRET_KEY` is generated by Render.
   - `PYTHON_VERSION`, `TIME_ZONE` (America/Los_Angeles) and `KONDATE_WEEK_START` (0 = Monday) come from `render.yaml`.
4. Click **Apply**. The first deploy:
   - **Build:** `pip install` + `collectstatic` (about 1–2 minutes).
   - **Start:** `migrate` creates the tables and loads the seed recipes, `ensure_superuser` prints `created '<you>'`, then gunicorn starts.
   - The health check on `/healthz` turns green, and the service shows **Live**.
5. Note the URL, `https://kondate-xxxx.onrender.com`; Render adds a random suffix to the service name. The app trusts this hostname automatically through `RENDER_EXTERNAL_HOSTNAME`, so no host settings are needed.

## 3. Verify

1. Open `https://<your-app>.onrender.com/healthz`. It should return `ok`.
2. Open the root URL. It should redirect to the sign-in page; log in with the superuser credentials.
3. Check that **Recipes** lists 45 recipes and **Ingredients** shows store sections.
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
# From the repo root
read -rsp 'DATABASE_URL: ' DATABASE_URL && echo && export DATABASE_URL
# Portable JSON (works with any database Django supports)
DJANGO_DEBUG=1 .venv/bin/python manage.py dumpdata kondate auth.user --indent 1 > backup-$(date +%F).json
# Or plain SQL, if you have the Postgres client tools installed
pg_dump "$DATABASE_URL" > backup-$(date +%F).sql
unset DATABASE_URL
```

To restore the JSON into a fresh database: `migrate`, then `loaddata backup-YYYY-MM-DD.json`. Delete the seed rows first if they collide.

Keep backups out of git. They contain password hashes.

## 6. Optional: custom domain

1. In Render, go to *Service → Settings → Custom Domains → Add*, e.g. `kondate.example.com`, and create the DNS record it shows you.
2. Add these environment variables to the service:
   - `DJANGO_ALLOWED_HOSTS=kondate.example.com`
   - `DJANGO_CSRF_TRUSTED_ORIGINS=https://kondate.example.com`
3. Redeploy. The `onrender.com` URL keeps working.

## 7. Operating it

### How a deploy happens

- **Every push to `master` deploys automatically.** Render builds from `render.yaml`. Merging a PR is shipping it, so keep `master` green (CI runs the tests on Postgres).
- **Build:** `pip install -r requirements.txt` + `collectstatic`.
- **Boot:** `migrate --noinput` → `ensure_superuser` → gunicorn. The free plan has no pre-deploy hook and no shell, so migrations run at boot.
- **Health check:** `/healthz` returns `ok` without touching the database.

### When you change code

- **Migrations run against live data on the next deploy.** If one fails, the boot fails and Render keeps the previous version running. Test new migrations on a copy of real data first (see *Backups* in section 5). Keep them backward compatible, because the old code is still serving requests while the new instance starts.
- **No shell on the free plan.** One-off fixes go in a data migration or a management command run from your machine (below), not a console session.
- **Changing dependencies:** edit `requirements.txt`, which is what Render installs. Python is pinned by `PYTHON_VERSION` in `render.yaml`.
- **Static files:** whitenoise serves them, and they're collected at build time. Reference them with `{% static %}`.
- **Don't add Supabase client libraries, Supabase Auth or Supabase's GitHub schema sync.** Supabase is used only as plain Postgres. Django owns the schema through its migrations.

### Running commands against production from your machine

Read the URI without echoing it, so it stays out of your shell history:

```bash
read -rsp 'DATABASE_URL: ' DATABASE_URL && echo && export DATABASE_URL
DJANGO_DEBUG=1 .venv/bin/python manage.py showmigrations   # or dumpdata, etc.
unset DATABASE_URL                                         # don't leave the shell pointed at prod
```

Never run the test suite with a production `DATABASE_URL` exported.

## Reference

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

### All settings (env vars)

| Variable | Default | Purpose |
|---|---|---|
| `DJANGO_SECRET_KEY` | — (required unless debug) | Signing key |
| `DJANGO_DEBUG` | off | Local development only |
| `DATABASE_URL` | `sqlite:///db.sqlite3` | Database |
| `DJANGO_ALLOWED_HOSTS` | Render hostname | Comma-separated extra hosts, e.g. a custom domain |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Render URL | Comma-separated, with scheme |
| `TIME_ZONE` | `America/Los_Angeles` | Decides what "today" and "this week" mean |
| `KONDATE_WEEK_START` | `0` (Monday) | `6` = Sunday-start weeks |
| `DJANGO_SECURE_SSL_REDIRECT` | on (production) | Redirect HTTP to HTTPS; `/healthz` is exempt |
| `DJANGO_HSTS_SECONDS` | `2592000` (30 days) | HSTS max-age in production |
| `LOG_LEVEL` | `INFO` | Root log level (stdout) |
| `CSP_REPORT_ONLY` | off | Report CSP violations in the browser console instead of blocking them |

### Security

- **Every page requires sign-in** (`LoginRequiredMiddleware`); only `/healthz` is public.
- **Sign-in rate limiting** (django-axes): 10 wrong passwords for a username pause sign-in for that username for an hour, on both the app's sign-in and the admin's. A successful sign-in resets the count. To unlock early, delete the username's entries under *Admin → Axes → Access attempts*. Lockouts are by username only, because behind Render's proxy the client IP can't be trusted (see `mysite/settings.py`). The trade-off is that anyone who knows a username can lock that account for an hour, so pick usernames that don't appear anywhere public.
- **Content-Security-Policy** on every response (`mysite/middleware.py`): scripts, styles and requests from this origin only, no inline script or style. A test fails if a template adds an inline one.

## Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| Deploy fails: `ImproperlyConfigured: DJANGO_SECRET_KEY must be set` | The variable was deleted. Add `DJANGO_SECRET_KEY` back (choose *Generate*). |
| Boot log: `Network is unreachable` / `could not translate host name` | You used the **Direct connection** string. Switch to the **Session pooler** URI (step 1b). |
| Boot log: `password authentication failed` | Wrong password, or special characters not URL-encoded. Re-encode it, or reset the DB password in Supabase (*Database → Settings*, see 1c) and update `DATABASE_URL` in Render. |
| `UnknownSchemeError: Scheme '://' is unknown` | The value isn't a plain URI. It was probably pasted as a Markdown link (`[…](…)`). Paste only the `postgresql://…` string. |
| Render's Blueprint list doesn't show the repo | Grant Render's GitHub app access to it (step 2). |
| Boot log: `Tenant or user not found` | The username in the URI must be `postgres.<project-ref>` for the pooler, not plain `postgres`. |
| Connection errors after days of working fine | The Supabase project was paused. Restore it (section 5). |
| `Bad Request (400)` in the browser | The host isn't allowed. Set `DJANGO_ALLOWED_HOSTS` for any custom domain. |
| `CSRF verification failed` on login with a custom domain | Set `DJANGO_CSRF_TRUSTED_ORIGINS=https://your.domain`. |
| Page unstyled | Check that the build log shows `collectstatic` running; the build command is in `render.yaml`. |
| Can't log in and no user exists | `DJANGO_SUPERUSER_USERNAME`/`_PASSWORD` weren't set on first boot. Set them and redeploy (*Manual Deploy → Deploy latest commit*). |

Logs are under *Render → Service → Logs*. The app logs to stdout at INFO; set `LOG_LEVEL=DEBUG` temporarily for more detail.
