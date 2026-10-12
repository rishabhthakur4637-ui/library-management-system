# Library Management System

A Python REST API for a public library with three branches. It replaces spreadsheet tracking with a relational SQLite database and supports books, authors, branch copies, members, staff, loans, fines, and partner catalogue access.

## Assignment requirements covered

- Normalized relational tables with primary keys, foreign keys, checks, unique constraints, and useful indexes.
- Sample records for three branches, books, authors, copies, members, staff, loans, and a fine.
- SQL reports for most borrowed books, overdue loans, and a member's loan history.
- Python's `sqlite3` data layer using parameterized queries for values supplied by requests.
- REST endpoints for books, members, loans, returns, fines, and partner catalogue access.
- Three authentication methods: member bearer token, librarian session cookie, and partner API key plus secret.
- Automated API tests, a Postman collection, a curl script, and the documentation on this page.

## Project structure

```text
app/
  main.py                 FastAPI routes, validation, and library rules
  auth.py                 Password hashing and member, librarian, and partner authentication
  db.py                   SQLite connections, schema initialization, and sample seeding
database/
  schema.sql              Tables, constraints, foreign keys, and indexes
  seed.sql                Repeatable sample data
  reports.sql             Plain SQL reporting examples
tests/
  test_api.py             API behavior tests using temporary databases
postman/
  library_api.json        Postman collection
scripts/
  run_server.py           Start API and open Swagger when ready
  test_api.sh             curl success and failure checks
requirements.txt          Python dependencies
README.md                 Setup, design, and API guide
```

## Database design

The database uses SQLite, which is included with Python and does not need a separate database server.

- `books` stores each title; `authors` stores authors. `book_authors` joins them so a title can have multiple authors and an author can have multiple titles.
- `branches` stores the three library locations. `book_copies` links a title to a branch and tracks whether each physical copy is available or loaned.
- `members` and `staff` store account details and password hashes. Each staff member is assigned to a branch.
- `loans` links a member, a copy, and the librarian who checked it out. A partial unique index allows only one active loan for a copy.
- `fines` stores overdue days, amount, and payment status, with at most one fine per loan.
- `partner_credentials` stores the partner key and a hash of its secret. `librarian_sessions` stores hashed session tokens and their expiry.

Foreign key checks are enabled on every SQLite connection. Indexes support copy lookups and loan-member, status, and due-date queries. See [schema.sql](database/schema.sql), [seed.sql](database/seed.sql), and [reports.sql](database/reports.sql).

Sample data includes three branches, four books, multiple copies, sample member and librarian accounts, a returned late loan with an unpaid fine, and an active overdue loan. Startup creates missing tables and inserts missing seed rows, so initialization can be repeated safely.

## Library rules and design decisions

- Only a librarian session can check out or return a copy. Checkout requires a valid member, an available copy, and a due date that is today or later.
- A member may have at most three active loans. The fourth checkout is rejected.
- A return on or before the due date has no fine. Each calendar day after the due date adds 10 units. A fine is created when a late loan is returned.
- Members can view their own loan history and fines, and can pay only their own fines. The member ID used for these checks comes from the verified token.
- Paying a fine sets its `is_paid` status. This assignment does not integrate an external payment provider.
- Member passwords use PBKDF2 hashing. Member tokens are signed and expire after one hour. Librarian sessions expire after eight hours; the cookie is HTTP-only.
- The partner catalogue route requires both `X-API-Key` and `X-API-Secret` headers. The partner secret is stored as a password hash.
- API errors use the same JSON shape: `{ "error": { "code": "...", "message": "..." } }`.

## Run on Windows

Open PowerShell and change to the project folder:

```powershell
cd "C:\Users\rt815\Desktop\library_management_system"
```

If `.venv` does not exist yet, create it and install the dependencies:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Set local development credentials in that same PowerShell window, then start the API using the `.venv` interpreter:

```powershell
$env:TOKEN_SECRET = "local-development-secret-change-this"
$env:PARTNER_API_KEY = "local-catalogue-key"
$env:PARTNER_API_SECRET = "local-catalogue-secret"
.\.venv\Scripts\python.exe scripts\run_server.py
```

The server initializes `library.db` in the project folder on startup. Keep this terminal open while using the API. When the API is ready, the launcher opens Swagger UI at **http://127.0.0.1:8000/docs** in your default browser. Stop the server with `Ctrl+C`.

