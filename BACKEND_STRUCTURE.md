# Lawyer Backend Structure (Modularized)

The previous monolithic `app.py` has been split into modules so developers can navigate logic faster.

## Files

- `app.py`
  - Thin entrypoint.
  - Imports route modules and starts Flask app.

- `core.py`
  - Shared Flask app object, CSRF, limiter setup, logging, validation helpers, DB helper functions, and shared utility functions.
  - Contains reusable functions used by route modules.

- `routes/public_routes.py`
  - Public pages and APIs:
    - Home, lawyers listing, contact, lawyer apply flow, lawyer profile, ratings
    - Public/PWA/static routes
    - Lawyer search/state-district APIs
    - New `/auth-center` entry page

- `routes/auth_routes.py`
  - Authentication and role portal flows:
    - Admin login/logout
    - Lawyer login/dashboard/logout
    - User register/login/home/logout

- `routes/admin_routes.py`
  - Admin dashboards and admin APIs:
    - Admin panel data endpoints
    - Application status updates
    - Message status update/delete
    - Admin statistics and test-email API

- `templates/auth_center.html`
  - Frontend portal hub for User/Lawyer/Admin authentication entry.

## Startup

Run from `lawyer/`:

```bash
python app.py
```

The app runs on port `5001` (same as earlier behavior).
