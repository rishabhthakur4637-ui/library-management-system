-- Most borrowed books
SELECT b.book_id,b.title,COUNT(l.loan_id) AS total_borrowed
FROM books b JOIN book_copies c ON c.book_id=b.book_id
JOIN loans l ON l.copy_id=c.copy_id
GROUP BY b.book_id,b.title ORDER BY total_borrowed DESC,b.title;

-- Overdue active loans, evaluated against today's local date
SELECT l.loan_id,m.member_name,b.title,l.due_date
FROM loans l JOIN members m ON m.member_id=l.member_id
JOIN book_copies c ON c.copy_id=l.copy_id JOIN books b ON b.book_id=c.book_id
WHERE l.return_date IS NULL AND l.due_date < date('now','localtime');

-- Loan history for the supplied member_id
SELECT l.loan_id,b.title,l.checkout_date,l.due_date,l.return_date,l.status
FROM loans l JOIN book_copies c ON c.copy_id=l.copy_id JOIN books b ON b.book_id=c.book_id
WHERE l.member_id=? ORDER BY l.checkout_date DESC;


