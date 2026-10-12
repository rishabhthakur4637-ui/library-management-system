"""Beginner-friendly REST API for the library."""
import hashlib
import os
import secrets
import re
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from fastapi import FastAPI, Depends, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from pydantic import BaseModel, Field, validator
from app.db import get_connection, initialize_database
from app.auth import (hash_password, verify_password, issue_member_token,
                     require_member, require_librarian, verify_partner)

app = FastAPI(title="Library Management System", version="1.0")
STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def frontend():
    return FileResponse(STATIC_DIR / "index.html")


@app.on_event("startup")
def startup():
    initialize_database()


@app.exception_handler(HTTPException)
async def http_error(request, exc):
    codes = {400:"BAD_REQUEST",401:"UNAUTHORIZED",403:"FORBIDDEN",404:"NOT_FOUND",409:"CONFLICT",422:"VALIDATION_ERROR"}
    message = exc.detail if isinstance(exc.detail, str) else "Request failed"
    return JSONResponse(status_code=exc.status_code, content={"error":{"code":codes.get(exc.status_code,"ERROR"),"message":message}}, headers=exc.headers)


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    return JSONResponse(status_code=422, content={"error":{"code":"VALIDATION_ERROR","message":"Request data is invalid"}})


@app.exception_handler(Exception)
async def unexpected_error(request, exc):
    return JSONResponse(status_code=500, content={"error":{"code":"INTERNAL_ERROR","message":"An unexpected server error occurred"}})


def run_one(sql, values=(), write=False):
    con=get_connection()
    try:
        cur=con.execute(sql, values)
        row=cur.fetchone()
        if write: con.commit()
        return row
    finally: con.close()


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=150)
    password: str = Field(min_length=8)

    @validator("email")
    def email_has_basic_shape(cls, value):
        value=value.strip()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
            raise ValueError("Enter a valid email address")
        return value.strip()

class MemberInput(BaseModel):
    member_name: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=150)
    password: str = Field(min_length=8)

    @validator("email")
    def email_has_basic_shape(cls, value):
        value=value.strip()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
            raise ValueError("Enter a valid email address")
        return value.strip()

class BookInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    isbn: str = Field(min_length=1, max_length=20)
    publication_year: Optional[int] = Field(default=None, ge=0, le=2100)
    publisher: Optional[str] = None
    authors: list[str] = Field(default_factory=list, max_length=20)

class CopyInput(BaseModel):
    branch_id: int = Field(gt=0)

class CheckoutInput(BaseModel):
    member_id: int = Field(gt=0)
    copy_id: int = Field(gt=0)
    checkout_date: Optional[date] = None
    due_date: date


# Authentication
@app.post("/auth/member/login")
def member_login(body: Credentials):
    row=run_one("SELECT member_id,password_hash FROM members WHERE email=?",(body.email,))
    if not row or not verify_password(body.password,row["password_hash"]): raise HTTPException(401,"Invalid email or password")
    return {"access_token":issue_member_token(row["member_id"]),"token_type":"bearer","expires_in":3600}

@app.post("/auth/librarian/login")
def librarian_login(body: Credentials, response: Response):
    row=run_one("SELECT staff_id,staff_name,password_hash FROM staff WHERE email=?",(body.email,))
    if not row or not verify_password(body.password,row["password_hash"]): raise HTTPException(401,"Invalid email or password")
    token=secrets.token_urlsafe(32); expiry=datetime.now(timezone.utc)+timedelta(hours=8)
    con=get_connection()
    try:
        con.execute("INSERT INTO librarian_sessions(token_hash,staff_id,expires_at) VALUES(?,?,?)",
                    (hashlib.sha256(token.encode()).hexdigest(),row["staff_id"],expiry.isoformat()))
        con.commit()
    finally: con.close()
    response.set_cookie("librarian_session",token,httponly=True,samesite="lax",secure=os.getenv("COOKIE_SECURE","false").lower()=="true",max_age=28800)
    return {"message":"Librarian login successful","staff_id":row["staff_id"],"staff_name":row["staff_name"],"expires_in":28800}

