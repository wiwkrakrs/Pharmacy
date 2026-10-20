import os
import secrets
import sqlite3
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, session

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY') or secrets.token_hex(32)
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

DATABASE = 'database.db'
CLINIC_PHONE = '09815509921'
STAFF_USERNAME = '@Lindy123'
STAFF_PASSWORD = '@Lindy_1234'

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reference_no TEXT UNIQUE NOT NULL,
            patient_name TEXT NOT NULL,
            patient_phone TEXT NOT NULL,
            patient_age INTEGER,
            patient_address TEXT,
            patient_gender TEXT,
            marital_status TEXT,
            appointment_date TEXT NOT NULL,
            appointment_time TEXT NOT NULL,
            service TEXT NOT NULL,
            notes TEXT,
            status TEXT DEFAULT 'Pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    existing_columns = {
        row['name'] for row in cursor.execute('PRAGMA table_info(appointments)')
    }
    for column, column_type in (
        ('patient_age', 'INTEGER'),
        ('patient_address', 'TEXT'),
        ('patient_gender', 'TEXT'),
        ('marital_status', 'TEXT'),
        ('doctor_name', 'TEXT'),
    ):
        if column not in existing_columns:
            cursor.execute(f'ALTER TABLE appointments ADD COLUMN {column} {column_type}')
    conn.commit()
    conn.close()

def generate_ref():
    conn = get_db_connection()
    count = conn.cursor().execute('SELECT COUNT(*) FROM appointments').fetchone()[0]
    conn.close()
    return f"APT-{datetime.now().strftime('%Y%m%d')}-{count + 1001}"

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/doctors')
def doctors():
    return render_template('doctors.html')

@app.route('/book', methods=['GET', 'POST'])
def book():
    if request.method == 'POST':
        patient_name = request.form['patient_name']
        patient_phone = request.form['patient_phone']
        try:
            patient_age = int(request.form['patient_age'])
        except (KeyError, ValueError):
            flash('Please enter a valid age between 0 and 120.', 'error')
            return redirect(url_for('book'))
        if not 0 <= patient_age <= 120:
            flash('Please enter a valid age between 0 and 120.', 'error')
            return redirect(url_for('book'))
        patient_address = request.form.get('patient_address', '').strip()
        patient_gender = request.form.get('patient_gender', '').strip()
        marital_status = request.form.get('marital_status', '')
        if not patient_address or not patient_gender:
            flash('Please enter your address and gender.', 'error')
            return redirect(url_for('book'))
        if marital_status not in ('Single', 'Married', 'Widowed'):
            flash('Please select a valid marital status.', 'error')
            return redirect(url_for('book'))
        appointment_date = ''
        appointment_time = ''
        service = request.form['service']
        if service == 'Others:':
            other_service = request.form.get('other_service', '').strip()
            if not other_service:
                flash('Please specify the other service you need.', 'error')
                return redirect(url_for('book'))
            service = f'Others: {other_service}'
        notes = request.form.get('notes', '')

        ref_no = generate_ref()

        conn = get_db_connection()
        appointment_columns = [
            'reference_no', 'patient_name', 'patient_phone',
            'patient_age', 'patient_address', 'patient_gender', 'marital_status',
            'appointment_date', 'appointment_time', 'service', 'notes',
        ]
        appointment_values = [
            ref_no, patient_name, patient_phone,
            patient_age, patient_address, patient_gender, marital_status,
            appointment_date, appointment_time, service, notes,
        ]
        existing_columns = {
            row['name'] for row in conn.execute('PRAGMA table_info(appointments)')
        }
        if 'patient_email' in existing_columns:
            appointment_columns.insert(2, 'patient_email')
            appointment_values.insert(2, '')
        placeholders = ', '.join('?' for _ in appointment_values)
        conn.execute(
            f"INSERT INTO appointments ({', '.join(appointment_columns)}) "
            f"VALUES ({placeholders})",
            appointment_values,
        )
        conn.commit()
        conn.close()

        flash(f'Appointment requested successfully! Your Reference Code is {ref_no}', 'success')
        return redirect(url_for('status', ref=ref_no))

    return render_template('book.html')

@app.route('/status')
def status():
    ref = request.args.get('ref', '').strip()
    appointment = None

    if ref:
        conn = get_db_connection()
        appointment = conn.execute('SELECT * FROM appointments WHERE reference_no = ?', (ref,)).fetchone()
        conn.close()

        if not appointment:
            flash('No appointment found with that Reference Code.', 'error')

    return render_template(
        'status.html',
        appointment=appointment,
        ref=ref,
        clinic_phone=CLINIC_PHONE,
    )

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if not session.get('staff_logged_in'):
        if request.method == 'POST' and 'username' in request.form:
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '')

            if username == STAFF_USERNAME and password == STAFF_PASSWORD:
                session['staff_logged_in'] = True
                flash('Login successful.', 'success')
                return redirect(url_for('admin'))

            flash('Invalid username or password.', 'error')

        return render_template('admin.html', login_required=True)

    conn = get_db_connection()

    if request.method == 'POST':
        apt_id = request.form.get('appointment_id', '')
        new_status = request.form.get('status', '')
        if new_status == 'Remove':
            cursor = conn.execute('DELETE FROM appointments WHERE id = ?', (apt_id,))
            conn.commit()
            conn.close()
            if cursor.rowcount == 0:
                flash('Appointment not found.', 'error')
            else:
                flash('Appointment removed.', 'success')
            return redirect(url_for('admin'))

        if new_status not in ('Approved', 'Cancelled', 'Pending'):
            conn.close()
            flash('Choose a valid appointment action.', 'error')
            return redirect(url_for('admin'))

        appointment = conn.execute(
            'SELECT id FROM appointments WHERE id = ?',
            (apt_id,),
        ).fetchone()
        if not appointment:
            conn.close()
            flash('Appointment not found.', 'error')
            return redirect(url_for('admin'))

        if new_status == 'Approved':
            cursor = conn.execute(
                'UPDATE appointments SET status = ? WHERE id = ? AND status IS NOT ?',
                (new_status, apt_id, new_status),
            )
        else:
            cursor = conn.execute(
                'UPDATE appointments SET status = ? WHERE id = ? AND status IS NOT ?',
                (new_status, apt_id, new_status),
            )
        conn.commit()
        conn.close()

        if cursor.rowcount == 0:
            flash(f'Appointment is already {new_status.lower()}.', 'success')
        elif new_status == 'Approved':
            flash('Appointment approved.', 'success')
        elif new_status == 'Pending':
            flash('Appointment set to pending.', 'success')
        else:
            flash('Appointment cancelled.', 'success')
        return redirect(url_for('admin'))

    appointments = conn.execute('SELECT * FROM appointments ORDER BY created_at DESC').fetchall()
    conn.close()
    return render_template(
        'admin.html',
        appointments=appointments,
        appointment_count=len(appointments),
        login_required=False,
    )

@app.route('/logout')
def logout():
    session.pop('staff_logged_in', None)
    flash('You have been logged out.', 'success')
    return redirect(url_for('admin'))

if __name__ == '__main__':
    init_db()
    app.run(debug=os.environ.get('FLASK_DEBUG') == '1')