PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS branches (
 branch_id INTEGER PRIMARY KEY, branch_name TEXT NOT NULL UNIQUE, address TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS books (
 book_id INTEGER PRIMARY KEY, title TEXT NOT NULL, isbn TEXT NOT NULL UNIQUE,
 publication_year INTEGER, publisher TEXT, CHECK(publication_year IS NULL OR publication_year BETWEEN 0 AND 2100)
);
CREATE TABLE IF NOT EXISTS authors (
 author_id INTEGER PRIMARY KEY, author_name TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS book_authors (
 book_id INTEGER NOT NULL REFERENCES books(book_id) ON DELETE RESTRICT,
 author_id INTEGER NOT NULL REFERENCES authors(author_id) ON DELETE RESTRICT,
 PRIMARY KEY(book_id, author_id)
);
CREATE TABLE IF NOT EXISTS book_copies (
 copy_id INTEGER PRIMARY KEY, book_id INTEGER NOT NULL REFERENCES books(book_id) ON DELETE RESTRICT,
 branch_id INTEGER NOT NULL REFERENCES branches(branch_id) ON DELETE RESTRICT,
 status TEXT NOT NULL DEFAULT 'available' CHECK(status IN ('available','loaned'))
);
CREATE TABLE IF NOT EXISTS members (
 member_id INTEGER PRIMARY KEY, member_name TEXT NOT NULL, email TEXT NOT NULL UNIQUE,
 password_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS staff (
 staff_id INTEGER PRIMARY KEY, staff_name TEXT NOT NULL, email TEXT NOT NULL UNIQUE,
 password_hash TEXT NOT NULL, branch_id INTEGER NOT NULL REFERENCES branches(branch_id) ON DELETE RESTRICT
);
CREATE TABLE IF NOT EXISTS loans (
 loan_id INTEGER PRIMARY KEY, copy_id INTEGER NOT NULL REFERENCES book_copies(copy_id) ON DELETE RESTRICT,
 member_id INTEGER NOT NULL REFERENCES members(member_id) ON DELETE RESTRICT,
 staff_id INTEGER NOT NULL REFERENCES staff(staff_id) ON DELETE RESTRICT,
 checkout_date TEXT NOT NULL DEFAULT (date('now','localtime')), due_date TEXT NOT NULL,
 return_date TEXT, status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','returned')),
 CHECK(due_date >= checkout_date), CHECK(return_date IS NULL OR return_date >= checkout_date)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_one_active_loan_per_copy ON loans(copy_id) WHERE return_date IS NULL;
CREATE TABLE IF NOT EXISTS fines (
 fine_id INTEGER PRIMARY KEY, loan_id INTEGER NOT NULL UNIQUE REFERENCES loans(loan_id) ON DELETE RESTRICT,
 overdue_days INTEGER NOT NULL CHECK(overdue_days >= 0), amount REAL NOT NULL CHECK(amount >= 0),
 is_paid INTEGER NOT NULL DEFAULT 0 CHECK(is_paid IN (0,1))
);
CREATE TABLE IF NOT EXISTS partner_credentials (
 partner_id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, api_key TEXT NOT NULL, secret_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS librarian_sessions (
 token_hash TEXT PRIMARY KEY, staff_id INTEGER NOT NULL REFERENCES staff(staff_id) ON DELETE CASCADE,
 expires_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_copies_branch ON book_copies(branch_id);
CREATE INDEX IF NOT EXISTS idx_copies_book ON book_copies(book_id);
CREATE INDEX IF NOT EXISTS idx_loans_member ON loans(member_id);
CREATE INDEX IF NOT EXISTS idx_loans_status ON loans(status);
CREATE INDEX IF NOT EXISTS idx_loans_due_date ON loans(due_date);