The app also reads these settings from a `.env` file. `DATABASE_PATH` can point to a different SQLite file. Use a strong random `TOKEN_SECRET` and real partner credentials outside local development; set `COOKIE_SECURE=true` when serving over HTTPS. Do not commit real credentials.

## Try the API in Swagger

Open `http://127.0.0.1:8000/docs`, expand a route, choose **Try it out**, fill in the request fields, then choose **Execute**.

1. Try `GET /books` to list the seeded titles.
2. Use `POST /auth/librarian/login` with a sample librarian account to set the session cookie. The browser keeps this cookie for the protected librarian routes.
3. Use `POST /auth/member/login` to receive an access token. For member routes, send it in the `Authorization` header as `Bearer <access_token>`.
4. For `GET /partner/catalogue`, provide both partner headers. Local development values are shown below.

The API base URL is `http://127.0.0.1:8000`.

## API endpoints

| Method | Path | Access | Purpose |
|---|---|---|---|
| `GET` | `/books` | Public | List books and authors |
| `GET` | `/books/{book_id}` | Public | Get a book, authors, and physical copies |
| `POST` | `/books` | Librarian session | Add a book; accepts an optional `authors` array |
| `POST` | `/books/{book_id}/copies` | Librarian session | Add a copy at a branch using `{ "branch_id": 1 }` |
| `POST` | `/members` | Public | Register a member |
| `POST` | `/auth/member/login` | Public | Log in and receive a bearer token |
| `POST` | `/auth/librarian/login` | Public | Log in and receive a session cookie |
| `POST` | `/loans/checkout` | Librarian session | Check out a copy to a member |
| `GET` | `/loans/me` | Member token | View the signed-in member's loan history |
| `POST` | `/loans/{loan_id}/return` | Librarian session | Return a copy and calculate a fine if late |
| `GET` | `/fines/me` | Member token | View the signed-in member's fines |
| `POST` | `/fines/{fine_id}/pay` | Owning member token | Mark the member's fine as paid |
| `GET` | `/reports/overdue-loans` | Librarian session | List active overdue loans |
| `GET` | `/reports/most-borrowed-books` | Librarian session | Rank books by loan count |
| `GET` | `/partner/catalogue` | Partner headers | Return the protected book catalogue |

The checkout request body is `{ "member_id": 1, "copy_id": 1, "due_date": "2099-12-31" }`. A book request can include multiple authors, for example `{ "title": "Shared Voices", "isbn": "ISBN-EXAMPLE", "authors": ["Author One", "Author Two"] }`.

Successful reads, returns, and fine payments return `200`; creations return `201`. Common errors use `400` for a bad request, `401` for missing or invalid authentication, `404` for a missing record, `409` for a conflict, and `422` for invalid fields.

## Sample accounts

All sample member and librarian accounts use the local password `password123`.

| Role | Email |
|---|---|
| Member | `aman@example.com` |
| Member | `priya@example.com` |
| Member | `rahul@example.com` |
| Librarian | `librarian1@example.com` |
| Librarian | `librarian2@example.com` |
| Librarian | `librarian3@example.com` |

Local partner headers:

```text
X-API-Key: local-catalogue-key
X-API-Secret: local-catalogue-secret
```

These sample credentials are for local development only.

## Tests and API examples

Run automated tests in a second PowerShell terminal from the project folder:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Tests create a temporary database, so they do not change `library.db`. They cover authentication and member privacy, the three-loan limit, unavailable copies, return and fine rules, reporting, multiple authors, and branch copies.

If Python reports an import error involving `pydantic_core`, reinstall the project dependencies in `.venv` and run tests with that same interpreter. This avoids accidentally using another environment such as `venv`:

```powershell
.\.venv\Scripts\python.exe -m pip install --force-reinstall --no-cache-dir -r requirements.txt
.\.venv\Scripts\python.exe -m pytest -q
```

Import [library_api.json](postman/library_api.json) into Postman. Log in as a member before calling member routes, and as a librarian before checkout, return, or report routes.

For curl checks, start the API first and run `scripts/test_api.sh` from Git Bash or WSL. The script exercises success and failure responses and consumes sample copies, so use a disposable database if you need to preserve the seeded copy availability.

## Reporting SQL

The plain SQL examples in [reports.sql](database/reports.sql) use joins and filters to show most-borrowed books, overdue loans, and a member's loan history. The member-history query uses a `?` parameter. Request values in Python queries are also bound using SQLite placeholders; SQL is not built from request data using string formatting.

## Project video

[Watch the project video on Loom](https://www.loom.com/share/03bf2d55820c4f1ba8cde15a543f57bf)

