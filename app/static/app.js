const grid = document.querySelector('#book-grid');
const searchInput = document.querySelector('#search-input');
const resultsLabel = document.querySelector('#results-label');
const formMessage = document.querySelector('#form-message');
let books = [];
let dashboardData = null;
let memberAccessToken = '';
const palette = ['#718d78', '#bd886c', '#7b789b', '#c0a15e', '#678b91', '#ad7580', '#72866a'];

function escapeHTML(value = '') {
  return String(value).replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
}
function renderBooks() {
  const query = searchInput.value.trim().toLowerCase();
  const filtered = books.filter(book => [book.title, book.authors, book.isbn, book.publisher].join(' ').toLowerCase().includes(query));
  resultsLabel.textContent = `${filtered.length} ${filtered.length === 1 ? 'title' : 'titles'}`;
  if (!filtered.length) {
    grid.innerHTML = `<div class="empty-state">${books.length ? 'No books match your search. Try another title or author.' : 'The catalogue is empty right now.'}</div>`;
    return;
  }
  grid.innerHTML = filtered.map((book, index) => {
    const available = book.available_copies;
    const availability = available == null ? '' : `<span class="book-tag">${available} available</span>`;
    const author = book.authors || 'Author details unavailable';
    return `<article class="book-card"><div class="cover" style="background:${palette[index % palette.length]}"><span class="cover-mark">${escapeHTML((book.title || 'L').trim().charAt(0).toUpperCase())}</span></div><div class="book-info"><h3 class="book-title">${escapeHTML(book.title)}</h3><div class="book-author">${escapeHTML(author)}</div><div class="book-meta">${book.publication_year ? escapeHTML(book.publication_year) + ' · ' : ''}ISBN ${escapeHTML(book.isbn)}</div>${availability}</div></article>`;
  }).join('');
}
function formatRupees(amount) {
  return `₹${Number(amount || 0).toFixed(2)}`;
}
async function loadBooks() {
  resultsLabel.textContent = 'Loading collection…';
  try {
    const response = await fetch('/books');
    if (!response.ok) throw new Error('Could not load catalogue');
    books = await response.json();
    renderBooks();
    document.querySelector('#book-count').textContent = String(books.length).padStart(2, '0');
    const total = books.reduce((sum, book) => sum + (book.available_copies || 0), 0);
    document.querySelector('#available-count').textContent = total ? `${total} copies available` : 'Ask us at the desk';
  } catch (error) {
    resultsLabel.textContent = 'Connection unavailable';
    grid.innerHTML = '<div class="empty-state">Could not connect to the library API. Please refresh the page.</div>';
  }
}
searchInput.addEventListener('input', renderBooks);
document.querySelector('#refresh-button').addEventListener('click', loadBooks);
const dialog = document.querySelector('#login-dialog');
const memberDialog = document.querySelector('#member-login-dialog');
const memberRegisterDialog = document.querySelector('#member-register-dialog');
document.querySelector('#session-chip').addEventListener('click', () => dialog.showModal());
const navItems = [...document.querySelectorAll('.nav-item')];
const sectionNames = {dashboard:'Staff dashboard', catalogue:'Catalogue', manage:'Add a book', account:'Librarian access', 'member-dashboard':'Member dashboard'};
let librarianSignedIn = false;
function updateActiveNavigation() {
  const section = location.hash.slice(1) || 'catalogue';
  navItems.forEach(item => item.classList.toggle('active', item.hash === `#${section}`));
  document.querySelector('#current-section').textContent = sectionNames[section] || sectionNames.catalogue;
}
navItems.forEach(item => item.addEventListener('click', () => {
  if ((item.hash === '#account' || item.hash === '#dashboard') && !librarianSignedIn && !dialog.open) dialog.showModal();
  if (item.hash === '#account' && librarianSignedIn && !dialog.open) dialog.showModal();
  if (item.hash === '#member-dashboard' && !memberAccessToken && !memberDialog.open) memberDialog.showModal();
}));
document.querySelector('#account-signin').addEventListener('click', () => dialog.showModal());
window.addEventListener('hashchange', updateActiveNavigation);
updateActiveNavigation();
document.querySelector('#close-dialog').addEventListener('click', () => dialog.close());
dialog.addEventListener('click', event => { if (event.target === dialog) dialog.close(); });
document.querySelector('#close-member-dialog').addEventListener('click', () => memberDialog.close());
memberDialog.addEventListener('click', event => { if (event.target === memberDialog) memberDialog.close(); });

