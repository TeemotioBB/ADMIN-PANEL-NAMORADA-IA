#!/usr/bin/env python3
"""
🎯 Sophia Admin Panel - Modern Dashboard
Live chat monitoring, analytics & management
"""

import os
import json
import redis
from datetime import datetime, timedelta
from flask import Flask, request, redirect, session, jsonify
from collections import defaultdict

# ================= CONFIG =================
REDIS_URL = "redis://default:DcddfJOHLXZdFPjEhRjHeodNgdtrsevl@shuttle.proxy.rlwy.net:12241"
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
SECRET_KEY = os.getenv("SECRET_KEY", "sophia-admin-secret-key-2024")

r = redis.from_url(REDIS_URL, decode_responses=True)
app = Flask(__name__)
app.secret_key = SECRET_KEY

# ================= MODERN STYLES =================
MODERN_CSS = """
<style>
:root {
    --primary: #6366f1;
    --primary-dark: #4f46e5;
    --secondary: #10b981;
    --danger: #ef4444;
    --warning: #f59e0b;
    --dark: #1f2937;
    --light: #f9fafb;
    --gray: #6b7280;
    --gray-light: #e5e7eb;
}

* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

body {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
    min-height: 100vh;
    color: var(--dark);
}

/* Login Page */
.login-container {
    display: flex;
    justify-content: center;
    align-items: center;
    min-height: 100vh;
    padding: 20px;
}

.login-card {
    background: white;
    border-radius: 20px;
    padding: 40px;
    width: 100%;
    max-width: 400px;
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.1);
    text-align: center;
}

.logo {
    margin-bottom: 30px;
}

.logo h1 {
    color: var(--primary);
    font-size: 28px;
    margin-bottom: 8px;
}

.logo p {
    color: var(--gray);
    font-size: 14px;
}

.input-group {
    margin-bottom: 20px;
    text-align: left;
}

.input-group label {
    display: block;
    margin-bottom: 8px;
    font-weight: 500;
    color: var(--dark);
}

.input-group input {
    width: 100%;
    padding: 12px 16px;
    border: 2px solid var(--gray-light);
    border-radius: 10px;
    font-size: 14px;
    transition: all 0.3s;
}

.input-group input:focus {
    outline: none;
    border-color: var(--primary);
    box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
}

.btn {
    display: inline-block;
    padding: 12px 24px;
    border: none;
    border-radius: 10px;
    font-weight: 600;
    font-size: 14px;
    cursor: pointer;
    transition: all 0.3s;
    text-decoration: none;
}

.btn-primary {
    background: var(--primary);
    color: white;
    width: 100%;
}

.btn-primary:hover {
    background: var(--primary-dark);
    transform: translateY(-2px);
    box-shadow: 0 10px 20px rgba(99, 102, 241, 0.2);
}

/* Dashboard Layout */
.dashboard {
    display: flex;
    min-height: 100vh;
}

/* Sidebar */
.sidebar {
    width: 260px;
    background: white;
    box-shadow: 2px 0 20px rgba(0, 0, 0, 0.05);
    padding: 24px 0;
}

.sidebar-header {
    padding: 0 24px 24px;
    border-bottom: 1px solid var(--gray-light);
}

.sidebar-nav {
    padding: 24px;
}

.nav-item {
    display: flex;
    align-items: center;
    padding: 12px 16px;
    color: var(--gray);
    text-decoration: none;
    border-radius: 8px;
    margin-bottom: 8px;
    transition: all 0.3s;
}

.nav-item:hover {
    background: var(--gray-light);
    color: var(--primary);
}

.nav-item.active {
    background: rgba(99, 102, 241, 0.1);
    color: var(--primary);
    font-weight: 600;
}

.nav-icon {
    margin-right: 12px;
    font-size: 18px;
}

/* Main Content */
.main-content {
    flex: 1;
    padding: 24px;
    overflow-y: auto;
}

.header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 30px;
}

.header h1 {
    font-size: 28px;
    font-weight: 700;
}

.stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
    gap: 20px;
    margin-bottom: 30px;
}

.stat-card {
    background: white;
    border-radius: 16px;
    padding: 24px;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.05);
    border-left: 4px solid var(--primary);
}

.stat-card:nth-child(2) { border-left-color: var(--secondary); }
.stat-card:nth-child(3) { border-left-color: var(--warning); }
.stat-card:nth-child(4) { border-left-color: var(--danger); }

.stat-value {
    font-size: 32px;
    font-weight: 700;
    margin: 8px 0;
}

.stat-label {
    color: var(--gray);
    font-size: 14px;
}

/* User List */
.users-container {
    background: white;
    border-radius: 16px;
    padding: 24px;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.05);
    margin-bottom: 30px;
}

.users-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 20px;
}

.search-box {
    padding: 10px 16px;
    border: 2px solid var(--gray-light);
    border-radius: 10px;
    width: 300px;
}

.user-list {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
    gap: 16px;
}

.user-card {
    border: 1px solid var(--gray-light);
    border-radius: 12px;
    padding: 20px;
    transition: all 0.3s;
    cursor: pointer;
}

.user-card:hover {
    border-color: var(--primary);
    transform: translateY(-4px);
    box-shadow: 0 10px 25px rgba(99, 102, 241, 0.1);
}

.user-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 12px;
}

.user-id {
    font-weight: 600;
    color: var(--dark);
}

.user-status {
    padding: 4px 12px;
    border-radius: 20px;
    font-size: 12px;
    font-weight: 600;
}

.status-active {
    background: rgba(16, 185, 129, 0.1);
    color: var(--secondary);
}

.status-inactive {
    background: rgba(239, 68, 68, 0.1);
    color: var(--danger);
}

.user-info {
    display: flex;
    justify-content: space-between;
    font-size: 13px;
    color: var(--gray);
    margin-top: 12px;
}

/* Chat Interface */
.chat-container {
    display: flex;
    flex-direction: column;
    height: calc(100vh - 120px);
    background: white;
    border-radius: 16px;
    overflow: hidden;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.05);
}

.chat-header {
    background: var(--primary);
    color: white;
    padding: 20px 24px;
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.chat-messages {
    flex: 1;
    padding: 24px;
    overflow-y: auto;
    background: linear-gradient(180deg, #f8fafc 0%, #ffffff 100%);
}

.message {
    display: flex;
    margin-bottom: 20px;
    max-width: 70%;
}

.message-user {
    margin-left: auto;
    flex-direction: row-reverse;
}

.message-content {
    padding: 16px;
    border-radius: 18px;
    position: relative;
}

.message-sophia .message-content {
    background: white;
    border: 1px solid var(--gray-light);
    border-top-left-radius: 4px;
}

.message-user .message-content {
    background: var(--primary);
    color: white;
    border-top-right-radius: 4px;
}

.message-sender {
    font-weight: 600;
    font-size: 13px;
    margin-bottom: 4px;
    color: var(--gray);
}

.message-user .message-sender {
    text-align: right;
    color: rgba(255, 255, 255, 0.9);
}

.message-time {
    font-size: 11px;
    color: var(--gray);
    margin-top: 4px;
}

.message-user .message-time {
    color: rgba(255, 255, 255, 0.7);
    text-align: right;
}

/* Revenue Section */
.revenue-card {
    background: white;
    border-radius: 16px;
    padding: 24px;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.05);
}

.revenue-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 16px;
    border-bottom: 1px solid var(--gray-light);
    transition: background 0.3s;
}

.revenue-item:hover {
    background: var(--gray-light);
}

.revenue-amount {
    font-weight: 700;
    font-size: 18px;
    color: var(--secondary);
}

/* Animations */
@keyframes fadeIn {
    from { opacity: 0; transform: translateY(10px); }
    to { opacity: 1; transform: translateY(0); }
}

.fade-in {
    animation: fadeIn 0.3s ease-out;
}

/* Responsive */
@media (max-width: 768px) {
    .dashboard {
        flex-direction: column;
    }
    
    .sidebar {
        width: 100%;
        padding: 16px;
    }
    
    .main-content {
        padding: 16px;
    }
    
    .search-box {
        width: 100%;
    }
    
    .message {
        max-width: 90%;
    }
}
</style>
"""

