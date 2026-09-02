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

---

## DONE — Authentication (first batch)

Email/password auth with JWT. POST /auth/register, POST /auth/login,
GET /auth/me. See git history for details — do not redo this batch.

## DONE — Products (first batch)

POST /products (seller-only, 403 for buyers), GET /products/mine.
ProductCreate/ProductRead schemas. See git history — do not redo this batch.

---

## CURRENT TASK — Product images + edit/delete

Extend the Product API: image upload, and edit/delete for the seller's own
products. This is the first batch of a larger "make products fully usable
for buyers" effort — later batches will add a public catalog; do NOT build
that yet.

### Deliverables

1. Migration: add `image_url` (string, nullable) to `products`.

2. GCS integration (app/core/storage.py or similar):
   - Read bucket name from Settings (new env var, e.g. GCS_BUCKET_NAME).
   - A small upload helper using google-cloud-storage — add it to
     requirements.txt with a stated reason (this task).

3. New routes (app/routers/products.py):
   - POST /products/{id}/image (Bearer token, seller-only, must own the
     product -> 403/404 otherwise) — accepts multipart/form-data file
     upload, uploads to GCS, saves the public URL to image_url, returns
     the updated ProductRead.
   - PATCH /products/{id} (Bearer token, must own the product) — partial
     update of title/description/price/stock. Returns ProductRead.
   - DELETE /products/{id} (Bearer token, must own the product) — deletes
     the product. Decide and document what happens to its image in GCS
     (delete it too, to avoid orphaned files).

4. ProductRead schema: add image_url (string | None).

### Acceptance criteria

- A seller can upload an image for their own product; other sellers get
  403 trying to upload/edit/delete a product they don't own.
- PATCH allows partial updates (only sent fields change).
- DELETE actually removes the row (and its GCS image, per the decision above).
- image_url is null until an image is uploaded — do not fake a placeholder.

### Out of scope (do NOT implement now)

- Public catalog / browsing other sellers' products.
- Multiple images per product, image resizing/thumbnails.
- Signed URLs / direct-to-GCS upload from the frontend.
- Categories.
