from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from groq import Groq
import sqlite3
import hashlib
import os
import re
import secrets
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "emmyai-super-secret-key-2024")

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
client = Groq(api_key=GROQ_API_KEY)

GMAIL_USER = os.environ.get("GMAIL_USER", "emmy41096@gmail.com")
GMAIL_PASS = os.environ.get("GMAIL_PASS", "wuox xrdo oaxn otzu")
APP_URL = os.environ.get("APP_URL", "http://localhost:5000")

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

DB = "emmyai.db"

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT DEFAULT 'New Chat',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(chat_id) REFERENCES chats(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reset_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token TEXT UNIQUE NOT NULL,
            expires_at TEXT NOT NULL,
            used INTEGER DEFAULT 0,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)
    conn.commit()
    conn.close()

init_db()

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def is_valid_email(email):
    return re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email)

def send_email(to_email, subject, html_body):
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = GMAIL_USER
        msg["To"] = to_email
        msg.attach(MIMEText(html_body, "html"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_USER, GMAIL_PASS)
            server.sendmail(GMAIL_USER, to_email, msg.as_string())
        return True
    except Exception as e:
        print("EMAIL ERROR:", str(e))
        return False

class User(UserMixin):
    def __init__(self, id, name, email):
        self.id = id
        self.name = name
        self.email = email

@login_manager.user_loader
def load_user(user_id):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    if user:
        return User(user["id"], user["name"], user["email"])
    return None

@app.route("/")
@login_required
def index():
    return render_template("index.html", user=current_user)

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    if request.method == "POST":
        data = request.json
        email = data.get("email", "").strip().lower()
        password = hash_password(data.get("password", ""))
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE email = ? AND password = ?", (email, password)).fetchone()
        conn.close()
        if user:
            login_user(User(user["id"], user["name"], user["email"]), remember=True)
            return jsonify({"success": True})
        return jsonify({"success": False, "error": "Invalid email or password"})
    return render_template("login.html")

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    if request.method == "POST":
        data = request.json
        name = data.get("name", "").strip()
        email = data.get("email", "").strip().lower()
        password = data.get("password", "")

        if not name or not email or not password:
            return jsonify({"success": False, "error": "All fields are required"})
        if not is_valid_email(email):
            return jsonify({"success": False, "error": "Please enter a valid email address"})
        if len(password) < 6:
            return jsonify({"success": False, "error": "Password must be at least 6 characters"})

        conn = get_db()
        try:
            conn.execute("INSERT INTO users (name, email, password) VALUES (?, ?, ?)", (name, email, hash_password(password)))
            conn.commit()
            user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            login_user(User(user["id"], user["name"], user["email"]), remember=True)
            conn.close()
            return jsonify({"success": True})
        except sqlite3.IntegrityError:
            conn.close()
            return jsonify({"success": False, "error": "Email already registered"})
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        data = request.json
        email = data.get("email", "").strip().lower()
        if not is_valid_email(email):
            return jsonify({"success": False, "error": "Please enter a valid email address"})
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if user:
            token = secrets.token_urlsafe(32)
            expires_at = (datetime.now() + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
            conn.execute("INSERT INTO reset_tokens (user_id, token, expires_at) VALUES (?, ?, ?)", (user["id"], token, expires_at))
            conn.commit()
            reset_link = f"{APP_URL}/reset-password/{token}"
            html = f"""
            <div style="font-family:Arial,sans-serif;max-width:500px;margin:0 auto;padding:20px;">
              <h2 style="color:#10a37f;">EmmyAI Password Reset</h2>
              <p>Hello <strong>{user['name']}</strong>,</p>
              <p>Click the button below to reset your password. This link expires in <strong>1 hour</strong>.</p>
              <a href="{reset_link}" style="display:inline-block;padding:12px 24px;background:#10a37f;color:#fff;text-decoration:none;border-radius:8px;margin:16px 0;">Reset Password</a>
              <p style="color:#888;font-size:12px;">If you didn't request this, ignore this email.</p>
            </div>
            """
            send_email(email, "Reset your EmmyAI password", html)
        conn.close()
        return jsonify({"success": True, "message": "If that email exists, a reset link has been sent."})
    return render_template("forgot_password.html")

@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    conn = get_db()
    row = conn.execute("SELECT * FROM reset_tokens WHERE token = ? AND used = 0", (token,)).fetchone()
    if not row or datetime.strptime(row["expires_at"], "%Y-%m-%d %H:%M:%S") < datetime.now():
        conn.close()
        return render_template("reset_password.html", error="This reset link is invalid or has expired.")
    if request.method == "POST":
        data = request.json
        password = data.get("password", "")
        if len(password) < 6:
            conn.close()
            return jsonify({"success": False, "error": "Password must be at least 6 characters"})
        conn.execute("UPDATE users SET password = ? WHERE id = ?", (hash_password(password), row["user_id"]))
        conn.execute("UPDATE reset_tokens SET used = 1 WHERE token = ?", (token,))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    conn.close()
    return render_template("reset_password.html", token=token, error=None)

# Chat APIs
@app.route("/api/chats", methods=["GET"])
@login_required
def get_chats():
    conn = get_db()
    chats = conn.execute("SELECT * FROM chats WHERE user_id = ? ORDER BY created_at DESC", (current_user.id,)).fetchall()
    conn.close()
    return jsonify([{"id": c["id"], "title": c["title"], "created_at": c["created_at"]} for c in chats])

@app.route("/api/chats", methods=["POST"])
@login_required
def new_chat():
    conn = get_db()
    conn.execute("INSERT INTO chats (user_id, title) VALUES (?, ?)", (current_user.id, "New Chat"))
    conn.commit()
    chat = conn.execute("SELECT * FROM chats WHERE user_id = ? ORDER BY id DESC LIMIT 1", (current_user.id,)).fetchone()
    conn.close()
    return jsonify({"id": chat["id"], "title": chat["title"]})

@app.route("/api/chats/<int:chat_id>", methods=["GET"])
@login_required
def get_chat(chat_id):
    conn = get_db()
    chat = conn.execute("SELECT * FROM chats WHERE id = ? AND user_id = ?", (chat_id, current_user.id)).fetchone()
    if not chat:
        conn.close()
        return jsonify({"error": "Not found"}), 404
    messages = conn.execute("SELECT * FROM messages WHERE chat_id = ? ORDER BY created_at", (chat_id,)).fetchall()
    conn.close()
    return jsonify({
        "id": chat["id"],
        "title": chat["title"],
        "messages": [{"role": m["role"], "content": m["content"]} for m in messages]
    })

@app.route("/api/chats/<int:chat_id>", methods=["DELETE"])
@login_required
def delete_chat(chat_id):
    conn = get_db()
    conn.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
    conn.execute("DELETE FROM chats WHERE id = ? AND user_id = ?", (chat_id, current_user.id))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route("/api/chat", methods=["POST"])
@login_required
def chat():
    try:
        body = request.json
        chat_id = body.get("chat_id")
        user_message = body.get("message", "")
        conn = get_db()
        chat = conn.execute("SELECT * FROM chats WHERE id = ? AND user_id = ?", (chat_id, current_user.id)).fetchone()
        if not chat:
            conn.close()
            return jsonify({"success": False, "error": "Chat not found"})
        prev_messages = conn.execute("SELECT * FROM messages WHERE chat_id = ? ORDER BY created_at", (chat_id,)).fetchall()
        history = [{"role": "system", "content": f"You are EmmyAI, a helpful and friendly AI assistant. The user's name is {current_user.name}. Be concise, clear, and friendly."}]
        for m in prev_messages:
            history.append({"role": m["role"], "content": m["content"]})
        history.append({"role": "user", "content": user_message})
        conn.execute("INSERT INTO messages (chat_id, role, content) VALUES (?, ?, ?)", (chat_id, "user", user_message))
        if len(prev_messages) == 0:
            title = user_message[:40] + ("..." if len(user_message) > 40 else "")
            conn.execute("UPDATE chats SET title = ? WHERE id = ?", (title, chat_id))
        conn.commit()
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=history
        )
        reply = response.choices[0].message.content
        conn.execute("INSERT INTO messages (chat_id, role, content) VALUES (?, ?, ?)", (chat_id, "assistant", reply))
        conn.commit()
        conn.close()
        return jsonify({"success": True, "reply": reply})
    except Exception as e:
        print("ERROR:", str(e))
        return jsonify({"success": False, "error": str(e)})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)