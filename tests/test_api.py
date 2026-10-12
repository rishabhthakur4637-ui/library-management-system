"""API behavior tests use an isolated temporary SQLite file per test."""
import pytest
from datetime import date as real_date, timedelta
from fastapi.testclient import TestClient
from app.main import app
from app.db import get_connection, initialize_database


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test-library.sqlite"))
    monkeypatch.setenv("PARTNER_API_KEY", "test-key")
    monkeypatch.setenv("PARTNER_API_SECRET", "test-secret")
    with TestClient(app) as test_client:
        yield test_client


def member_token(client, email="aman@example.com"):
    result=client.post("/auth/member/login",json={"email":email,"password":"password123"})
    assert result.status_code==200
    return {"Authorization":"Bearer "+result.json()["access_token"]}


def librarian(client):
    result=client.post("/auth/librarian/login",json={"email":"librarian1@example.com","password":"password123"})
    assert result.status_code==200


class FrozenDate(real_date):
    """Date replacement whose today() is controlled by individual tests."""
    fixed_today = real_date(2025, 5, 20)

    @classmethod
    def today(cls):
        return cls.fixed_today


def create_loan_due_on(client, due_on, checkout_on="2020-01-01"):
    """Create a valid loan, then move its dates back while preserving constraints."""
    checkout_date = real_date.today()
    future_due = (checkout_date + timedelta(days=30)).isoformat()
    response = client.post("/loans/checkout", json={"member_id":1,"copy_id":1,"due_date":future_due})
    assert response.status_code == 201
    loan_id = response.json()["loan_id"]
    con = get_connection()
    try:
        con.execute("UPDATE loans SET checkout_date=?,due_date=? WHERE loan_id=?",
                    (checkout_on,due_on,loan_id))
        con.commit()
    finally:
        con.close()
    return loan_id


def test_three_active_loan_limit_and_unavailable_copy(client):
    librarian(client)
    for copy in (1,3,7):
        response=client.post("/loans/checkout",json={"member_id":1,"copy_id":copy,"due_date":"2099-12-31"})
        assert response.status_code==201
    fourth=client.post("/loans/checkout",json={"member_id":1,"copy_id":2,"due_date":"2099-12-31"})
    assert fourth.status_code==409 and "three" in fourth.json()["error"]["message"]
    con=get_connection()
    try:
        assert con.execute("SELECT COUNT(*) FROM loans WHERE member_id=1 AND return_date IS NULL").fetchone()[0]==3
        assert con.execute("SELECT status FROM book_copies WHERE copy_id=2").fetchone()[0]=="available"
    finally: con.close()
    unavailable=client.post("/loans/checkout",json={"member_id":2,"copy_id":1,"due_date":"2099-12-31"})
    assert unavailable.status_code==409


def test_checkout_date_allows_on_or_after_2026_10_10_and_rejects_earlier_dates(client,monkeypatch):
    librarian(client)
    FrozenDate.fixed_today=real_date(2026,10,12)
    monkeypatch.setattr("app.main.date",FrozenDate)
    checkout_dates=((1,1,"2026-10-10"),(1,3,"2026-10-12"),(1,4,"2027-06-15"),(2,5,"2028-01-01"))
    for member_id,copy_id,checkout_date in checkout_dates:
        response=client.post("/loans/checkout",json={"member_id":member_id,"copy_id":copy_id,"checkout_date":checkout_date,"due_date":checkout_date})
        assert response.status_code==201
        assert response.json()["checkout_date"]==checkout_date

    invalid_dates=("2026-10-09","2025-05-20","1900-01-01")
    for copy_id,checkout_date in zip((6,7,8),invalid_dates):
        response=client.post("/loans/checkout",json={"member_id":2,"copy_id":copy_id,"checkout_date":checkout_date,"due_date":"2099-12-31"})
        assert response.status_code==400
        assert "checkout date" in response.json()["error"]["message"].lower()

    before_checkout=client.post("/loans/checkout",json={"member_id":2,"copy_id":6,"checkout_date":"2026-10-10","due_date":"2026-10-09"})
    assert before_checkout.status_code==400
    assert "due date" in before_checkout.json()["error"]["message"].lower()
    con=get_connection()
    try:
        assert con.execute("SELECT checkout_date FROM loans WHERE copy_id=1 AND member_id=1 AND return_date IS NULL").fetchone()[0]=="2026-10-10"
        assert con.execute("SELECT checkout_date FROM loans WHERE copy_id=9 AND loan_id=2").fetchone()[0]=="2025-03-01"
    finally: con.close()


