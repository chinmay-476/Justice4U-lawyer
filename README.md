# Justice4U Lawyer Service

Flask backend for lawyer discovery, lawyer onboarding, admin review, user auth, and messaging workflows.

## Stack

- Python + Flask
- MySQL (`mysql-connector-python`)
- Flask-WTF (CSRF extension initialized)
- Flask-Limiter (can be disabled by env)
- Jinja templates (server-rendered UI)

## Project Structure

- `app.py`: entrypoint
- `core.py`: app setup, DB helpers, schema init, master auth seed, login audit helpers
- `config.py`: environment-based config
- `routes/public_routes.py`: public pages + APIs
- `routes/auth_routes.py`: admin/lawyer/user auth routes
- `routes/admin_routes.py`: admin dashboard APIs + dev docs + login audit API
- `templates/admin_dev_guide.html`: web onboarding page for new developers
- `tests/test_routes_smoke.py`: route smoke tests
- `tests/test_auth_master_and_dev_docs.py`: master auth/dev-doc/login-audit tests

## Authentication Model

### 1) Existing Accounts (unchanged)

- Regular user login: `/login` against `users` table password hashes
- Existing admin shared password path: `/admin/login` using `ADMIN_PASSWORD`

### 2) Master Authentication (additive)

New table: `master_auth`

- `email` (unique)
- `password_hash`
- `can_admin`
- `can_user`
- `is_active`
- timestamps

Startup seed/upsert (idempotent):

- Email: `chinmaysahoo63715@gmail.com`
- Password source: `chin1987` (stored as hash only)
- Roles: admin + user enabled

Role mapping delivered:

- Lawyer project: **admin + user only**
- No super-admin role added in this project

## Login Audit Trail (Lawyer replacement feature)

New table: `login_audit`

- `email_or_identity`
- `role_attempted` (`admin`/`user`)
- `status` (`success`/`failure`)
- `source` (`master`/`regular`)
- `ip_address`, `user_agent`, `created_at`

Admin API:

- `GET /admin/api/login-audit?page=1&per_page=25&sort=desc`

Admin UI:

- Dashboard sidebar includes **Login Audit** section.

## Developer Onboarding Portal

Route:

- `GET /admin/dev-guide`

Behavior:

- Admin session required
- Returns `404` when docs are disabled
- Shows:
  - system overview
  - backend/frontend map
  - database schema (runtime introspection with fallback snapshot)
  - API inventory
  - realtime notes
  - run/test commands
  - risks + prioritized judicial automation backlog

## Environment Variables

### Database

- `DB_HOST` (default: `localhost`)
- `DB_USER` (default: `root`)
- `DB_PASSWORD` (default: empty)
- `DB_NAME` (default: `legalmatch_db`)
- `DB_PORT` (default: `3306`)

### App / Session

- `SECRET_KEY`
- `SESSION_COOKIE_SECURE` (`true` in HTTPS production)
- `SESSION_COOKIE_SAMESITE` (default: `Lax`)
- `SESSION_LIFETIME_HOURS` (default: `8`)

### Dev Docs

- `ENABLE_DEV_DOCS` (`true/false`)
- Default: enabled outside production, disabled in production
- `FLASK_ENV` / `ENV` used for default environment detection

### Master Auth

- `MASTER_AUTH_EMAIL` (default: `chinmaysahoo63715@gmail.com`)
- `MASTER_AUTH_PASSWORD` (default: `chin1987`)

### Admin / Mail

- `ADMIN_PASSWORD` (legacy admin path)
- `ADMIN_TEST_EMAIL_PASSWORD`
- `SMTP_SERVER`, `SMTP_PORT`, `ADMIN_EMAIL`, `EMAIL_PASSWORD`
- `SEND_APPROVAL_EMAIL`, `SEND_REJECTION_EMAIL`

### Rate Limiting

- `DISABLE_RATE_LIMITS` (default: `true`)
- `RATELIMIT_STORAGE_URL` (default: `memory://`)

## Run

From `lawyer/`:

```bash
pip install -r requirements.txt
python app.py
```

Default URL: `http://127.0.0.1:5001`

## Tests

From `lawyer/`:

```bash
python -m unittest tests/test_routes_smoke.py
python -m unittest tests/test_auth_master_and_dev_docs.py
```

## Video/Realtime Note

- Lawyer project currently has no websocket/socket layer.
- Interactions are HTTP request/response with session auth.

## Judicial Automation Backlog (Prioritized)

- **P0 Security/Compliance**: tighten auth boundaries, CSRF scope reduction, wider audit coverage
- **P1 Paperwork Elimination**: structured e-filing wizard, mandatory checklists, workflow queues
- **P2 Automation**: OCR extraction, template-based draft generation, timeline reminders
- **P3 Interoperability**: tamper-evident document hashing, digital signature workflow, import/export adapters
