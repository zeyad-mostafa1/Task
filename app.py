import ctypes
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session, send_file, flash
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import csv
import io
import logging

app = Flask(__name__)
app.secret_key = 'supersecretkey'
logging.basicConfig(filename='app.log', level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s')

# Load C++ shared library
lib = ctypes.CDLL('./studentlib.so')
lib.search_students.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
lib.search_students.restype = ctypes.c_char_p
lib.free_result.argtypes = [ctypes.c_char_p]
lib.free_result.restype = None

# Initialize database
def init_db():
    conn = sqlite3.connect('students.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS students 
                 (id INTEGER PRIMARY KEY, name TEXT, grade INTEGER, course TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (id INTEGER PRIMARY KEY, username TEXT, password TEXT, role TEXT)''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_name ON students (name)')
    c.execute('INSERT OR IGNORE INTO users (username, password, role) VALUES (?, ?, ?)',
              ('admin', generate_password_hash('admin123'), 'admin'))
    conn.commit()
    conn.close()

# Parse search results
def parse_search_results(raw_output):
    results = []
    current_student = {}
    lines = raw_output.split('\n') if raw_output else []
    for line in lines:
        if line == '---':
            if current_student:
                results.append(current_student)
                current_student = {}
        elif ': ' in line:
            key, value = line.split(': ', 1)
            if key == 'id':
                current_student[key] = int(value) if value != 'NULL' else None
            elif key == 'grade':
                current_student[key] = int(value) if value != 'NULL' else None
            else:
                current_student[key] = value if value != 'NULL' else None
    if current_student:
        results.append(current_student)
    return results

# Search function
def search_students(db_path, search_name):
    db_path_c = db_path.encode('utf-8')
    search_name_c = search_name.encode('utf-8')
    logging.info(f"Searching for: {search_name}")
    result_pointer = lib.search_students(db_path_c, search_name_c)
    if not result_pointer:
        logging.error("Search failed: NULL pointer returned")
        flash('Search failed: No results or error occurred.', 'danger')
        return []
    raw_output = result_pointer.decode('utf-8')
    logging.info(f"C++ search result: {raw_output}")
    parsed_results = parse_search_results(raw_output)
    logging.info(f"Parsed results: {parsed_results}")
    lib.free_result(result_pointer)
    return parsed_results

# Login required decorator
def login_required(f):
    @wraps(f)
    def wrap(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in first.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return wrap

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('students'))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = sqlite3.connect('students.db')
        c = conn.cursor()
        c.execute('SELECT * FROM users WHERE username = ?', (username,))
        user = c.fetchone()
        conn.close()
        if user and check_password_hash(user[2], password):
            session['user_id'] = user[0]
            session['role'] = user[3]
            logging.info(f'User {username} logged in')
            flash('Login successful!', 'success')
            return redirect(url_for('students'))
        flash('Invalid credentials', 'danger')
        return render_template('login.html')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    session.pop('user_id', None)
    session.pop('role', None)
    flash('Logged out successfully.', 'success')
    return redirect(url_for('login'))

@app.route('/students', methods=['GET'])
@login_required
def students():
    conn = sqlite3.connect('students.db')
    c = conn.cursor()
    c.execute('SELECT id, name, grade, course FROM students')
    students = c.fetchall()  
    conn.close()
    return render_template('students.html', students=students)

@app.route('/add', methods=['GET', 'POST'])
@login_required
def add_student():
    if session['role'] != 'admin':
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('students'))
    if request.method == 'POST':
        name = request.form['name']
        grade = request.form['grade']
        course = request.form['course']
        try:
            grade = int(grade) if grade else None
            if not name:
                raise ValueError("Name is required")
            conn = sqlite3.connect('students.db')
            c = conn.cursor()
            c.execute('INSERT INTO students (name, grade, course) VALUES (?, ?, ?)', 
                      (name, grade, course))
            conn.commit()
            conn.close()
            logging.info(f'Student {name} added with grade={grade}, course={course}')
            flash('Student added successfully!', 'success')
            return redirect(url_for('students'))
        except ValueError as e:
            flash(f'Invalid input: {str(e)}', 'danger')
        except Exception as e:
            flash(f'Error adding student: {str(e)}', 'danger')
    return render_template('add_student.html')

@app.route('/update/<int:id>', methods=['GET', 'POST'])
@login_required
def update_student(id):
    if session['role'] != 'admin':
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('students'))
    conn = sqlite3.connect('students.db')
    c = conn.cursor()
    if request.method == 'POST':
        name = request.form['name']
        grade = request.form['grade']
        course = request.form['course']
        try:
            grade = int(grade) if grade else None
            if not name:
                raise ValueError("Name is required")
            c.execute('UPDATE students SET name = ?, grade = ?, course = ? WHERE id = ?', 
                      (name, grade, course, id))
            conn.commit()
            flash('Student updated successfully!', 'success')
            return redirect(url_for('students'))
        except ValueError as e:
            flash(f'Invalid input: {str(e)}', 'danger')
        except Exception as e:
            flash(f'Error updating student: {str(e)}', 'danger')
        finally:
            conn.close()
    c.execute('SELECT id, name, grade, course FROM students WHERE id = ?', (id,))
    student = c.fetchone()  # Return as tuple
    conn.close()
    if student:
        return render_template('update_student.html', student=student)
    flash('Student not found.', 'danger')
    return redirect(url_for('students'))

@app.route('/delete/<int:id>')
@login_required
def delete_student(id):
    if session['role'] != 'admin':
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('students'))
    try:
        conn = sqlite3.connect('students.db')
        c = conn.cursor()
        c.execute('DELETE FROM students WHERE id = ?', (id,))
        conn.commit()
        conn.close()
        logging.info(f'Student ID {id} deleted')
        flash('Student deleted successfully!', 'success')
    except Exception as e:
        flash(f'Error deleting student: {str(e)}', 'danger')
    return redirect(url_for('students'))

@app.route('/search', methods=['GET', 'POST'])
@login_required
def search():
    if request.method == 'POST':
        name = request.form['name']
        logging.info(f"Search request for name: {name}")
        results = search_students('students.db', name)
        logging.info(f"Search results: {results}")
        return render_template('search.html', results=results)
    return render_template('search.html', results=[])

@app.route('/report')
@login_required
def report():
    conn = sqlite3.connect('students.db')
    c = conn.cursor()
    c.execute('SELECT id, name, grade, course FROM students')
    students = c.fetchall()
    conn.close()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Name', 'Grade', 'Course'])
    writer.writerows(students)
    output.seek(0)
    return send_file(io.BytesIO(output.getvalue().encode('utf-8')), 
                     mimetype='text/csv', as_attachment=True, 
                     download_name='students_report.csv')

if __name__ == '__main__':
    init_db()
    app.run(debug=True)