@app.post("/auth/librarian/logout")
def librarian_logout(request: Request, response: Response):
    token=request.cookies.get("librarian_session")
    if token:
        token_hash=hashlib.sha256(token.encode()).hexdigest()
        con=get_connection()
        try:
            con.execute("DELETE FROM librarian_sessions WHERE token_hash=?",(token_hash,))
            con.commit()
        finally: con.close()
    response.delete_cookie("librarian_session",httponly=True,samesite="lax",secure=os.getenv("COOKIE_SECURE","false").lower()=="true")
    return {"message":"Librarian logged out successfully"}

@app.get("/librarian/dashboard")
def librarian_dashboard(staff_id:int=Depends(require_librarian)):
    con=get_connection()
    try:
        staff=con.execute("SELECT staff_id,staff_name,email FROM staff WHERE staff_id=?",(staff_id,)).fetchone()
        if not staff: raise HTTPException(401,"Librarian session is invalid")
        summary={
            "available_copies":con.execute("SELECT COUNT(*) AS n FROM book_copies WHERE status='available'").fetchone()["n"],
            "total_members":con.execute("SELECT COUNT(*) AS n FROM members").fetchone()["n"],
            "overdue_loans":con.execute("SELECT COUNT(*) AS n FROM loans WHERE return_date IS NULL AND due_date < date('now','localtime')").fetchone()["n"],
            "total_books":con.execute("SELECT COUNT(*) AS n FROM books").fetchone()["n"],
            "currently_borrowed":con.execute("SELECT COUNT(*) AS n FROM loans WHERE return_date IS NULL").fetchone()["n"],
        }
        unpaid_fines=con.execute("SELECT COALESCE(SUM(amount),0) AS amount FROM fines WHERE is_paid=0").fetchone()["amount"]
        active_overdue=con.execute("SELECT COALESCE(SUM(CAST(julianday(date('now','localtime'))-julianday(l.due_date) AS INTEGER)*10),0) AS amount FROM loans l WHERE l.return_date IS NULL AND l.due_date < date('now','localtime') AND NOT EXISTS (SELECT 1 FROM fines f WHERE f.loan_id=l.loan_id AND f.is_paid=0)").fetchone()["amount"]
        summary["outstanding_fines"]=unpaid_fines+active_overdue
        members=[dict(row) for row in con.execute("SELECT member_id,member_name,email FROM members ORDER BY member_name")]
        available_copies=[dict(row) for row in con.execute("SELECT c.copy_id,b.title,br.branch_name FROM book_copies c JOIN books b ON b.book_id=c.book_id JOIN branches br ON br.branch_id=c.branch_id WHERE c.status='available' ORDER BY b.title,br.branch_name,c.copy_id")]
        active_loans=[dict(row) for row in con.execute("SELECT l.loan_id,l.member_id,m.member_name,l.copy_id,b.title,br.branch_name,l.due_date FROM loans l JOIN members m ON m.member_id=l.member_id JOIN book_copies c ON c.copy_id=l.copy_id JOIN books b ON b.book_id=c.book_id JOIN branches br ON br.branch_id=c.branch_id WHERE l.return_date IS NULL ORDER BY l.due_date,l.loan_id")]
        overdue_loans=[dict(row) for row in con.execute("SELECT l.loan_id,l.member_id,m.member_name,l.copy_id,b.title,br.branch_name,l.due_date,CAST(julianday(date('now','localtime'))-julianday(l.due_date) AS INTEGER) AS overdue_days,COALESCE(f.amount,CAST(julianday(date('now','localtime'))-julianday(l.due_date) AS INTEGER)*10) AS fine_amount FROM loans l JOIN members m ON m.member_id=l.member_id JOIN book_copies c ON c.copy_id=l.copy_id JOIN books b ON b.book_id=c.book_id JOIN branches br ON br.branch_id=c.branch_id LEFT JOIN fines f ON f.loan_id=l.loan_id WHERE l.return_date IS NULL AND l.due_date < date('now','localtime') ORDER BY l.due_date,l.loan_id")]
        loan_records=[dict(row) for row in con.execute("SELECT l.loan_id,l.member_id,m.member_name,b.title,l.copy_id,br.branch_name,l.checkout_date,l.due_date,l.return_date,l.status,CASE WHEN f.fine_id IS NOT NULL THEN f.overdue_days WHEN l.return_date IS NULL AND l.due_date < date('now','localtime') THEN CAST(julianday(date('now','localtime'))-julianday(l.due_date) AS INTEGER) ELSE 0 END AS overdue_days,COALESCE(f.amount,CASE WHEN l.return_date IS NULL AND l.due_date < date('now','localtime') THEN CAST(julianday(date('now','localtime'))-julianday(l.due_date) AS INTEGER)*10 ELSE 0 END) AS fine_amount FROM loans l JOIN members m ON m.member_id=l.member_id JOIN book_copies c ON c.copy_id=l.copy_id JOIN books b ON b.book_id=c.book_id JOIN branches br ON br.branch_id=c.branch_id LEFT JOIN fines f ON f.loan_id=l.loan_id ORDER BY l.loan_id DESC")]
        most_borrowed=[dict(row) for row in con.execute("SELECT b.book_id,b.title,COUNT(l.loan_id) AS total_borrowed FROM books b JOIN book_copies c ON c.book_id=b.book_id JOIN loans l ON l.copy_id=c.copy_id GROUP BY b.book_id,b.title ORDER BY total_borrowed DESC,b.title")]
        return {"staff":dict(staff),"summary":summary,"members":members,"available_copies":available_copies,"active_loans":active_loans,"loan_records":loan_records,"overdue_loans":overdue_loans,"most_borrowed":most_borrowed}
    finally: con.close()

