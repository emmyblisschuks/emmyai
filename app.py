from flask import Flask, render_template, request, jsonify
from groq import Groq
import os

app = Flask(__name__)

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "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")client = Groq(api_key=GROQ_API_KEY)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/chat", methods=["POST"])
def chat():
    try:
        body = request.json
        messages = body.get("messages", [])

        history = [{"role": "system", "content": "You are EmmyAI, a helpful and friendly assistant. Always be concise and clear."}]

        for msg in messages:
            role = "user" if msg["role"] == "user" else "assistant"
            history.append({"role": role, "content": msg["content"]})

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=history
        )

        reply = response.choices[0].message.content
        print("SUCCESS:", reply[:50])
        return jsonify({"success": True, "reply": reply})

    except Exception as e:
        print("ERROR:", str(e))
        return jsonify({"success": False, "error": str(e)})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)