# ================= UTILITIES =================
def get_active_users():
    """Get users with activity in last 30 minutes"""
    active_users = set()
    now = datetime.now()
    
    for key in r.scan_iter("chatlog:*"):
        uid = key.split(":")[1]
        logs = r.lrange(key, 0, -1)
        if logs:
            try:
                last_msg = json.loads(logs[-1])
                msg_time = datetime.fromisoformat(last_msg["ts"])
                if now - msg_time < timedelta(minutes=30):
                    active_users.add(uid)
            except:
                continue
    return active_users

def get_chat_stats(uid):
    """Get statistics for a specific user chat"""
    logs = r.lrange(f"chatlog:{uid}", 0, -1)
    user_msgs = 0
    sophia_msgs = 0
    last_activity = None
    
    for log in logs:
        try:
            msg = json.loads(log)
            if msg["role"] == "user":
                user_msgs += 1
            else:
                sophia_msgs += 1
            
            msg_time = datetime.fromisoformat(msg["ts"])
            if not last_activity or msg_time > last_activity:
                last_activity = msg_time
        except:
            continue
    
    return {
        "user_messages": user_msgs,
        "sophia_messages": sophia_msgs,
        "total_messages": user_msgs + sophia_msgs,
        "last_activity": last_activity
    }

def get_revenue_summary():
    """Get revenue summary from Redis"""
    revenue_logs = r.lrange("revenue", 0, -1)
    total = 0
    today_total = 0
    today = datetime.now().date()
    
    for log in revenue_logs:
        try:
            if ":" in log:
                amount_str, date_str = log.split(":", 1)
                amount = float(amount_str.replace("R$", "").strip())
                log_date = datetime.strptime(date_str.strip(), "%Y-%m-%d %H:%M:%S").date()
                
                total += amount
                if log_date == today:
                    today_total += amount
        except:
            continue
    
    return {
        "total": total,
        "today": today_total,
        "average": total / max(len(revenue_logs), 1)
    }