# Books
@app.get("/books")
def list_books():
    con=get_connection()
    try:
        rows=con.execute("SELECT b.book_id,b.title,b.isbn,b.publication_year,b.publisher,group_concat(a.author_name, ', ') AS authors,(SELECT COUNT(*) FROM book_copies c WHERE c.book_id=b.book_id AND c.status='available') AS available_copies FROM books b LEFT JOIN book_authors ba ON ba.book_id=b.book_id LEFT JOIN authors a ON a.author_id=ba.author_id GROUP BY b.book_id ORDER BY b.title").fetchall()
        return [dict(r) for r in rows]
    finally: con.close()

@app.get("/books/{book_id}")
def get_book(book_id:int):
    con=get_connection()
    try:
        row=con.execute("SELECT book_id,title,isbn,publication_year,publisher FROM books WHERE book_id=?",(book_id,)).fetchone()
        if not row: raise HTTPException(404,"Book not found")
        book=dict(row)
        book["authors"]=[r["author_name"] for r in con.execute("SELECT a.author_name FROM authors a JOIN book_authors ba ON ba.author_id=a.author_id WHERE ba.book_id=? ORDER BY a.author_name",(book_id,)).fetchall()]
        book["copies"]=[dict(r) for r in con.execute("SELECT c.copy_id,c.status,b.branch_name FROM book_copies c JOIN branches b ON b.branch_id=c.branch_id WHERE c.book_id=? ORDER BY c.copy_id",(book_id,)).fetchall()]
        return book
    finally: con.close()

