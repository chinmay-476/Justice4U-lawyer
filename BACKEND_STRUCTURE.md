# Lawyer Backend Structure (Modularized)

The previous monolithic `app.py` has been split into modules so developers can navigate logic faster.

For setup, security, env variables, and test commands, see `README.md`.

## Files

- `app.py`
  - Thin entrypoint.
  - Imports route modules and starts Flask app.

- `core.py`
  - Shared Flask app object, session/cookie security settings, security headers, CSRF, limiter setup, logging, validation helpers, DB helper functions, and shared utility functions.
  - Contains reusable functions used by route modules.

- `routes/public_routes.py`
  - Public pages and APIs:
    - Home, lawyers listing, contact, lawyer apply flow, lawyer profile, ratings
    - Public/PWA/static routes
    - Lawyer search/state-district APIs
    - New `/auth-center` entry page
    - Health endpoint: `/api/health`

- `routes/auth_routes.py`
  - Authentication and role portal flows:
    - Admin login/logout
    - Lawyer login/dashboard/logout
    - User register/login/home/logout
  - Uses server-side session state for auth.

- `routes/admin_routes.py`
  - Admin dashboards and admin APIs:
    - Admin panel data endpoints
    - Application status updates
    - Message status update/delete
    - Admin statistics and test-email API

- `tests/test_routes_smoke.py`
  - Basic smoke checks for public and PWA routes.

- `templates/auth_center.html`
  - Frontend portal hub for User/Lawyer/Admin authentication entry.

## Startup

Run from `lawyer/`:

```bash
python app.py
```

The app runs on port `5001` (same as earlier behavior).
