# Marketplace Backend — Agent Context

## Purpose

Educational marketplace project (think WB/Temu, but built step by step).
The owner is a frontend engineer learning backend + DevOps. The goal is a
clean, understandable, production-shaped codebase — NOT a feature-complete
clone. Correctness and clarity over cleverness.

## Working Agreement (IMPORTANT)

- Do ONLY what the current task asks. Do not add extra features, endpoints,
  or abstractions that were not requested.
- Prefer simple, explicit code over clever or "future-proof" code.
- When a design decision is ambiguous, STOP and ask instead of guessing.
- Explain non-obvious choices in short comments.
- No premature optimization, no speculative microservices, no extra libraries
  without a stated reason.

## Tech Stack

- Language: Python 3.14
- Framework: FastAPI
- Server: Uvicorn
- Database: PostgreSQL (already installed locally)
- ORM: SQLAlchemy 2.x
- Migrations: Alembic
- Validation: Pydantic v2
- Auth: JWT access tokens (refresh tokens will come later, NOT now)
- Password hashing: passlib[bcrypt]

## Project Structure

marketplace-backend/
app/
main.py # FastAPI app entry
db/ # database engine, session, base
models/ # SQLAlchemy ORM models (DB tables)
schemas/ # Pydantic models (API request/response shapes)
routers/ # API routes grouped by domain
core/ # config, security (JWT, hashing)
alembic/ # migrations
requirements.txt
Makefile
.env # secrets & config (never committed)

## Conventions

- Keep DB models (models/) and API schemas (schemas/) SEPARATE. Never return
  ORM objects directly; always map to a Pydantic schema.
- One router file per domain (e.g. routers/auth.py).
- Config and secrets come from environment variables via a settings object
  in core/config.py. Never hardcode secrets.
- Passwords are ALWAYS stored hashed. Never store or log plaintext passwords.
- Use dependency injection for the DB session and the current user.

## Data Model (current scope only)

### User

- id: UUID (primary key)
- email: string, unique, required
- hashed_password: string, required
- role: enum { buyer, seller } — default buyer
- created_at: timestamp

### Product

- id: UUID (primary key)
- title: string, required
- description: string, nullable
- price: numeric(10,2), required
- stock: integer, default 0
- seller_id: UUID (FK -> users.id), required
- image_url: string, nullable — public GCS URL, set by POST /products/{id}/image
- created_at: timestamp

More entities (Category, Order, etc.) will be added in later tasks.
Do NOT create them yet.

## Image Storage (decided — do not re-litigate)

- Product images live in a Google Cloud Storage bucket in the same GCP
  project as Cloud Run (marketplace-507219). Only a public URL string is
  stored in the DB (products.image_url) — never image bytes in Postgres.
- Upload flow: the backend proxies the upload. The frontend sends the file
  as multipart/form-data directly to the backend; the backend uploads it to
  GCS via the google-cloud-storage SDK and stores the resulting public URL.
  The frontend never talks to GCS directly (no signed URLs in this batch).
- Bucket name comes from Settings (env var), never hardcoded.

## AI / Claude API (decided — in progress, learning-mode)

- Provider: Claude API via the official `anthropic` Python SDK, pinned
  `anthropic>=1.15,<2` (no surprise major upgrades).
- Dev model: Claude Haiku 5.5 (cheapest).
- Key: `anthropic_api_key` in Settings (from `ANTHROPIC_API_KEY`), passed
  explicitly to the client — pydantic-settings does NOT export .env into
  os.environ, so the SDK can't auto-read it.
- Key lives in the `marketplace-dev` Anthropic workspace ($5 spend limit).
  Prod reuses the same key (training project — owner's call); a real
  product would use a separate prod workspace + service account key.
- Prod: GCP secret `marketplace-anthropic-key` (secretAccessor granted to
  the compute SA + github-deployer, same as the other secrets), wired via
  `--set-secrets ANTHROPIC_API_KEY=...` in .github/workflows/deploy.yml.
  `anthropic_api_key` is a required Setting — without it Cloud Run won't start.

### DONE — AI product description (backend)

POST /products/generate-description (seller-only, multipart: `title` +
optional `image` JPEG/PNG/GIF/WebP ≤ 5 MB) -> { description }. Nothing is
saved — the seller edits the text and saves the product normally. Claude
logic lives in app/core/ai.py (AIGenerationError -> 502 in the router).

---

## DONE — Authentication (first batch)

Email/password auth with JWT. POST /auth/register, POST /auth/login,
GET /auth/me. See git history for details — do not redo this batch.

## DONE — Products (first batch)

POST /products (seller-only, 403 for buyers), GET /products/mine.
ProductCreate/ProductRead schemas. See git history — do not redo this batch.

---

## DONE — Product images + edit/delete

POST /products/{id}/image (multipart upload to GCS), PATCH /products/{id}
(partial update), DELETE /products/{id} (also deletes GCS image). All
seller-only, ownership-checked. See git history — do not redo this batch.

---

## CURRENT TASK — Public product catalog (read-only, for buyers)

Add read-only, unauthenticated endpoints so anyone (including logged-out
visitors) can browse all sellers' products. This is intentionally
read-only — no cart, no orders, no checkout yet. Buying itself is a later
batch; do NOT build it now.

### Deliverables

1. New routes in app/routers/products.py, placed BEFORE `/mine` if there's
   any path-matching ambiguity (there shouldn't be, since these are
   unauthenticated — no `Depends(get_current_seller)` — but keep route
   order sane regardless):
   - GET /products — public, no auth required. Returns products from ALL
     sellers, newest first (same ordering as /mine), PAGINATED via
     `limit`/`offset` query params (limit default 20, max 100; offset
     default 0). Also accepts an optional `search` query param (string)
     that filters by case-insensitive substring match on `title` before
     pagination is applied — e.g. GET /products?search=camera&limit=20.
     Response is NOT a bare list — it's `ProductPage` (see schema below)
     so the frontend can render a pager/know the total count.
   - GET /products/{id} — public, no auth required. Returns a single
     ProductRead by id, or 404 if it doesn't exist. This is for a product
     detail page on the frontend.

2. New Pydantic schema in app/schemas/product.py:
   - ProductPage: { items: list[ProductRead], total: int }. `total` is
     the count matching the search filter BEFORE limit/offset are
     applied (so the frontend can compute page count).

### Acceptance criteria

- GET /products with no query params returns the first page (default
  limit) of products across all sellers, with no Authorization header
  required, plus an accurate `total`.
- GET /products?search=xyz only counts/returns products whose title
  contains "xyz" (case-insensitive) — `total` reflects the filtered count,
  not the whole table.
- GET /products?limit=5&offset=5 returns the correct second page.
- limit is clamped/validated to (1, 100]; invalid values are a 422, not a
  silent clamp — use FastAPI's Query validation (ge/le) rather than
  hand-rolled clamping.
- GET /products/{id} returns the product for a valid id; 404 for an
  unknown id. No auth required, no ownership check (any product, any
  visitor).
- GET /products/mine and the seller-only mutation routes are UNCHANGED —
  this task only adds new routes, it does not touch seller-side behavior.

### Out of scope (do NOT implement now)

- Cart, orders, checkout, payments.
- Categories, sorting, price-range filters.
- Reviews/ratings.
- Any change to auth, roles, or the seller-side product routes.