@app.post("/books",status_code=201)
def add_book(body:BookInput,staff_id=Depends(require_librarian)):
    con=get_connection()
    try:
        cur=con.execute("INSERT INTO books(title,isbn,publication_year,publisher) VALUES(?,?,?,?)",(body.title,body.isbn,body.publication_year,body.publisher))
        book_id=cur.lastrowid
        for name in dict.fromkeys(a.strip() for a in body.authors if a.strip()):
            con.execute("INSERT INTO authors(author_name) VALUES(?) ON CONFLICT(author_name) DO NOTHING",(name,))
            author=con.execute("SELECT author_id FROM authors WHERE author_name=?",(name,)).fetchone()
            con.execute("INSERT INTO book_authors(book_id,author_id) VALUES(?,?)",(book_id,author["author_id"]))
        con.commit()
        return {"book_id":book_id,"title":body.title,"isbn":body.isbn,"publication_year":body.publication_year,"publisher":body.publisher,"authors":list(dict.fromkeys(a.strip() for a in body.authors if a.strip()))}
    except Exception as e:
        con.rollback()
        if "UNIQUE" in str(e): raise HTTPException(409,"A book with this ISBN already exists")
        raise
    finally: con.close()

@app.post("/books/{book_id}/copies",status_code=201)
def add_book_copy(book_id:int,body:CopyInput,staff_id=Depends(require_librarian)):
    con=get_connection()
    try:
        if not con.execute("SELECT 1 FROM books WHERE book_id=?",(book_id,)).fetchone(): raise HTTPException(404,"Book not found")
        if not con.execute("SELECT 1 FROM branches WHERE branch_id=?",(body.branch_id,)).fetchone(): raise HTTPException(404,"Branch not found")
        cur=con.execute("INSERT INTO book_copies(book_id,branch_id) VALUES(?,?)",(book_id,body.branch_id))
        con.commit()
        return {"copy_id":cur.lastrowid,"book_id":book_id,"branch_id":body.branch_id,"status":"available"}
    except HTTPException: con.rollback(); raise
    finally: con.close()

@app.get("/partner/catalogue",dependencies=[Depends(verify_partner)])
def partner_catalogue(): return list_books()


# Members
@app.post("/members",status_code=201)
def register_member(body:MemberInput):
    try: row=run_one("INSERT INTO members(member_name,email,password_hash) VALUES(?,?,?) RETURNING member_id,member_name,email",(body.member_name,body.email,hash_password(body.password)),True)
    except Exception as e:
        if "UNIQUE" in str(e): raise HTTPException(409,"Email is already registered")
        raise
    return dict(row)

# Loans and returns
@app.post("/loans/checkout",status_code=201)
def checkout(body:CheckoutInput,staff_id:int=Depends(require_librarian)):
    today=date.today()
    checkout_date=body.checkout_date or max(today,date(2026,10,10))
    if checkout_date < date(2026,10,10): raise HTTPException(400,"Checkout date cannot be earlier than 2026-10-10")
    if body.due_date < checkout_date: raise HTTPException(400,"Due date cannot be earlier than the checkout date")
    con=get_connection()
    try:
        con.execute("BEGIN IMMEDIATE")
        member=con.execute("SELECT member_id FROM members WHERE member_id=?",(body.member_id,)).fetchone()
        copy=con.execute("SELECT status FROM book_copies WHERE copy_id=?",(body.copy_id,)).fetchone()
        if not member: raise HTTPException(404,"Member not found")
        if not copy: raise HTTPException(404,"Copy not found")
        if copy["status"]!='available': raise HTTPException(409,"Book copy is not available")
        count=con.execute("SELECT COUNT(*) AS n FROM loans WHERE member_id=? AND return_date IS NULL",(body.member_id,)).fetchone()["n"]
        if count>=3: raise HTTPException(409,"Member already has the maximum of three active loans")
        cur=con.execute("INSERT INTO loans(copy_id,member_id,staff_id,checkout_date,due_date) VALUES(?,?,?,?,?)",
                        (body.copy_id,body.member_id,staff_id,checkout_date.isoformat(),body.due_date.isoformat()))
        con.execute("UPDATE book_copies SET status='loaned' WHERE copy_id=?",(body.copy_id,)); con.commit()
        return {"loan_id":cur.lastrowid,"copy_id":body.copy_id,"member_id":body.member_id,"checkout_date":checkout_date.isoformat(),"due_date":body.due_date.isoformat(),"status":"active"}
    except HTTPException: con.rollback(); raise
    except Exception: con.rollback(); raise HTTPException(409,"Could not check out this copy")
    finally: con.close()

