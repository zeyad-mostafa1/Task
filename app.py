import sqlite3
import ctypes
import logging
from flask import Flask, render_template, request, redirect, url_for, session, send_file
from werkzeug.security import generate_password_hash, check_password_hash
import csv
import io

app = Flask(__name__)
app.secret_key = 'supersecretkey'  # Replace with a secure key in production

# Load C++ shared library
lib = ctypes.CDLL('./studentlib.so')
lib.search_students.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
lib.search_students.restype = ctypes.c_int

# Configure logging
logging.basicConfig(filename='app.log', level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s')

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

# Parse C++ output into list of dictionaries
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
    buffer_size = 1024
    buffer = ctypes.create_string_buffer(buffer_size)
    db_path_c = db_path.encode('utf-8')
    search_name_c = search_name.encode('utf-8')
    logging.info(f"Searching for: {search_name}")
    result = lib.search_students(db_path_c, search_name_c, buffer, buffer_size)
    raw_output = buffer.value.decode('utf-8')
    logging.info(f"C++ search result: {raw_output}")
    if result == 0:
        parsed_results = parse_search_results(raw_output)
        logging.info(f"Parsed results: {parsed_results}")
        return parsed_results
    else:
        logging.error(f"Search failed: {raw_output}")
        return []

# Login required decorator
def login_required(f):
    def wrap(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    wrap.__name__ = f.__name__
    return wrap

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
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
            return redirect(url_for('students'))
        return 'Invalid credentials'
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('role', None)
    return redirect(url_for('login'))

@app.route('/students', methods=['GET'])
@login_required
def students():
    conn = sqlite3.connect('students.db')
    c = conn.cursor()
    c.execute('SELECT * FROM students')
    students = c.fetchall()
    conn.close()
    return render_template('students.html', students=students)

@app.route('/add', methods=['GET', 'POST'])
@login_required
def add_student():
    if session['role'] != 'admin':
        return 'Unauthorized', 403
    if request.method == 'POST':
        name = request.form['name']
        grade = int(request.form['grade'])
        course = request.form['course']
        if not name or grade < 0:
            logging.error(f'Invalid input: name={name}, grade={grade}, course={course}')
            return 'Invalid input', 400
        conn = sqlite3.connect('students.db')
        c = conn.cursor()
        c.execute('INSERT INTO students (name, grade, course) VALUES (?, ?, ?)', 
                  (name, grade, course))
        conn.commit()
        conn.close()
        logging.info(f'Student {name} added with grade={grade}, course={course}')
        return redirect(url_for('students'))
    return render_template('add_student.html')

@app.route('/update/<int:id>', methods=['GET', 'POST'])
@login_required
def update_student(id):
    if session['role'] != 'admin':
        return 'Unauthorized', 403
    conn = sqlite3.connect('students.db')
    c = conn.cursor()
    if request.method == 'POST':
        name = request.form['name']
        grade = int(request.form['grade'])
        course = request.form['course']
        c.execute('UPDATE students SET name = ?, grade = ?, course = ? WHERE id = ?', 
                  (name, grade, course, id))
        conn.commit()
        conn.close()
        logging.info(f'Student ID {id} updated')
        return redirect(url_for('students'))
    c.execute('SELECT * FROM students WHERE id = ?', (id,))
    student = c.fetchone()
    conn.close()
    return render_template('update_student.html', student=student)

@app.route('/delete/<int:id>')
@login_required
def delete_student(id):
    if session['role'] != 'admin':
        return 'Unauthorized', 403
    conn = sqlite3.connect('students.db')
    c = conn.cursor()
    c.execute('DELETE FROM students WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    logging.info(f'Student ID {id} deleted')
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
    c.execute('SELECT * FROM students')
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