function localDateString(date) {
  return `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`;
}
const dueInput = document.querySelector('#checkout-due');
const checkoutDateInput = document.querySelector('#checkout-date');
const today = new Date();
const todayValue = localDateString(today);
const yesterday = new Date(today);
yesterday.setDate(yesterday.getDate() - 1);
checkoutDateInput.min = '2026-10-10';
checkoutDateInput.value = todayValue;
dueInput.min = checkoutDateInput.value;
const defaultDueDate = new Date(today);
defaultDueDate.setDate(defaultDueDate.getDate() + 14);
dueInput.value = localDateString(defaultDueDate);
checkoutDateInput.addEventListener('change', () => { dueInput.min = checkoutDateInput.value; });

function renderDashboard(data) {
  dashboardData = data;
  librarianSignedIn = true;
  document.querySelector('#staff-name').textContent = data.staff.staff_name;
  document.querySelector('#session-label').textContent = data.staff.staff_name;
  document.querySelector('#dash-available').textContent = data.summary.available_copies;
  document.querySelector('#dash-members').textContent = data.summary.total_members;
  document.querySelector('#dash-overdue').textContent = data.summary.overdue_loans;
  document.querySelector('#dash-books').textContent = data.summary.total_books;
  document.querySelector('#dash-borrowed').textContent = data.summary.currently_borrowed;
  document.querySelector('#dash-fines').textContent = formatRupees(data.summary.outstanding_fines);
  const memberSelect = document.querySelector('#checkout-member');
  const selectedMember = memberSelect.value;
  memberSelect.innerHTML = '<option value="">Select a member</option>' + data.members.map(member => `<option value="${member.member_id}">${escapeHTML(member.member_name)} · ${escapeHTML(member.email)}</option>`).join('');
  if (data.members.some(member => String(member.member_id) === selectedMember)) memberSelect.value = selectedMember;
  const copySelect = document.querySelector('#checkout-copy');
  const selectedCopy = copySelect.value;
  copySelect.innerHTML = '<option value="">Select a copy</option>' + data.available_copies.map(copy => `<option value="${copy.copy_id}">${escapeHTML(copy.title)} · ${escapeHTML(copy.branch_name)} · #${copy.copy_id}</option>`).join('');
  if (data.available_copies.some(copy => String(copy.copy_id) === selectedCopy)) copySelect.value = selectedCopy;
  document.querySelector('#active-loan-count').textContent = `${data.active_loans.length} active`;
  document.querySelector('#active-loans-body').innerHTML = data.active_loans.length ? data.active_loans.map(loan => `<tr><td>#${loan.loan_id}</td><td>${escapeHTML(loan.member_name)}</td><td>${escapeHTML(loan.title)}</td><td>${escapeHTML(loan.branch_name)}</td><td>${escapeHTML(loan.due_date)}</td><td><button class="table-action" data-return-loan="${loan.loan_id}">Return</button></td></tr>`).join('') : '<tr><td class="table-empty" colspan="6">No active loans right now.</td></tr>';
  document.querySelector('#loan-records-body').innerHTML = data.loan_records.length ? data.loan_records.map(loan => `<tr><td>#${loan.loan_id}</td><td>#${loan.member_id}</td><td>${escapeHTML(loan.member_name)}</td><td>${escapeHTML(loan.title)}</td><td>${escapeHTML(loan.checkout_date)}</td><td>${escapeHTML(loan.due_date)}</td><td>${escapeHTML(loan.return_date || '—')}</td><td><span class="loan-status ${loan.status === 'active' ? 'status-active' : 'status-returned'}">${escapeHTML(loan.status)}</span></td><td>${formatRupees(loan.fine_amount)}</td></tr>`).join('') : '<tr><td class="table-empty" colspan="9">No borrowing records yet.</td></tr>';
  document.querySelector('#overdue-loans-body').innerHTML = data.overdue_loans.length ? data.overdue_loans.map(loan => `<tr><td>#${loan.loan_id}</td><td>${escapeHTML(loan.member_name)}</td><td>${escapeHTML(loan.title)}</td><td>${escapeHTML(loan.branch_name)}</td><td>${escapeHTML(loan.due_date)}</td><td><span class="overdue-badge">${loan.overdue_days} days</span></td><td>${formatRupees(loan.fine_amount)}</td></tr>`).join('') : '<tr><td class="table-empty" colspan="7">No overdue loans. Everything is up to date.</td></tr>';
  document.querySelector('#most-borrowed-body').innerHTML = data.most_borrowed.length ? data.most_borrowed.map(book => `<tr><td>${escapeHTML(book.title)}</td><td>${book.total_borrowed}</td></tr>`).join('') : '<tr><td class="table-empty" colspan="2">No checkout history yet.</td></tr>';
  renderLoanSearch();
}
function renderLoanSearch() {
  if (!dashboardData) return;
  const query = document.querySelector('#loan-search-input').value.trim().toLowerCase();
  const results = document.querySelector('#loan-search-results');
  if (!query) {
    results.innerHTML = '<tr><td class="table-empty" colspan="5">Search active loans to find overdue books.</td></tr>';
    return;
  }
  const overdueById = new Map(dashboardData.overdue_loans.map(loan => [loan.loan_id, loan]));
  const matches = dashboardData.active_loans.filter(loan => [loan.member_name,loan.member_id,loan.loan_id,loan.title].some(value => String(value).toLowerCase().includes(query)));
  if (!matches.length) {
    results.innerHTML = '<tr><td class="table-empty" colspan="5">No matching active loans found.</td></tr>';
    return;
  }
  results.innerHTML = matches.map(loan => {
    const overdue = overdueById.get(loan.loan_id);
    const status = overdue ? `<span class="overdue-badge">Overdue · ${overdue.overdue_days} days · ${formatRupees(overdue.fine_amount)}</span>` : '<span class="not-overdue-badge">Not overdue · 0 days</span>';
    return `<tr><td>${escapeHTML(loan.member_name)} <span class="member-id">#${loan.member_id}</span></td><td>${escapeHTML(loan.title)}</td><td>#${loan.loan_id}</td><td>${escapeHTML(loan.due_date)}</td><td>${status}</td></tr>`;
  }).join('');
}
document.querySelector('#loan-search-input').addEventListener('input', renderLoanSearch);
async function loadDashboard({silent = false} = {}) {
  try {
    const response = await fetch('/librarian/dashboard');
    if (!response.ok) {
      if (response.status === 401) librarianSignedIn = false;
      if (!silent) throw new Error(response.status === 401 ? 'Your librarian session has expired. Please sign in again.' : 'Could not load the staff dashboard.');
      return false;
    }
    renderDashboard(await response.json());
    return true;
  } catch (error) {
    if (!silent) showActionMessage('checkout-message', error.message, true);
    return false;
  }
}
function showActionMessage(id, text, isError = false) {
  const message = document.getElementById(id);
  message.textContent = text;
  message.className = `form-message${isError ? ' error' : ''}`;
}

