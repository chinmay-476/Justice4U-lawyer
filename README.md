# Justice4U Lawyer Service

Flask backend for lawyer discovery, lawyer onboarding, admin review, user auth, and messaging workflows.

## Stack

- Python + Flask
- MySQL (`mysql-connector-python`)
- Flask-WTF (CSRF extension is initialized)
- Flask-Limiter (can be disabled by env)

## Project Structure

- `app.py`: entrypoint
- `core.py`: app factory globals, DB helpers, validation, mail, security headers, session settings
- `config.py`: env-based config
- `routes/public_routes.py`: public pages + public APIs + health endpoint
- `routes/auth_routes.py`: admin/lawyer/user authentication routes
- `routes/admin_routes.py`: admin pages + admin APIs
- `tests/test_routes_smoke.py`: smoke tests

## Security Baseline

- Server-side session is used for auth state (no trust in raw auth cookies).
- Security headers are applied globally:
  - `X-Content-Type-Options: nosniff`
  - `X-Frame-Options: DENY`
  - `Referrer-Policy: strict-origin-when-cross-origin`
  - `Content-Security-Policy: default-src 'self' 'unsafe-inline' data: https:;`
- Sensitive lawyer mutation APIs are admin-protected:
  - `PUT /api/lawyers/<id>`
  - `DELETE /api/lawyers/<id>`
  - `PUT /api/lawyers/<id>/status`
- Auth endpoints include rate limits in `routes/auth_routes.py`.
- Password policy for user registration:
  - minimum 8 chars, at least one uppercase, one lowercase, one number

## Environment Variables

### Database

- `DB_HOST` (default: `localhost`)
- `DB_USER` (default: `root`)
- `DB_PASSWORD` (default: empty)
- `DB_NAME` (default: `legalmatch_db`)
- `DB_PORT` (default: `3306`)

### App / Session

- `SECRET_KEY` (set this in production)
- `SESSION_COOKIE_SECURE` (`true` in production HTTPS)
- `SESSION_COOKIE_SAMESITE` (default: `Lax`)
- `SESSION_LIFETIME_HOURS` (default: `8`)

### Auth / Admin

- `ADMIN_PASSWORD` (admin login password, fallback `admin123`)
- `ADMIN_TEST_EMAIL_PASSWORD` (test-email endpoint guard, fallback `123`)

### Mail

- `SMTP_SERVER` (default: `smtp.gmail.com`)
- `SMTP_PORT` (default: `587`)
- `ADMIN_EMAIL`
- `EMAIL_PASSWORD`
- `SEND_APPROVAL_EMAIL` (`true`/`false`)
- `SEND_REJECTION_EMAIL` (`true`/`false`)

### Rate Limiting

- `DISABLE_RATE_LIMITS` (default: `true`)
- `RATELIMIT_STORAGE_URL` (default: `memory://`)

## Run Locally

From `lawyer/`:

```bash
pip install -r requirements.txt
python app.py
```

App starts on `http://127.0.0.1:5001`.

## Health Endpoint

- `GET /api/health`

## Tests

From `lawyer/`:

```bash
python -m unittest tests/test_routes_smoke.py
```
