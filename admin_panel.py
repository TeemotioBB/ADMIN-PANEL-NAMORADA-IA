#!/usr/bin/env python3
"""
🧠 Sophia Admin Panel
Live chat monitoring, VIPs and revenue
"""

import os
import json
import redis
from datetime import datetime
from flask import Flask, request, redirect

# ================= CONFIG =================
REDIS_URL = "redis://default:DcddfJOHLXZdFPjEhRjHeodNgdtrsevl@shuttle.proxy.rlwy.net:12241"
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

r = redis.from_url(REDIS_URL, decode_responses=True)

app = Flask(__name__)

# ================= HTML BASE =================
BASE_STYLE = """
<style>
body {
    font-family: Arial, sans-serif;
    background: #f4f6fb;
    margin: 0;
    padding: 20px;
}
h1, h2 {
    color: #333;
}
a {
    text-decoration: none;
    color: #6a3df0;
}
.container {
    max-width: 900px;
    margin: auto;
}
.user-list li {
    padding: 10px;
    background: #fff;
    margin-bottom: 8px;
    border-radius: 6px;
}
.chat-box {
    background: #fff;
    padding: 15px;
    border-radius: 8px;
}
.msg {
    margin-bottom: 12px;
    max-width: 75%;
    padding: 10px;
    border-radius: 12px;
    clear: both;
}
.user {
    background: #e0e0ff;
    float: right;
    text-align: right;
}
.sophia {
    background: #ffe0f0;
    float: left;
}
.time {
    font-size: 11px;
    color: #777;
    margin-top: 4px;
}
.back {
    display: inline-block;
    margin-top: 15px;
}
.revenue {
    background: #fff;
    padding: 15px;
    border-radius: 8px;
    margin-top: 20px;
    font-size: 14px;
}
</style>
"""

# ================= AUTH =================
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            return redirect("/dashboard")

    return BASE_STYLE + """
    <div class="container">
        <h2>🔐 Sophia Admin Login</h2>
        <form method="post">
            <input type="password" name="password" placeholder="Password" />
            <button type="submit">Login</button>
        </form>
    </div>
    """

# ================= DASHBOARD =================
@app.route("/dashboard")
def dashboard():
    users = set()

    for key in r.scan_iter("chatlog:*"):
        users.add(key.split(":")[1])

    html = BASE_STYLE + "<div class='container'>"
    html += "<h1>💬 Sophia Live Chats</h1><ul class='user-list'>"

    for uid in sorted(users):
        html += f"<li><a href='/chat/{uid}'>User {uid}</a></li>"

    html += "</ul>"

    html += "<div class='revenue'><h2>💰 Revenue</h2><pre>"
    for row in r.lrange("revenue", 0, -1):
        html += row + "\n"
    html += "</pre></div>"

    html += "</div>"
    return html

# ================= CHAT VIEW =================
@app.route("/chat/<uid>")
def chat(uid):
    logs = r.lrange(f"chatlog:{uid}", 0, -1)

    html = BASE_STYLE + """
    <meta http-equiv="refresh" content="3">
    <div class="container">
    """
    html += f"<h1>💬 Chat with {uid}</h1>"
    html += "<div class='chat-box'>"

    for line in logs:
        try:
            msg = json.loads(line)
            ts = datetime.fromisoformat(msg["ts"]).strftime("%H:%M:%S")
            role = msg["role"]
            text = msg["text"]

            cls = "user" if role == "user" else "sophia"
            label = "USER" if role == "user" else "SOPHIA 💖"

            html += f"""
            <div class="msg {cls}">
                <strong>{label}</strong><br>
                {text}
                <div class="time">{ts}</div>
            </div>
            """
        except:
            continue

    html += "</div>"
    html += "<a class='back' href='/dashboard'>⬅ Back to dashboard</a>"
    html += "</div>"

    return html

# ================= MAIN =================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