function renderMemberDashboard(data) {
  document.querySelector('#member-name').textContent = data.member.member_name;
  document.querySelector('#session-label').textContent = `Member: ${data.member.member_name}`;
  document.querySelector('#member-borrowed-count').textContent = data.summary.currently_borrowed;
  document.querySelector('#member-overdue-count').textContent = data.summary.overdue_books;
  document.querySelector('#member-outstanding-fines').textContent = formatRupees(data.summary.outstanding_fines);
  document.querySelector('#member-loans-body').innerHTML = data.loans.length ? data.loans.map(loan => {
    const overdue = !loan.return_date && loan.overdue_days > 0;
    const status = overdue ? '<span class="overdue-badge">Overdue</span>' : `<span class="loan-status ${loan.status === 'active' ? 'status-active' : 'status-returned'}">${escapeHTML(loan.status)}</span>`;
    return `<tr class="${overdue ? 'overdue-row' : ''}"><td>${escapeHTML(loan.title)}</td><td>#${loan.loan_id}</td><td>${escapeHTML(loan.checkout_date)}</td><td>${escapeHTML(loan.due_date)}</td><td>${escapeHTML(loan.return_date || '—')}</td><td>${status}</td><td>${loan.overdue_days}</td><td>${formatRupees(loan.fine_amount)}</td></tr>`;
  }).join('') : '<tr><td class="table-empty" colspan="8">You have no borrowing records yet.</td></tr>';
  document.querySelector('#member-fines-body').innerHTML = data.fines.length ? data.fines.map(fine => `<tr><td>#${fine.loan_id}</td><td>${escapeHTML(fine.title)}</td><td>${escapeHTML(fine.due_date)}</td><td>${fine.overdue_days}</td><td>${formatRupees(fine.amount)}</td><td><span class="loan-status ${fine.is_paid ? 'status-returned' : 'status-active'}">${fine.is_paid ? 'Paid' : 'Outstanding'}</span></td><td>${fine.is_paid ? '' : `<button class="table-action" data-pay-fine="${fine.fine_id}">Pay fine</button>`}</td></tr>`).join('') : '<tr><td class="table-empty" colspan="7">No fine records.</td></tr>';
  const outstandingRows = data.fines.filter(fine => !fine.is_paid);
  const message = data.summary.outstanding_fines > 0 && outstandingRows.length === 0
    ? `You have ${formatRupees(data.summary.outstanding_fines)} in current overdue charges. Fines can be paid after the book is returned.`
    : data.summary.outstanding_fines > 0
      ? `Outstanding total: ${formatRupees(data.summary.outstanding_fines)}.`
      : 'No outstanding fines.';
  showActionMessage('member-fines-message', message);
}