@app.get("/members/dashboard")
def member_dashboard(member_id:int=Depends(require_member)):
    con=get_connection()
    try:
        member=con.execute("SELECT member_id,member_name,email FROM members WHERE member_id=?",(member_id,)).fetchone()
        if not member: raise HTTPException(404,"Member not found")
        loans=[dict(row) for row in con.execute("SELECT l.loan_id,l.copy_id,b.title,l.checkout_date,l.due_date,l.return_date,l.status,CASE WHEN f.fine_id IS NOT NULL THEN f.overdue_days WHEN l.return_date IS NULL AND l.due_date < date('now','localtime') THEN CAST(julianday(date('now','localtime'))-julianday(l.due_date) AS INTEGER) ELSE 0 END AS overdue_days,COALESCE(f.amount,CASE WHEN l.return_date IS NULL AND l.due_date < date('now','localtime') THEN CAST(julianday(date('now','localtime'))-julianday(l.due_date) AS INTEGER)*10 ELSE 0 END) AS fine_amount FROM loans l JOIN book_copies c ON c.copy_id=l.copy_id JOIN books b ON b.book_id=c.book_id LEFT JOIN fines f ON f.loan_id=l.loan_id WHERE l.member_id=? ORDER BY l.loan_id DESC",(member_id,))]
        fines=[dict(row) for row in con.execute("SELECT f.fine_id,f.loan_id,f.overdue_days,f.amount,f.is_paid,l.due_date,l.return_date,b.title FROM fines f JOIN loans l ON l.loan_id=f.loan_id JOIN book_copies c ON c.copy_id=l.copy_id JOIN books b ON b.book_id=c.book_id WHERE l.member_id=? ORDER BY f.fine_id DESC",(member_id,))]
        current_borrowed=con.execute("SELECT COUNT(*) AS n FROM loans WHERE member_id=? AND return_date IS NULL",(member_id,)).fetchone()["n"]
        overdue_books=con.execute("SELECT COUNT(*) AS n FROM loans WHERE member_id=? AND return_date IS NULL AND due_date < date('now','localtime')",(member_id,)).fetchone()["n"]
        unpaid_fines=con.execute("SELECT COALESCE(SUM(f.amount),0) AS amount FROM fines f JOIN loans l ON l.loan_id=f.loan_id WHERE l.member_id=? AND f.is_paid=0",(member_id,)).fetchone()["amount"]
        active_overdue=con.execute("SELECT COALESCE(SUM(CAST(julianday(date('now','localtime'))-julianday(l.due_date) AS INTEGER)*10),0) AS amount FROM loans l WHERE l.member_id=? AND l.return_date IS NULL AND l.due_date < date('now','localtime') AND NOT EXISTS (SELECT 1 FROM fines f WHERE f.loan_id=l.loan_id AND f.is_paid=0)",(member_id,)).fetchone()["amount"]
        return {"member":dict(member),"summary":{"currently_borrowed":current_borrowed,"overdue_books":overdue_books,"outstanding_fines":unpaid_fines+active_overdue},"loans":loans,"fines":fines}
    finally: con.close()

@app.get("/loans/me")
def my_loans(member_id:int=Depends(require_member)):
    con=get_connection()
    try: return [dict(r) for r in con.execute("SELECT l.loan_id,l.copy_id,b.title,l.checkout_date,l.due_date,l.return_date,l.status FROM loans l JOIN book_copies c ON c.copy_id=l.copy_id JOIN books b ON b.book_id=c.book_id WHERE l.member_id=? ORDER BY l.loan_id DESC",(member_id,)).fetchall()]
    finally: con.close()

