# Architecture Overview

This document summarizes the high-level architecture of SerwisPRO.

- Framework: Flask (Blueprints for modularity)
- ORM: SQLAlchemy 2.x (declarative models with `Mapped` / `mapped_column`)
- App structure:
  - `app/` — application package
  - `app/models/` — SQLAlchemy models
  - `app/templates/` — Jinja2 templates
  - `app/static/` — static assets (css/js/img)
  - `app/<module>/` — feature blueprints (customers, orders, devices, ...)
- Multi-tenancy: models inherit from `BaseTenantModel` (company/branch fields)
- Services / Repositories: service layer contains business logic, repository layer handles DB access
- UI: Bootstrap 5.3, server-side rendered templates with progressive enhancement

Notes:
- Database migrations are managed via Alembic (migrations/). Do not apply migrations automatically in this doc.
- Sensitive configuration is kept in instance config files and environment variables.