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

More entities (Product, Category, Order, etc.) will be added in later tasks.
Do NOT create them yet.

---

## CURRENT TASK — Authentication (first batch)

Implement email/password authentication with JWT.

### Deliverables

1. Database setup
   - SQLAlchemy engine + session (app/db/).
   - PostgreSQL connection string from .env.
   - Alembic configured; generate the first migration for the User table.

2. User model (app/models/user.py) per the data model above.

3. Pydantic schemas (app/schemas/user.py):
   - UserCreate (email, password, role optional -> default buyer)
   - UserRead (id, email, role, created_at) — NO password field
   - Token (access_token, token_type)

4. Security (app/core/security.py):
   - Password hashing/verify (passlib bcrypt).
   - JWT create + decode (use a SECRET_KEY from .env, HS256).

5. Auth routes (app/routers/auth.py):
   - POST /auth/register -> create user, return UserRead
   - POST /auth/login -> verify credentials, return Token (JWT)
   - GET /auth/me -> protected; return current user from the JWT

6. Wire routers into app/main.py.

### Acceptance criteria

- Can register a user; password is stored hashed, never returned.
- Can log in with correct credentials and receive a JWT.
- GET /auth/me returns the user only with a valid token, 401 otherwise.
- Duplicate email registration returns a clear 400 error.
- `make dev` runs the server; Alembic migration creates the users table.

### Out of scope (do NOT implement now)

- Refresh tokens, password reset, email verification.
- Any product/order logic.
- Role-based permissions beyond storing the role field.
