from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_mail import Mail, Message
from config import Config
from datetime import datetime

app = Flask(__name__)
app.config.from_object(Config)

mail = Mail(app)

# Make helper available inside templates
app.jinja_env.globals['get_user_by_id'] = lambda uid: next((u for u in users if u['id'] == uid), None)

# ─── In-memory data stores ────────────────────────────────────────────────────
users = [
    # Pre-seeded admin account
    {
        'id': 1,
        'username': 'Admin',
        'email': 'admin@example.com',
        'password': 'admin123',
        'is_admin': True
    }
]

complaints = []

complaint_id_counter = 1
user_id_counter = 2  # starts at 2 because admin is 1


# ─── Helpers ──────────────────────────────────────────────────────────────────
def get_user_by_email(email):
    return next((u for u in users if u['email'] == email), None)

def get_user_by_id(user_id):
    return next((u for u in users if u['id'] == user_id), None)

def get_complaint_by_id(complaint_id):
    return next((c for c in complaints if c['id'] == complaint_id), None)

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login'))
        user = get_user_by_id(session['user_id'])
        if not user or not user.get('is_admin'):
            flash('Access denied. Admins only.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated


# ─── Auth Routes ──────────────────────────────────────────────────────────────
@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        global user_id_counter
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        if not username or not email or not password:
            flash('All fields are required.', 'danger')
            return render_template('register.html')

        if get_user_by_email(email):
            flash('Email already registered.', 'danger')
            return render_template('register.html')

        users.append({
            'id': user_id_counter,
            'username': username,
            'email': email,
            'password': password,
            'is_admin': False
        })
        user_id_counter += 1
        flash('Account created successfully! Please log in.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        user = get_user_by_email(email)
        if user and user['password'] == password:
            session['user_id'] = user['id']
            flash(f'Welcome back, {user["username"]}!', 'success')
            if user.get('is_admin'):
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('dashboard'))

        flash('Invalid email or password.', 'danger')

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))


# ─── User Routes ──────────────────────────────────────────────────────────────
@app.route('/dashboard')
@login_required
def dashboard():
    user = get_user_by_id(session['user_id'])
    if user.get('is_admin'):
        return redirect(url_for('admin_dashboard'))
    user_complaints = [c for c in complaints if c['user_id'] == user['id']]
    return render_template('dashboard.html', user=user, complaints=user_complaints)


@app.route('/submit', methods=['GET', 'POST'])
@login_required
def submit_complaint():
    global complaint_id_counter
    user = get_user_by_id(session['user_id'])

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()

        if not title or not description:
            flash('Both title and description are required.', 'danger')
            return render_template('submit_complaint.html', user=user)

        complaints.append({
            'id': complaint_id_counter,
            'user_id': user['id'],
            'username': user['username'],
            'user_email': user['email'],
            'title': title,
            'description': description,
            'status': 'Pending',
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M')
        })
        complaint_id_counter += 1
        flash('Complaint submitted successfully!', 'success')
        return redirect(url_for('complaint_status'))

    return render_template('submit_complaint.html', user=user)


@app.route('/status')
@login_required
def complaint_status():
    user = get_user_by_id(session['user_id'])
    user_complaints = [c for c in complaints if c['user_id'] == user['id']]
    return render_template('complaint_status.html', user=user, complaints=user_complaints)


# ─── Admin Routes ─────────────────────────────────────────────────────────────
@app.route('/admin')
@admin_required
def admin_dashboard():
    user = get_user_by_id(session['user_id'])
    stats = {
        'total': len(complaints),
        'pending': sum(1 for c in complaints if c['status'] == 'Pending'),
        'in_progress': sum(1 for c in complaints if c['status'] == 'In Progress'),
        'resolved': sum(1 for c in complaints if c['status'] == 'Resolved')
    }
    return render_template('admin_dashboard.html', user=user, complaints=complaints, stats=stats)


@app.route('/admin/update/<int:complaint_id>', methods=['POST'])
@admin_required
def update_complaint(complaint_id):
    complaint = get_complaint_by_id(complaint_id)
    if not complaint:
        flash('Complaint not found.', 'danger')
        return redirect(url_for('admin_dashboard'))

    new_status = request.form.get('status')
    valid_statuses = ['Pending', 'In Progress', 'Resolved']
    if new_status not in valid_statuses:
        flash('Invalid status.', 'danger')
        return redirect(url_for('admin_dashboard'))

    complaint['status'] = new_status
    complaint['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M')

    # Send email notification
    try:
        msg = Message(
            subject='Complaint Status Updated',
            recipients=[complaint['user_email']],
            body=(
                f"Dear {complaint['username']},\n\n"
                f"Your complaint \"{complaint['title']}\" has been updated.\n\n"
                f"New Status: {new_status}\n\n"
                f"Thank you."
            )
        )
        mail.send(msg)
        flash(f'Status updated to "{new_status}" and email notification sent.', 'success')
    except Exception:
        flash(f'Status updated to "{new_status}". (Email notification could not be sent — check SMTP config.)', 'warning')

    return redirect(url_for('admin_dashboard'))


# ─── Run ──────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    app.run(debug=True)
