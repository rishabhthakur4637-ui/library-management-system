INSERT OR IGNORE INTO branches VALUES
 (1,'Main Branch','Solan'),(2,'City Branch','Chandigarh'),(3,'North Branch','Mohali');
INSERT OR IGNORE INTO books(book_id,title,isbn,publication_year,publisher) VALUES
 (1,'Malgudi Days','ISBN001',1943,'Indian Thought Publications'),
 (2,'Five Point Someone','ISBN002',2004,'Rupa'),
 (3,'Harry Potter and the Philosopher''s Stone','ISBN003',1997,'Bloomsbury'),
 (4,'Animal Farm','ISBN004',1945,'Secker & Warburg');
INSERT OR IGNORE INTO authors VALUES
 (1,'R. K. Narayan'),(2,'Chetan Bhagat'),(3,'J. K. Rowling'),(4,'George Orwell');
INSERT OR IGNORE INTO book_authors VALUES (1,1),(2,2),(3,3),(4,4);
INSERT OR IGNORE INTO book_copies(copy_id,book_id,branch_id,status) VALUES
 (1,1,1,'available'),(2,1,2,'available'),(3,2,1,'available'),(4,2,3,'available'),
 (5,3,2,'available'),(6,3,3,'available'),(7,4,1,'available'),(8,4,2,'available'),(9,4,3,'available');
INSERT OR IGNORE INTO members(member_id,member_name,email,password_hash) VALUES
 (1,'Aman Sharma','aman@example.com','seed-password-pending-hash'),
 (2,'Priya Verma','priya@example.com','seed-password-pending-hash'),
 (3,'Rahul Kumar','rahul@example.com','seed-password-pending-hash');
INSERT OR IGNORE INTO staff(staff_id,staff_name,email,password_hash,branch_id) VALUES
 (1,'Librarian One','librarian1@example.com','seed-password-pending-hash',1),
 (2,'Librarian Two','librarian2@example.com','seed-password-pending-hash',2),
 (3,'Librarian Three','librarian3@example.com','seed-password-pending-hash',3);
-- Historical returned loan with an unpaid fine, plus one active overdue loan.
INSERT OR IGNORE INTO loans(loan_id,copy_id,member_id,staff_id,checkout_date,due_date,return_date,status) VALUES
 (1,8,3,2,'2025-01-01','2025-01-10','2025-01-12','returned'),
 (2,9,3,3,'2025-03-01','2025-03-15',NULL,'active');
INSERT OR IGNORE INTO fines(fine_id,loan_id,overdue_days,amount,is_paid) VALUES
 (1,1,2,20,0);
UPDATE book_copies SET status=CASE WHEN EXISTS (SELECT 1 FROM loans WHERE copy_id=9 AND return_date IS NULL) THEN 'loaned' ELSE 'available' END WHERE copy_id=9;