# ================= ROUTES =================
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            session["authenticated"] = True
            session["login_time"] = datetime.now().isoformat()
            return redirect("/dashboard")
    
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Sophia Admin - Login</title>
        {MODERN_CSS}
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    </head>
    <body>
        <div class="login-container">
            <div class="login-card">
                <div class="logo">
                    <h1><i class="fas fa-brain"></i> Sophia AI</h1>
                    <p>Administrative Dashboard</p>
                </div>
                <form method="post">
                    <div class="input-group">
                        <label for="password"><i class="fas fa-lock"></i> Admin Password</label>
                        <input type="password" id="password" name="password" placeholder="Enter your password" required>
                    </div>
                    <button type="submit" class="btn btn-primary">
                        <i class="fas fa-sign-in-alt"></i> Access Dashboard
                    </button>
                </form>
            </div>
        </div>
    </body>
    </html>
    """

@app.route("/dashboard")
def dashboard():
    if not session.get("authenticated"):
        return redirect("/")
    
    # Get all users
    users = set()
    user_stats = {}
    
    for key in r.scan_iter("chatlog:*"):
        uid = key.split(":")[1]
        users.add(uid)
        user_stats[uid] = get_chat_stats(uid)
    
    active_users = get_active_users()
    
    # Get revenue summary
    revenue = get_revenue_summary()
    
    # Build users list HTML
    users_html = ""
    for uid in sorted(users, key=lambda x: user_stats[x].get("last_activity") or datetime.min, reverse=True):
        stats = user_stats[uid]
        status_class = "status-active" if uid in active_users else "status-inactive"
        status_text = "Active" if uid in active_users else "Inactive"
        
        last_active = stats.get("last_activity")
        if last_active:
            time_diff = datetime.now() - last_active
            if time_diff < timedelta(minutes=1):
                last_seen = "Just now"
            elif time_diff < timedelta(hours=1):
                last_seen = f"{int(time_diff.seconds / 60)} min ago"
            else:
                last_seen = last_active.strftime("%H:%M")
        else:
            last_seen = "Never"
        
        users_html += f"""
        <div class="user-card fade-in" onclick="window.location.href='/chat/{uid}'">
            <div class="user-header">
                <div class="user-id">
                    <i class="fas fa-user-circle"></i> User: {uid[:8]}...
                </div>
                <div class="user-status {status_class}">
                    {status_text}
                </div>
            </div>
            <div class="user-info">
                <span><i class="fas fa-comments"></i> {stats['total_messages']} msgs</span>
                <span><i class="fas fa-clock"></i> {last_seen}</span>
            </div>
        </div>
        """
    
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Sophia Admin Dashboard</title>
        {MODERN_CSS}
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    </head>
    <body>
        <div class="dashboard">
            <!-- Sidebar -->
            <div class="sidebar">
                <div class="sidebar-header">
                    <h2><i class="fas fa-brain"></i> Sophia AI</h2>
                    <p style="color: var(--gray); font-size: 12px;">Admin Panel</p>
                </div>
                <div class="sidebar-nav">
                    <a href="/dashboard" class="nav-item active">
                        <i class="fas fa-home nav-icon"></i> Dashboard
                    </a>
                    <a href="/revenue" class="nav-item">
                        <i class="fas fa-chart-line nav-icon"></i> Revenue Analytics
                    </a>
                    <a href="#" class="nav-item">
                        <i class="fas fa-cog nav-icon"></i> Settings
                    </a>
                    <a href="/logout" class="nav-item" style="color: var(--danger);">
                        <i class="fas fa-sign-out-alt nav-icon"></i> Logout
                    </a>
                </div>
            </div>
            
            <!-- Main Content -->
            <div class="main-content">
                <div class="header">
                    <h1><i class="fas fa-tachometer-alt"></i> Dashboard Overview</h1>
                    <div style="color: var(--gray); font-size: 14px;">
                        <i class="fas fa-clock"></i> {datetime.now().strftime("%Y-%m-%d %H:%M")}
                    </div>
                </div>
                
                <!-- Stats Grid -->
                <div class="stats-grid">
                    <div class="stat-card">
                        <div class="stat-value">{len(users)}</div>
                        <div class="stat-label">Total Users</div>
                        <div style="font-size: 12px; color: var(--secondary); margin-top: 8px;">
                            <i class="fas fa-users"></i> {len(active_users)} active now
                        </div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">R${revenue['total']:.2f}</div>
                        <div class="stat-label">Total Revenue</div>
                        <div style="font-size: 12px; color: var(--secondary); margin-top: 8px;">
                            <i class="fas fa-calendar-day"></i> R${revenue['today']:.2f} today
                        </div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">{sum(s['total_messages'] for s in user_stats.values())}</div>
                        <div class="stat-label">Total Messages</div>
                        <div style="font-size: 12px; color: var(--warning); margin-top: 8px;">
                            <i class="fas fa-exchange-alt"></i> User: {sum(s['user_messages'] for s in user_stats.values())}
                        </div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">24/7</div>
                        <div class="stat-label">Uptime</div>
                        <div style="font-size: 12px; color: var(--primary); margin-top: 8px;">
                            <i class="fas fa-server"></i> All systems operational
                        </div>
                    </div>
                </div>
                
                <!-- Users List -->
                <div class="users-container">
                    <div class="users-header">
                        <h3><i class="fas fa-comments"></i> Active Chats</h3>
                        <input type="text" class="search-box" placeholder="Search users..." 
                               onkeyup="filterUsers(this.value)">
                    </div>
                    <div class="user-list" id="userList">
                        {users_html}
                    </div>
                </div>
                
                <!-- Quick Actions -->
                <div style="display: flex; gap: 16px;">
                    <button class="btn btn-primary" onclick="refreshData()">
                        <i class="fas fa-sync-alt"></i> Refresh Data
                    </button>
                    <button class="btn" style="background: var(--warning); color: white;">
                        <i class="fas fa-download"></i> Export Data
                    </button>
                </div>
            </div>
        </div>
        
        <script>
        function filterUsers(search) {{
            const users = document.querySelectorAll('.user-card');
            search = search.toLowerCase();
            
            users.forEach(user => {{
                const text = user.textContent.toLowerCase();
                user.style.display = text.includes(search) ? 'block' : 'none';
            }});
        }}
        
        function refreshData() {{
            location.reload();
        }}
        
        // Auto-refresh every 30 seconds
        setTimeout(() => {{
            location.reload();
        }}, 30000);
        </script>
    </body>
    </html>
    """