@pytest.mark.parametrize("days_late,expected_fine", [(0,0),(1,10),(5,50)])
def test_due_date_and_overdue_fine_amounts(client,monkeypatch,days_late,expected_fine):
    librarian(client)
    FrozenDate.fixed_today=real_date(2025,5,20)
    monkeypatch.setattr("app.main.date",FrozenDate)
    due_on=(FrozenDate.fixed_today-timedelta(days=days_late)).isoformat()
    loan=create_loan_due_on(client,due_on)
    first=client.post(f"/loans/{loan}/return")
    assert first.status_code==200
    days=first.json()["overdue_days"]
    assert days==days_late and first.json()["fine_amount"]==expected_fine
    con=get_connection()
    try:
        fine=con.execute("SELECT overdue_days,amount FROM fines WHERE loan_id=?",(loan,)).fetchone()
        if days_late:
            assert fine["overdue_days"]==days_late and fine["amount"]==expected_fine
            assert con.execute("SELECT COUNT(*) FROM fines WHERE loan_id=?",(loan,)).fetchone()[0]==1
        else:
            assert fine is None
            assert con.execute("SELECT COUNT(*) FROM fines WHERE loan_id=?",(loan,)).fetchone()[0]==0
        assert con.execute("SELECT status FROM book_copies WHERE copy_id=1").fetchone()[0]=="available"
    finally: con.close()
    assert client.post(f"/loans/{loan}/return").status_code==409


def test_member_isolation_and_fine_payment_scope(client):
    librarian(client)
    FrozenDate.fixed_today=real_date(2025,5,20)
    loan=create_loan_due_on(client,"2025-05-15")
    client.post(f"/loans/{loan}/return")
    aman=member_token(client)
    priya=member_token(client,"priya@example.com")
    assert len(client.get("/loans/me",headers=aman).json())==1
    assert client.get("/loans/me",headers=priya).json()==[]
    fine=client.get("/fines/me",headers=aman).json()[0]["fine_id"]
    assert client.get("/fines/me",headers=priya).json()==[]
    assert client.post(f"/fines/{fine}/pay",headers=priya).status_code==404
    assert client.post(f"/fines/{fine}/pay",headers=aman).status_code==200


def test_member_dashboard_is_token_scoped_and_shows_loans_and_fines(client):
    assert client.get("/members/dashboard").status_code==401
    assert client.get("/members/dashboard",headers={"Authorization":"Bearer invalid"}).status_code==401
    rahul=member_token(client,"rahul@example.com")
    dashboard=client.get("/members/dashboard",headers=rahul)
    assert dashboard.status_code==200
    data=dashboard.json()
    assert data["member"]["member_id"]==3 and data["member"]["member_name"]=="Rahul Kumar"
    assert len(data["loans"])==2
    active=next(row for row in data["loans"] if row["loan_id"]==2)
    returned=next(row for row in data["loans"] if row["loan_id"]==1)
    assert active["title"]=="Animal Farm" and active["checkout_date"]=="2025-03-01"
    assert active["return_date"] is None and active["overdue_days"]>0
    assert active["fine_amount"]==active["overdue_days"]*10
    assert returned["return_date"]=="2025-01-12" and returned["overdue_days"]==2 and returned["fine_amount"]==20
    assert data["fines"][0]["loan_id"]==1 and data["fines"][0]["title"]=="Animal Farm"
    con=get_connection()
    try:
        assert data["summary"]["currently_borrowed"]==con.execute("SELECT COUNT(*) FROM loans WHERE member_id=3 AND return_date IS NULL").fetchone()[0]
        assert data["summary"]["overdue_books"]==con.execute("SELECT COUNT(*) FROM loans WHERE member_id=3 AND return_date IS NULL AND due_date<date('now','localtime')").fetchone()[0]
    finally: con.close()

    aman=member_token(client,"aman@example.com")
    spoofed=client.get("/members/dashboard?member_id=3",headers=aman)
    assert spoofed.status_code==200 and spoofed.json()["member"]["member_id"]==1
    assert spoofed.json()["loans"]==[] and spoofed.json()["fines"]==[]
    assert client.get("/loans/me?member_id=3",headers=aman).json()==[]
    assert client.get("/fines/me?member_id=3",headers=aman).json()==[]
    assert client.post("/fines/1/pay",headers=aman).status_code==404
    assert client.post("/fines/1/pay",headers=rahul).status_code==200
    assert client.get("/members/dashboard",headers=rahul).json()["fines"][0]["is_paid"]==1


