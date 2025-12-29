#!/usr/bin/env python3
"""
🧠 Sophia Admin Panel
Monitor chats, VIPs and revenue
"""

import os
import redis
from flask import Flask, request, redirect, url_for

REDIS_URL = "redis://default:DcddfJOHLXZdFPjEhRjHeodNgdtrsevl@shuttle.proxy.rlwy.net:12241"
ADMIN_PASSWORD = "admin123"  # MUDE ISSO

r = redis.from_url(REDIS_URL, decode_responses=True)

app = Flask(__name__)

# ================= AUTH =================
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            return redirect("/dashboard")
    return """
        <h2>Sophia Admin Login</h2>
        <form method="post">
            <input type="password" name="password" placeholder="Password"/>
            <button>Login</button>
        </form>
    """

# ================= DASHBOARD =================
@app.route("/dashboard")
def dashboard():
    users = set()

    for key in r.scan_iter("chatlog:*"):
        users.add(key.split(":")[1])

    html = "<h1>Sophia Dashboard</h1><ul>"
    for uid in users:
        html += f"<li><a href='/chat/{uid}'>User {uid}</a></li>"
    html += "</ul>"

    html += "<h2>Revenue</h2><pre>"
    for row in r.lrange("revenue", 0, -1):
        html += row + "\n"
    html += "</pre>"

    return html

# ================= CHAT VIEW =================
@app.route("/chat/<uid>")
def chat(uid):
    logs = r.lrange(f"chatlog:{uid}", 0, -1)

    html = f"<h1>Chat with {uid}</h1><pre>"
    for line in logs:
        html += line + "\n"
    html += "</pre><a href='/dashboard'>Back</a>"

    return html

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)
