from flask import Flask, render_template, request, redirect, url_for, flash, session
import pyodbc
import uuid
import hashlib
import os
from werkzeug.utils import secure_filename
import re
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import jsonify

app = Flask(__name__)
app.secret_key = "supersecretkey"

# -----------------------------
# 📁 IMAGE UPLOAD SETTINGS
# -----------------------------
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# -----------------------------
# 🌐 AZURE SQL CONNECTION DETAILS
# -----------------------------
server = 'lostndfound.database.windows.net'
database = 'LostFoundDB'
username = 'adminuser'
password = 'admin@123'
driver = '{ODBC Driver 18 for SQL Server}'
conn_str = f'DRIVER={driver};SERVER={server};DATABASE={database};UID={username};PWD={password}'

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def get_db_connection():
    return pyodbc.connect(conn_str)

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def check_password(password, hashed_password):
    """Compare a plaintext password with a hashed password"""
    return hash_password(password) == hashed_password

# -----------------------------
# 🧱 table creation for local use
# -----------------------------
def create_tables():
    conn = get_db_connection()
    cursor = conn.cursor()

    # USERS table
    cursor.execute("""
        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='Users' AND xtype='U')
        CREATE TABLE Users (
            id NVARCHAR(100) PRIMARY KEY,
            username NVARCHAR(100) UNIQUE,
            email NVARCHAR(200) UNIQUE,
            password NVARCHAR(256),
            is_verified BIT DEFAULT 0,
            verification_token NVARCHAR(100)
        )
    """)

    # ITEMS table
    cursor.execute("""
        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='Items' AND xtype='U')
        CREATE TABLE Items (
            id NVARCHAR(100) PRIMARY KEY,
            userId NVARCHAR(100),
            name NVARCHAR(200),
            description NVARCHAR(MAX),
            location NVARCHAR(200),
            image_url NVARCHAR(300),
            FOREIGN KEY (userId) REFERENCES Users(id)
        )
    """)

    conn.commit()
    conn.close()

create_tables()

# -----------------------------
# 📧 EMAIL SENDER
# -----------------------------
def send_verification_email(to_email, token):
    """Send verification email using SMTP."""
    from_email = "220701191@rajalakshmi.edu.in"
    from_password = "qpbi qexm cdee njqw"  # App password for Gmail
    subject = "Verify your Lost & Found account"
    verify_link = f"http://127.0.0.1:5000/verify-email/{token}"

    msg = MIMEMultipart()
    msg['From'] = from_email
    msg['To'] = to_email
    msg['Subject'] = subject
    body = f"Click the link below to verify your email:\n\n{verify_link}\n\nThank you!"
    msg.attach(MIMEText(body, 'plain'))

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(from_email, from_password)
        server.send_message(msg)
        server.quit()
        print(f"✅ Verification email sent to {to_email}")
    except Exception as e:
        print("❌ Error sending email:", e)