async function loadMemberDashboard() {
  if (!memberAccessToken) return false;
  try {
    const response = await fetch('/members/dashboard', {headers:{'Authorization':`Bearer ${memberAccessToken}`}});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error?.message || 'Could not load your member dashboard.');
    renderMemberDashboard(result);
    return true;
  } catch (error) {
    if (/session|token|authentication/i.test(error.message)) {
      memberAccessToken = '';
      document.querySelector('#member-dashboard').hidden = true;
      document.querySelector('#session-label').textContent = 'Member sign in';
    }
    showActionMessage('member-login-message', error.message, true);
    return false;
  }
}

memberDialog.addEventListener('close', () => {
  if (!memberAccessToken && location.hash === '#member-dashboard') location.hash = 'catalogue';
});
document.querySelector('#member-login-form').addEventListener('submit', async event => {
  event.preventDefault();
  const message = document.querySelector('#member-login-message');
  const credentials = Object.fromEntries(new FormData(event.currentTarget));
  message.textContent = 'Signing in…';
  message.className = 'form-message';
  try {
    const response = await fetch('/auth/member/login', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(credentials)});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error?.message || 'Sign in failed. Check your email and password.');
    memberAccessToken = result.access_token;
    if (!await loadMemberDashboard()) throw new Error('Signed in, but your member dashboard could not be loaded. Please try again.');
    document.querySelector('#member-dashboard').hidden = false;
    document.querySelector('#dashboard').hidden = true;
    dialog.close();
    memberDialog.close();
    location.hash = 'member-dashboard';
    document.querySelector('#member-dashboard').scrollIntoView({behavior:'smooth',block:'start'});
  } catch (error) {
    memberAccessToken = '';
    message.textContent = error.message;
    message.className = 'form-message error';
  }
});

document.querySelector('#open-member-register').addEventListener('click', () => {
  document.querySelector('#member-login-message').textContent = '';
  memberDialog.close();
  memberRegisterDialog.showModal();
});
document.querySelector('#close-member-register').addEventListener('click', () => memberRegisterDialog.close());
document.querySelector('#back-to-member-login').addEventListener('click', () => {
  memberRegisterDialog.close();
  memberDialog.showModal();
});
document.querySelector('#member-register-form').addEventListener('submit', async event => {
  event.preventDefault();
  const form = event.currentTarget;
  const fields = Object.fromEntries(new FormData(form));
  const message = document.querySelector('#member-register-message');
  message.className = 'form-message';
  const email = fields.email.trim();
  if (!fields.member_name.trim() || !email || !fields.password || !fields.confirm_password) {
    message.textContent = 'Please complete every field.';
    message.className = 'form-message error';
    return;
  }
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
    message.textContent = 'Enter a valid email address.';
    message.className = 'form-message error';
    return;
  }
  if (fields.password.length < 8) {
    message.textContent = 'Password must be at least 8 characters.';
    message.className = 'form-message error';
    return;
  }
  if (fields.password !== fields.confirm_password) {
    message.textContent = 'Password and confirmation do not match.';
    message.className = 'form-message error';
    return;
  }
  message.textContent = 'Creating your account…';
  try {
    const response = await fetch('/members', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({member_name:fields.member_name.trim(),email,password:fields.password})});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error?.message || 'Could not create your account.');
    form.reset();
    memberRegisterDialog.close();
    document.querySelector('#member-login-form [name="email"]').value = email;
    document.querySelector('#member-login-form [name="password"]').value = '';
    const loginMessage = document.querySelector('#member-login-message');
    loginMessage.textContent = 'Account created successfully. Please sign in.';
    loginMessage.className = 'form-message';
    memberDialog.showModal();
  } catch (error) {
    message.textContent = error.message;
    message.className = 'form-message error';
  }
});