@app.post("/loans/{loan_id}/return")
def return_loan(loan_id:int,staff_id:int=Depends(require_librarian)):
    today=date.today()
    con=get_connection()
    try:
        con.execute("BEGIN IMMEDIATE")
        row=con.execute("SELECT copy_id,due_date,return_date FROM loans WHERE loan_id=?",(loan_id,)).fetchone()
        if not row: raise HTTPException(404,"Loan not found")
        if row["return_date"] is not None: raise HTTPException(409,"Loan has already been returned")
        days=max(0,(today-date.fromisoformat(row["due_date"])).days)
        con.execute("UPDATE loans SET return_date=?,status='returned' WHERE loan_id=?",(today.isoformat(),loan_id))
        con.execute("UPDATE book_copies SET status='available' WHERE copy_id=?",(row["copy_id"],))
        if days:
            con.execute("INSERT INTO fines(loan_id,overdue_days,amount) VALUES(?,?,?) ON CONFLICT(loan_id) DO UPDATE SET overdue_days=excluded.overdue_days,amount=excluded.amount",(loan_id,days,days*10))
        fine=con.execute("SELECT fine_id,amount FROM fines WHERE loan_id=?",(loan_id,)).fetchone()
        con.commit()
        return {"message":"Book returned successfully","loan_id":loan_id,"return_date":today.isoformat(),"overdue_days":days,"fine_amount":fine["amount"] if fine else 0}
    except HTTPException: con.rollback(); raise
    except Exception: con.rollback(); raise HTTPException(409,"Could not return this loan")
    finally: con.close()

# Fines
@app.get("/fines/me")
def my_fines(member_id:int=Depends(require_member)):
    con=get_connection()
    try: return [dict(r) for r in con.execute("SELECT f.fine_id,f.loan_id,f.overdue_days,f.amount,f.is_paid FROM fines f JOIN loans l ON l.loan_id=f.loan_id WHERE l.member_id=? ORDER BY f.fine_id",(member_id,)).fetchall()]
    finally: con.close()

@app.post("/fines/{fine_id}/pay")
def pay_fine(fine_id:int,member_id:int=Depends(require_member)):
    con=get_connection()
    try:
        row=con.execute("SELECT f.is_paid FROM fines f JOIN loans l ON l.loan_id=f.loan_id WHERE f.fine_id=? AND l.member_id=?",(fine_id,member_id)).fetchone()
        if not row: raise HTTPException(404,"Fine not found")
        if row["is_paid"]: raise HTTPException(409,"Fine is already paid")
        con.execute("UPDATE fines SET is_paid=1 WHERE fine_id=?",(fine_id,)); con.commit()
        return {"message":"Fine marked as paid","fine_id":fine_id,"payment_status":"paid"}
    finally: con.close()

# Librarian reports
@app.get("/reports/overdue-loans",dependencies=[Depends(require_librarian)])
def overdue_loans():
    con=get_connection()
    try: return [dict(r) for r in con.execute("SELECT l.loan_id,m.member_id,m.member_name,b.title,l.copy_id,l.due_date,CAST(julianday(date('now','localtime'))-julianday(l.due_date) AS INTEGER) AS overdue_days FROM loans l JOIN members m ON m.member_id=l.member_id JOIN book_copies c ON c.copy_id=l.copy_id JOIN books b ON b.book_id=c.book_id WHERE l.return_date IS NULL AND l.due_date < date('now','localtime') ORDER BY l.due_date").fetchall()]
    finally: con.close()

@app.get("/reports/most-borrowed-books",dependencies=[Depends(require_librarian)])
def most_borrowed_books():
    con=get_connection()
    try: return [dict(r) for r in con.execute("SELECT b.book_id,b.title,COUNT(l.loan_id) AS total_borrowed FROM books b JOIN book_copies c ON c.book_id=b.book_id JOIN loans l ON l.copy_id=c.copy_id GROUP BY b.book_id,b.title ORDER BY total_borrowed DESC,b.title").fetchall()]
    finally: con.close()