def test_website_entry_keeps_member_staff_signin_and_swagger(client):
    page=client.get("/")
    assert page.status_code==200
    assert 'href="#member-dashboard"' in page.text
    assert 'id="member-login-form"' in page.text and 'id="login-form"' in page.text
    assert client.get("/static/app.js").status_code==200
    assert client.get("/static/styles.css").status_code==200
    assert client.get("/books").status_code==200
    assert client.get("/docs").status_code==200


def test_authentication_partner_and_librarian_permissions(client):
    assert client.get("/reports/most-borrowed-books").status_code==401
    assert client.post("/loans/1/return").status_code==401
    assert client.post("/auth/member/login",json={"email":"aman@example.com","password":"wrongpass"}).status_code==401
    assert client.get("/loans/me",headers={"Authorization":"Bearer invalid-token"}).status_code==401
    assert client.get("/partner/catalogue").status_code==401
    assert client.get("/partner/catalogue",headers={"X-API-Key":"wrong","X-API-Secret":"test-secret"}).status_code==401
    assert client.get("/partner/catalogue",headers={"X-API-Key":"test-key","X-API-Secret":"wrong"}).status_code==401
    assert client.get("/partner/catalogue",headers={"X-API-Key":"test-key","X-API-Secret":"test-secret"}).status_code==200
    librarian(client)
    assert client.get("/reports/most-borrowed-books").status_code==200
    assert client.get("/reports/overdue-loans").status_code==200


def test_librarian_dashboard_data_checkout_return_and_logout(client):
    assert client.get("/librarian/dashboard").status_code==401
    assert client.post("/auth/librarian/login",json={"email":"librarian1@example.com","password":"wrongpass"}).status_code==401
    login=client.post("/auth/librarian/login",json={"email":"librarian1@example.com","password":"password123"})
    assert login.status_code==200 and login.json()["staff_name"]=="Librarian One"

    dashboard=client.get("/librarian/dashboard")
    assert dashboard.status_code==200
    data=dashboard.json()
    assert data["staff"]["staff_name"]=="Librarian One"
    con=get_connection()
    try:
        assert data["summary"]["available_copies"]==con.execute("SELECT COUNT(*) FROM book_copies WHERE status='available'").fetchone()[0]
        assert data["summary"]["total_members"]==con.execute("SELECT COUNT(*) FROM members").fetchone()[0]
        assert data["summary"]["total_books"]==con.execute("SELECT COUNT(*) FROM books").fetchone()[0]
        assert data["summary"]["currently_borrowed"]==con.execute("SELECT COUNT(*) FROM loans WHERE return_date IS NULL").fetchone()[0]
        assert data["summary"]["overdue_loans"]==con.execute("SELECT COUNT(*) FROM loans WHERE return_date IS NULL AND due_date<date('now','localtime')").fetchone()[0]
        unpaid=con.execute("SELECT COALESCE(SUM(amount),0) FROM fines WHERE is_paid=0").fetchone()[0]
        accruing=con.execute("SELECT COALESCE(SUM(CAST(julianday(date('now','localtime'))-julianday(due_date) AS INTEGER)*10),0) FROM loans WHERE return_date IS NULL AND due_date<date('now','localtime') AND NOT EXISTS(SELECT 1 FROM fines f WHERE f.loan_id=loans.loan_id AND f.is_paid=0)").fetchone()[0]
        assert data["summary"]["outstanding_fines"]==unpaid+accruing
    finally: con.close()
    assert len(data["members"])==3 and any(copy["copy_id"]==1 for copy in data["available_copies"])
    assert any(row["loan_id"]==2 and row["branch_name"]=="North Branch" for row in data["active_loans"])
    assert any(row["loan_id"]==2 and row["overdue_days"]>0 for row in data["overdue_loans"])
    assert any(row["title"]=="Animal Farm" and row["total_borrowed"]==2 for row in data["most_borrowed"])
    assert data["most_borrowed"]==client.get("/reports/most-borrowed-books").json()
    overdue_record=next(row for row in data["loan_records"] if row["loan_id"]==2)
    returned_record=next(row for row in data["loan_records"] if row["loan_id"]==1)
    assert overdue_record["member_id"]==3 and overdue_record["member_name"]=="Rahul Kumar"
    assert overdue_record["title"]=="Animal Farm" and overdue_record["checkout_date"]=="2025-03-01" and overdue_record["due_date"]=="2025-03-15"
    assert overdue_record["status"]=="active" and overdue_record["fine_amount"]==overdue_record["overdue_days"]*10
    assert returned_record["return_date"]=="2025-01-12" and returned_record["fine_amount"]==20

    checkout=client.post("/loans/checkout",json={"member_id":1,"copy_id":1,"due_date":(real_date.today()+timedelta(days=14)).isoformat()})
    assert checkout.status_code==201
    loan_id=checkout.json()["loan_id"]
    assert any(row["loan_id"]==loan_id for row in client.get("/librarian/dashboard").json()["active_loans"])
    returned=client.post(f"/loans/{loan_id}/return")
    assert returned.status_code==200
    refreshed=client.get("/librarian/dashboard").json()
    assert all(row["loan_id"]!=loan_id for row in refreshed["active_loans"])
    assert refreshed["summary"]["available_copies"]==8

    assert client.get("/books").status_code==200
    assert client.post("/auth/librarian/logout").status_code==200
    assert client.get("/librarian/dashboard").status_code==401
    assert client.get("/reports/most-borrowed-books").status_code==401