document.querySelector('#member-fines-body').addEventListener('click', async event => {
  const button = event.target.closest('[data-pay-fine]');
  if (!button || !memberAccessToken) return;
  button.disabled = true;
  try {
    const response = await fetch(`/fines/${button.dataset.payFine}/pay`, {method:'POST',headers:{'Authorization':`Bearer ${memberAccessToken}`}});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error?.message || 'Could not pay this fine.');
    await loadMemberDashboard();
    showActionMessage('member-fines-message', 'Fine payment recorded.');
  } catch (error) {
    showActionMessage('member-fines-message', error.message, true);
    button.disabled = false;
  }
});
document.querySelector('#member-logout-button').addEventListener('click', () => {
  memberAccessToken = '';
  document.querySelector('#member-dashboard').hidden = true;
  document.querySelector('#member-name').textContent = '';
  document.querySelector('#member-loans-body').innerHTML = '';
  document.querySelector('#member-fines-body').innerHTML = '';
  document.querySelector('#session-label').textContent = 'Member sign in';
  memberDialog.showModal();
});

document.querySelector('#logout-button').addEventListener('click', async () => {
  try {
    const response = await fetch('/auth/librarian/logout', {method:'POST'});
    if (!response.ok) throw new Error('Could not log out. Please try again.');
    librarianSignedIn = false;
    document.querySelector('#dashboard').hidden = true;
    document.querySelector('#session-label').textContent = 'Staff sign in';
    location.hash = 'catalogue';
    window.scrollTo({top:0, behavior:'smooth'});
    dialog.showModal();
  } catch (error) { showActionMessage('checkout-message', error.message, true); }
});

document.querySelector('#checkout-form').addEventListener('submit', async event => {
  event.preventDefault();
  const memberId = Number(document.querySelector('#checkout-member').value);
  const copyId = Number(document.querySelector('#checkout-copy').value);
  const checkoutDate = checkoutDateInput.value;
  const dueDate = dueInput.value;
  const button = event.currentTarget.querySelector('button[type="submit"]');
  button.disabled = true;
  try {
    const response = await fetch('/loans/checkout', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({member_id:memberId,copy_id:copyId,checkout_date:checkoutDate,due_date:dueDate})});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error?.message || 'Could not check out this copy.');
    showActionMessage('checkout-message', `Checkout complete. Loan #${result.loan_id} is due ${result.due_date}.`);
    await loadDashboard(); await loadBooks();
  } catch (error) { showActionMessage('checkout-message', error.message, true); }
  finally { button.disabled = false; }
});
document.querySelector('#active-loans-body').addEventListener('click', async event => {
  const button = event.target.closest('[data-return-loan]');
  if (!button) return;
  button.disabled = true;
  try {
    const response = await fetch(`/loans/${button.dataset.returnLoan}/return`, {method:'POST'});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error?.message || 'Could not return this loan.');
    showActionMessage('checkout-message', `Book returned. Fine: ${result.fine_amount}.`);
    await loadDashboard(); await loadBooks();
  } catch (error) { showActionMessage('checkout-message', error.message, true); button.disabled = false; }
});

document.querySelector('#login-form').addEventListener('submit', async event => {
  event.preventDefault();
  const message = document.querySelector('#login-message');
  const data = Object.fromEntries(new FormData(event.currentTarget));
  message.textContent = 'Signing in…'; message.className = 'form-message';
  try {
    const response = await fetch('/auth/librarian/login', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error?.message || 'Sign in failed');
    memberAccessToken = '';
    document.querySelector('#member-dashboard').hidden = true;
    const dashboardLoaded = await loadDashboard();
    if (!dashboardLoaded) throw new Error('Signed in, but could not load the staff dashboard. Please try again.');
    document.querySelector('#dashboard').hidden = false;
    message.textContent = 'Signed in successfully.';
    dialog.close();
    location.hash = 'dashboard';
    document.querySelector('#dashboard').scrollIntoView({behavior:'smooth', block:'start'});
  } catch (error) { message.textContent = error.message; message.className = 'form-message error'; }
});

document.querySelector('#book-form').addEventListener('submit', async event => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector('button[type="submit"]');
  const values = Object.fromEntries(new FormData(form));
  const payload = {title:values.title.trim(), isbn:values.isbn.trim(), authors:values.authors.split(',').map(author => author.trim()).filter(Boolean), publisher:values.publisher.trim() || null, publication_year:values.publication_year ? Number(values.publication_year) : null};
  button.disabled = true; formMessage.textContent = 'Adding book…'; formMessage.className = 'form-message';
  try {
    const response = await fetch('/books', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error?.message || (response.status === 401 ? 'Please sign in as a librarian first.' : 'Could not add book.'));
    form.reset(); formMessage.textContent = 'Book added to the catalogue.'; await loadBooks();
  } catch (error) { formMessage.textContent = error.message; formMessage.className = 'form-message error'; }
  finally { button.disabled = false; }
});
loadBooks();
loadDashboard({silent:true}).then(loaded => {
  if (loaded) {
    document.querySelector('#dashboard').hidden = false;
    location.hash = 'dashboard';
  }
});