@app.route("/chat/<uid>")
def chat(uid):
    if not session.get("authenticated"):
        return redirect("/")
    
    logs = r.lrange(f"chatlog:{uid}", 0, -1)
    stats = get_chat_stats(uid)
    
    messages_html = ""
    for line in logs:
        try:
            msg = json.loads(line)
            ts = datetime.fromisoformat(msg["ts"])
            time_str = ts.strftime("%H:%M")
            date_str = ts.strftime("%b %d")
            
            if msg["role"] == "user":
                messages_html += f"""
                <div class="message message-user">
                    <div class="message-content">
                        <div class="message-sender">USER</div>
                        <div>{msg["text"]}</div>
                        <div class="message-time">{time_str} • {date_str}</div>
                    </div>
                </div>
                """
            else:
                messages_html += f"""
                <div class="message message-sophia">
                    <div class="message-content">
                        <div class="message-sender">SOPHIA 💖</div>
                        <div>{msg["text"]}</div>
                        <div class="message-time">{time_str} • {date_str}</div>
                    </div>
                </div>
                """
        except:
            continue
    
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Chat with User {uid}</title>
        {MODERN_CSS}
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    </head>
    <body>
        <div class="dashboard">
            <!-- Sidebar -->
            <div class="sidebar">
                <div class="sidebar-header">
                    <h2><i class="fas fa-comments"></i> Chat View</h2>
                    <p style="color: var(--gray); font-size: 12px;">User: {uid[:12]}...</p>
                </div>
                <div class="sidebar-nav">
                    <a href="/dashboard" class="nav-item">
                        <i class="fas fa-arrow-left nav-icon"></i> Back to Dashboard
                    </a>
                    <a href="#" class="nav-item active">
                        <i class="fas fa-user nav-icon"></i> User Profile
                    </a>
                    <a href="#" class="nav-item">
                        <i class="fas fa-ban nav-icon"></i> Block User
                    </a>
                    <a href="#" class="nav-item">
                        <i class="fas fa-trash nav-icon"></i> Clear Chat
                    </a>
                </div>
                <div style="padding: 24px; border-top: 1px solid var(--gray-light);">
                    <h4 style="margin-bottom: 16px;">Chat Statistics</h4>
                    <div style="font-size: 14px; line-height: 24px;">
                        <div><i class="fas fa-user" style="color: var(--primary);"></i> User Messages: {stats['user_messages']}</div>
                        <div><i class="fas fa-robot" style="color: var(--secondary);"></i> Sophia Replies: {stats['sophia_messages']}</div>
                        <div><i class="fas fa-hashtag" style="color: var(--warning);"></i> Total: {stats['total_messages']}</div>
                        <div><i class="fas fa-clock" style="color: var(--gray);"></i> Last: {stats['last_activity'].strftime('%H:%M') if stats['last_activity'] else 'Never'}</div>
                    </div>
                </div>
            </div>
            
            <!-- Main Content -->
            <div class="main-content" style="padding: 0;">
                <div class="chat-container">
                    <div class="chat-header">
                        <div>
                            <h3 style="color: white; margin-bottom: 4px;">
                                <i class="fas fa-user-circle"></i> Conversation with {uid}
                            </h3>
                            <div style="font-size: 12px; opacity: 0.9;">
                                {stats['total_messages']} messages • Last active: {stats['last_activity'].strftime('%H:%M') if stats['last_activity'] else 'Never'}
                            </div>
                        </div>
                        <div>
                            <button class="btn" style="background: rgba(255,255,255,0.2); color: white;" 
                                    onclick="location.reload()">
                                <i class="fas fa-sync-alt"></i> Refresh
                            </button>
                        </div>
                    </div>
                    <div class="chat-messages" id="chatMessages">
                        {messages_html}
                    </div>
                </div>
            </div>
        </div>
        
        <script>
        // Auto-scroll to bottom
        const chatMessages = document.getElementById('chatMessages');
        chatMessages.scrollTop = chatMessages.scrollHeight;
        
        // Auto-refresh every 5 seconds
        setInterval(() => {{
            location.reload();
        }}, 5000);
        </script>
    </body>
    </html>
    """

@app.route("/revenue")
def revenue():
    if not session.get("authenticated"):
        return redirect("/")
    
    revenue_logs = r.lrange("revenue", 0, -1)
    summary = get_revenue_summary()
    
    revenue_html = ""
    for log in reversed(revenue_logs[-50:]):  # Show last 50 entries
        revenue_html += f"""
        <div class="revenue-item">
            <div>
                <div style="font-weight: 600;">Payment Received</div>
                <div style="font-size: 12px; color: var(--gray);">{log.split(':', 1)[1] if ':' in log else 'Unknown date'}</div>
            </div>
            <div class="revenue-amount">{log.split(':')[0] if ':' in log else log}</div>
        </div>
        """
    
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Revenue Analytics</title>
        {MODERN_CSS}
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    </head>
    <body>
        <div class="dashboard">
            <div class="sidebar">
                <div class="sidebar-header">
                    <h2><i class="fas fa-chart-line"></i> Revenue</h2>
                </div>
                <div class="sidebar-nav">
                    <a href="/dashboard" class="nav-item">
                        <i class="fas fa-home nav-icon"></i> Dashboard
                    </a>
                    <a href="/revenue" class="nav-item active">
                        <i class="fas fa-chart-line nav-icon"></i> Revenue Analytics
                    </a>
                    <a href="/revenue" class="nav-item">
                        <i class="fas fa-file-export nav-icon"></i> Export Report
                    </a>
                </div>
                <div style="padding: 24px; border-top: 1px solid var(--gray-light);">
                    <h4 style="margin-bottom: 16px;">Quick Stats</h4>
                    <div style="font-size: 14px; line-height: 24px;">
                        <div><i class="fas fa-money-bill-wave" style="color: var(--secondary);"></i> Today: R${summary['today']:.2f}</div>
                        <div><i class="fas fa-chart-bar" style="color: var(--primary);"></i> Average: R${summary['average']:.2f}</div>
                        <div><i class="fas fa-receipt" style="color: var(--warning);"></i> Total Records: {len(revenue_logs)}</div>
                    </div>
                </div>
            </div>
            
            <div class="main-content">
                <div class="header">
                    <h1><i class="fas fa-chart-pie"></i> Revenue Analytics</h1>
                </div>
                
                <div class="stats-grid">
                    <div class="stat-card">
                        <div class="stat-value">R${summary['total']:.2f}</div>
                        <div class="stat-label">Total Revenue</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">R${summary['today']:.2f}</div>
                        <div class="stat-label">Today's Revenue</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">R${summary['average']:.2f}</div>
                        <div class="stat-label">Average per Transaction</div>
                    </div>
                </div>
                
                <div class="revenue-card">
                    <h3 style="margin-bottom: 20px;"><i class="fas fa-history"></i> Recent Transactions</h3>
                    <div id="revenueList">
                        {revenue_html if revenue_html else '<div style="text-align: center; padding: 40px; color: var(--gray);">No revenue data available</div>'}
                    </div>
                </div>
            </div>
        </div>
    </body>
    </html>
    """

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

@app.route("/api/chat/<uid>")
def api_chat(uid):
    """API endpoint for chat data (for potential future AJAX updates)"""
    if not session.get("authenticated"):
        return jsonify({"error": "Unauthorized"}), 401
    
    logs = r.lrange(f"chatlog:{uid}", 0, -1)
    messages = []
    
    for line in logs:
        try:
            msg = json.loads(line)
            messages.append({
                "role": msg["role"],
                "text": msg["text"],
                "time": msg["ts"]
            })
        except:
            continue
    
    return jsonify({
        "user_id": uid,
        "messages": messages,
        "total": len(messages)
    })

# ================= MAIN =================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=True)