def test_expired_member_token_is_rejected(client,monkeypatch):
    headers=member_token(client)
    monkeypatch.setattr("app.auth.time.time",lambda: 10**12)
    assert client.get("/loans/me",headers=headers).status_code==401


def test_seed_is_repeatable_and_database_constraints_work(client):
    initialize_database()
    initialize_database()
    con=get_connection()
    try:
        assert con.execute("SELECT COUNT(*) FROM branches").fetchone()[0]==3
        assert con.execute("SELECT COUNT(*) FROM books").fetchone()[0]==4
        assert con.execute("SELECT COUNT(*) FROM members").fetchone()[0]==3
        stored=con.execute("SELECT password_hash FROM members WHERE member_id=1").fetchone()[0]
        assert stored.startswith("pbkdf2_sha256$") and stored!="password123"
        assert con.execute("PRAGMA foreign_keys").fetchone()[0]==1
        with pytest.raises(Exception):
            con.execute("INSERT INTO book_copies(book_id,branch_id) VALUES(9999,1)")
        con.rollback()
        with pytest.raises(Exception):
            con.execute("INSERT INTO books(title,isbn) VALUES('Duplicate ISBN','ISBN001')")
        con.rollback()
        indexes={row[1] for row in con.execute("PRAGMA index_list('loans')")}
        assert "idx_loans_member" in indexes and "idx_one_active_loan_per_copy" in indexes
    finally:
        con.close()


def test_books_and_member_registration_conflicts(client):
    assert client.post("/members",json={"member_name":"Invalid","email":"not-an-email","password":"secure-pass"}).status_code==422
    assert client.get("/books").status_code==200
    assert client.get("/books/999").status_code==404
    librarian(client)
    added=client.post("/books",json={"title":"Unique title","isbn":"ISBN999"})
    assert added.status_code==201
    book_id=added.json()["book_id"]
    assert client.get(f"/books/{book_id}").json()["title"]=="Unique title"
    assert client.post("/books",json={"title":"Duplicate","isbn":"ISBN999"}).status_code==409
    created=client.post("/members",json={"member_name":"New Reader","email":"new@example.com","password":"secure-pass"})
    assert created.status_code==201 and "password" not in created.json()
    assert client.post("/members",json={"member_name":"Duplicate","email":"new@example.com","password":"secure-pass"}).status_code==409
    injection=client.post("/books",json={"title":"Quoted '; DROP TABLE books;--","isbn":"ISBNSQL"})
    assert injection.status_code==201 and client.get("/books").status_code==200


