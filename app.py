from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from groq import Groq
import sqlite3
import hashlib
import os
import json
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "emmyai-super-secret-key-2024")

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
client = Groq(api_key=GROQ_API_KEY)

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
    conn.commit()
    conn.close()

init_db()

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

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
        password = hash_password(data.get("password", ""))
        if not name or not email or not data.get("password"):
            return jsonify({"success": False, "error": "All fields are required"})
        conn = get_db()
        try:
            conn.execute("INSERT INTO users (name, email, password) VALUES (?, ?, ?)", (name, email, password))
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

        # Verify chat belongs to user
        chat = conn.execute("SELECT * FROM chats WHERE id = ? AND user_id = ?", (chat_id, current_user.id)).fetchone()
        if not chat:
            conn.close()
            return jsonify({"success": False, "error": "Chat not found"})

        # Get history
        prev_messages = conn.execute("SELECT * FROM messages WHERE chat_id = ? ORDER BY created_at", (chat_id,)).fetchall()

        history = [{"role": "system", "content": f"You are EmmyAI, a helpful and friendly AI assistant. The user's name is {current_user.name}. Be concise, clear, and friendly."}]
        for m in prev_messages:
            history.append({"role": m["role"], "content": m["content"]})
        history.append({"role": "user", "content": user_message})

        # Save user message
        conn.execute("INSERT INTO messages (chat_id, role, content) VALUES (?, ?, ?)", (chat_id, "user", user_message))

        # Update chat title if first message
        if len(prev_messages) == 0:
            title = user_message[:40] + ("..." if len(user_message) > 40 else "")
            conn.execute("UPDATE chats SET title = ? WHERE id = ?", (title, chat_id))

        conn.commit()

        # Call Groq
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=history
        )
        reply = response.choices[0].message.content

        # Save assistant message
        conn.execute("INSERT INTO messages (chat_id, role, content) VALUES (?, ?, ?)", (chat_id, "assistant", reply))
        conn.commit()
        conn.close()

        return jsonify({"success": True, "reply": reply})

    except Exception as e:
        print("ERROR:", str(e))
        return jsonify({"success": False, "error": str(e)})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)