@app.route('/get-phone/<item_id>')
def get_phone(item_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT U.phone 
        FROM Users U
        JOIN Items I ON U.id = I.userId
        WHERE I.id = ?
    """, (item_id,))
    phone = cursor.fetchone()
    conn.close()

    if phone and phone[0]:
        return jsonify({"phone": phone[0]})
    else:
        return jsonify({"phone": None})
    
# -----------------------------
# 👤 USER ROUTES
# -----------------------------
@app.route('/')
def home():
    return redirect(url_for('user_login'))

@app.route('/user/signup', methods=['GET', 'POST'])
def user_signup():
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        password = request.form['password'].strip()
        phone = request.form['phone'].strip()

        # Restrict to college domain
        if not email.endswith("@rajalakshmi.edu.in"):
            flash("Only @rajalakshmi.edu.in emails are allowed!", "danger")
            return render_template("user_signup.html")

        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if email exists
        cursor.execute("SELECT email FROM Users WHERE email=?", (email,))
        if cursor.fetchone():
            flash("Email already registered!", "warning")
            conn.close()
            return render_template("user_signup.html")

        # Create user
        user_id = str(uuid.uuid4())
        token = str(uuid.uuid4())
        hashed_password = hash_password(password)
        username = email.split("@")[0]

        cursor.execute("""
            INSERT INTO Users (username, email, password, phone, is_verified, verification_token)
            VALUES (?, ?, ?, ?, 0, ?)
        """, (username, email, hashed_password, phone, token))
        conn.commit()
        conn.close()

        send_verification_email(email, token)
        flash("Signup successful! Check your email to verify your account.", "success")
        return redirect(url_for('user_login'))

    return render_template("user_signup.html")

@app.route('/verify-email/<token>')
def verify_email(token):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM Users WHERE verification_token=?", (token,))
    user = cursor.fetchone()

    if user:
        cursor.execute("UPDATE Users SET is_verified=1, verification_token=NULL WHERE id=?", (user[0],))
        conn.commit()
        flash("Email verified! You can now log in.", "success")
    else:
        flash("Invalid or expired verification link.", "danger")

    conn.close()
    return redirect(url_for('user_login'))

@app.route("/user_login", methods=["GET", "POST"])
def user_login():
    if request.method == "POST":
        identifier = request.form["identifier"].strip()
        password = request.form["password"].strip()

        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if identifier is an email or username
        if "@rajalakshmi.edu.in" in identifier:
            cursor.execute("SELECT id, username, email, password, is_verified FROM Users WHERE email = ?", (identifier,))
        else:
            cursor.execute("SELECT id, username, email, password, is_verified FROM Users WHERE username = ?", (identifier,))

        user = cursor.fetchone()
        conn.close()

        if not user:
            flash("Invalid username or email.", "danger")
            return redirect(url_for("user_login"))

        user_id, username, email, hashed_password, is_verified = user

        if not is_verified:
            flash("Please verify your email before logging in.", "warning")
            return redirect(url_for("user_login"))

        if not check_password(password, hashed_password):
            flash("Incorrect password. Please try again.", "danger")
            return redirect(url_for("user_login"))

        session["user_id"] = user_id
        session["username"] = username
        flash("Login successful!", "success")
        return redirect(url_for("user_dashboard"))  # Change to your actual user dashboard route

    return render_template("user_login.html")

@app.route('/user/dashboard')
def user_dashboard():
    if 'user_id' not in session:
        return redirect(url_for('user_login'))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, description, location, image_url FROM Items WHERE userId=?", (session['user_id'],))
    items = cursor.fetchall()
    conn.close()
    return render_template('user_dashboard.html', items=items, username=session['username'])

@app.route('/user/post-lost', methods=['GET', 'POST'])
def user_post_lost():
    if 'user_id' not in session:
        return redirect(url_for('user_login'))

    if request.method == 'POST':
        name = request.form['item_name']
        description = request.form['description']
        location = request.form['location']
        image = request.files.get('image')

        item_id = str(uuid.uuid4())
        image_url = "https://via.placeholder.com/150"

        if image and allowed_file(image.filename):
            filename = secure_filename(image.filename)
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            image.save(image_path)
            image_url = f"/static/uploads/{filename}"

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO Items (id, userId, name, description, location, image_url)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (item_id, session['user_id'], name, description, location, image_url))
        conn.commit()
        conn.close()
        flash('Item posted successfully!', 'success')
        return redirect(url_for('user_dashboard'))

    return render_template('user_post_lost.html')

@app.route('/user/profile')
def user_profile():
    return render_template('user_profile.html')


@app.route('/user/browse')
def user_browse():
    if 'user_id' not in session:
        return redirect(url_for('user_login'))

    search_query = request.args.get('q', '')
    conn = get_db_connection()
    cursor = conn.cursor()

    if search_query:
        cursor.execute("""
            SELECT id, userId, name, description, location, image_url
            FROM Items WHERE userId != ? AND (LOWER(name) LIKE ? OR LOWER(location) LIKE ?)
        """, (session['user_id'], f"%{search_query.lower()}%", f"%{search_query.lower()}%"))
    else:
        cursor.execute("""
            SELECT id, userId, name, description, location, image_url
            FROM Items WHERE userId != ?
        """, (session['user_id'],))

    items = cursor.fetchall()
    conn.close()

    return render_template('user_browse.html', items=items, search_query=search_query)

@app.route('/logout')
def logout():
    session.clear()
    flash("Logged out successfully!", "info")
    return redirect(url_for('user_login'))

# -----------------------------
# 🧑‍💼 ADMIN ROUTES
# -----------------------------
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        if request.form['username'] == 'admin' and request.form['password'] == 'admin123':
            session['admin'] = True
            flash("Welcome, Admin!", "success")
            return redirect(url_for('admin_dashboard'))
        else:
            flash("Invalid admin credentials!", "danger")
    return render_template('admin_login.html')

@app.route('/admin/dashboard')
def admin_dashboard():
    if 'admin' not in session:
        return redirect(url_for('admin_login'))
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, userId, name, description, location, image_url FROM Items")
    items = cursor.fetchall()
    conn.close()
    return render_template('admin_dashboard.html', items=items)

@app.route('/admin/delete/<item_id>')
def admin_delete_item(item_id):
    if 'admin' not in session:
        return redirect(url_for('admin_login'))
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM Items WHERE id=?", (item_id,))
    conn.commit()
    conn.close()
    flash("Item deleted successfully!", "success")
    return redirect(url_for('admin_dashboard'))

# -----------------------------
# 🚀 RUN APP
# -----------------------------
if __name__ == '__main__':
    app.run(debug=True)