def test_member_registration_validation_hashing_login_and_dashboard_isolation(client):
    assert client.post("/members",json={}).status_code==422
    assert client.post("/members",json={"member_name":"Missing","email":"missing@example.com"}).status_code==422
    assert client.post("/members",json={"member_name":"Invalid","email":"reader@@example.com","password":"secure-pass"}).status_code==422
    assert client.post("/members",json={"member_name":"Short","email":"short@example.com","password":"short"}).status_code==422

    created=client.post("/members",json={"member_name":"New Reader","email":"new.reader@example.com","password":"secure-pass","role":"staff"})
    assert created.status_code==201 and "password_hash" not in created.json()
    assert client.post("/members",json={"member_name":"Duplicate","email":"new.reader@example.com","password":"secure-pass"}).status_code==409
    con=get_connection()
    try:
        record=con.execute("SELECT member_name,password_hash FROM members WHERE email=?",("new.reader@example.com",)).fetchone()
        assert record["member_name"]=="New Reader"
        assert record["password_hash"].startswith("pbkdf2_sha256$")
        assert record["password_hash"]!="secure-pass"
    finally:
        con.close()

    assert client.post("/auth/member/login",json={"email":"new.reader@example.com","password":"wrong-pass"}).status_code==401
    login=client.post("/auth/member/login",json={"email":"new.reader@example.com","password":"secure-pass"})
    assert login.status_code==200
    own={"Authorization":"Bearer "+login.json()["access_token"]}
    dashboard=client.get("/members/dashboard",headers=own)
    assert dashboard.status_code==200
    assert dashboard.json()["member"]["member_name"]=="New Reader"
    assert client.get("/loans/me",headers=own).json()==[]
    assert "role" not in created.json()


def test_member_registration_form_is_connected_to_member_sign_in(client):
    page=client.get("/")
    assert page.status_code==200
    for marker in ("id=\"open-member-register\"", "id=\"member-register-form\"", "name=\"member_name\"", "name=\"confirm_password\"", "Password and confirmation do not match", "Account created successfully. Please sign in."):
        assert marker in page.text or marker in client.get("/static/app.js").text


def test_librarian_reports_show_borrowed_and_overdue_data(client,monkeypatch):
    librarian(client)
    due=(real_date.today()+timedelta(days=30)).isoformat()
    loan=client.post("/loans/checkout",json={"member_id":1,"copy_id":1,"due_date":due}).json()["loan_id"]
    con=get_connection()
    try:
        con.execute("UPDATE loans SET checkout_date='2000-01-01',due_date='2000-01-01' WHERE loan_id=?",(loan,))
        con.commit()
    finally:
        con.close()
    overdue=client.get("/reports/overdue-loans").json()
    assert any(row["loan_id"]==loan for row in overdue)
    borrowed=client.get("/reports/most-borrowed-books").json()
    assert any(row["title"]=="Malgudi Days" and row["total_borrowed"]==1 for row in borrowed)


def test_book_authors_and_branch_copies_can_be_managed(client):
    librarian(client)
    created=client.post("/books",json={"title":"Shared Voices","isbn":"ISBN-MULTI-AUTHOR","authors":["Author A","Author B"]})
    assert created.status_code==201
    book_id=created.json()["book_id"]
    assert client.get(f"/books/{book_id}").json()["authors"]==["Author A","Author B"]
    copy=client.post(f"/books/{book_id}/copies",json={"branch_id":2})
    assert copy.status_code==201 and copy.json()["status"]=="available"
    details=client.get(f"/books/{book_id}").json()
    assert len(details["copies"])==1 and details["copies"][0]["branch_name"]=="City Branch"
    assert client.post(f"/books/{book_id}/copies",json={"branch_id":999}).status_code==404


def test_fine_payment_records_receipt_once_and_enforces_ownership(client,monkeypatch):
    librarian(client)
    FrozenDate.fixed_today=real_date(2025,5,20)
    monkeypatch.setattr("app.main.date",FrozenDate)
    loan=create_loan_due_on(client,"2025-05-15")
    client.post(f"/loans/{loan}/return")
    fine=client.get("/fines/me",headers=member_token(client)).json()[0]["fine_id"]
    paid=client.post(f"/fines/{fine}/pay",headers=member_token(client))
    assert paid.status_code==200
    assert paid.json()["payment_status"]=="paid"
    assert client.post(f"/fines/{fine}/pay",headers=member_token(client)).status_code==409
    con=get_connection()
    try:
        assert con.execute("SELECT is_paid FROM fines WHERE fine_id=?",(fine,)).fetchone()[0]==1
    finally: con.close()
