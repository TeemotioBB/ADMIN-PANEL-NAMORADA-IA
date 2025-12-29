#!/usr/bin/env python3
"""
🎯 Sophia Admin Panel - Optimized for Railway
"""

import os
import json
import redis
from datetime import datetime, timedelta
from flask import Flask, request, redirect, session, jsonify, render_template_string
import logging
import time

# ================= CONFIG =================
# Railway fornece essas variáveis automaticamente
REDIS_URL = os.environ.get("REDIS_URL", "redis://default:DcddfJOHLXZdFPjEhRjHeodNgdtrsevl@shuttle.proxy.rlwy.net:12241")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")
SECRET_KEY = os.environ.get("SECRET_KEY", "sophia-secret-" + str(int(time.time())))
PORT = int(os.environ.get("PORT", 8080))

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Inicializar Redis com retry
redis_client = None
try:
    redis_client = redis.from_url(REDIS_URL, decode_responses=True, socket_connect_timeout=5, socket_timeout=5)
    redis_client.ping()
    logger.info("✅ Redis conectado com sucesso")
except Exception as e:
    logger.error(f"❌ Erro ao conectar ao Redis: {e}")
    # Criar cliente dummy para desenvolvimento
    redis_client = None

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=2)

# ================= HTML TEMPLATES =================
BASE_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - Sophia Admin</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        {css}
    </style>
</head>
<body>
    {content}
    <script>
        {scripts}
    </script>
</body>
</html>
"""

MODERN_CSS = """
:root {
    --primary: #7c3aed;
    --primary-light: #8b5cf6;
    --primary-dark: #5b21b6;
    --secondary: #10b981;
    --danger: #ef4444;
    --warning: #f59e0b;
    --info: #3b82f6;
    --dark: #1f2937;
    --light: #f9fafb;
    --gray-100: #f3f4f6;
    --gray-200: #e5e7eb;
    --gray-300: #d1d5db;
    --gray-400: #9ca3af;
    --gray-500: #6b7280;
    --gray-600: #4b5563;
    --gray-700: #374151;
    --gray-800: #1f2937;
    --gray-900: #111827;
    
    --shadow-sm: 0 1px 2px 0 rgb(0 0 0 / 0.05);
    --shadow: 0 1px 3px 0 rgb(0 0 0 / 0.1), 0 1px 2px -1px rgb(0 0 0 / 0.1);
    --shadow-md: 0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1);
    --shadow-lg: 0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1);
}

* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

body {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    min-height: 100vh;
    color: var(--gray-800);
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
    padding: 50px 40px;
    width: 100%;
    max-width: 420px;
    box-shadow: var(--shadow-lg);
    animation: slideUp 0.5s ease-out;
}

@keyframes slideUp {
    from {
        opacity: 0;
        transform: translateY(20px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}

.logo {
    text-align: center;
    margin-bottom: 40px;
}

.logo-icon {
    font-size: 48px;
    color: var(--primary);
    margin-bottom: 16px;
}

.logo h1 {
    color: var(--primary-dark);
    font-size: 32px;
    font-weight: 800;
    letter-spacing: -0.5px;
    margin-bottom: 8px;
}

.logo p {
    color: var(--gray-500);
    font-size: 14px;
    font-weight: 500;
}

.input-group {
    margin-bottom: 24px;
}

.input-group label {
    display: block;
    margin-bottom: 8px;
    font-weight: 600;
    color: var(--gray-700);
    font-size: 14px;
}

.input-wrapper {
    position: relative;
}

.input-wrapper i {
    position: absolute;
    left: 16px;
    top: 50%;
    transform: translateY(-50%);
    color: var(--gray-400);
}

.input-wrapper input {
    width: 100%;
    padding: 14px 16px 14px 48px;
    border: 2px solid var(--gray-200);
    border-radius: 12px;
    font-size: 15px;
    font-weight: 500;
    transition: all 0.3s;
    background: var(--gray-50);
}

.input-wrapper input:focus {
    outline: none;
    border-color: var(--primary);
    background: white;
    box-shadow: 0 0 0 4px rgba(124, 58, 237, 0.1);
}

.btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    padding: 14px 28px;
    border: none;
    border-radius: 12px;
    font-weight: 600;
    font-size: 15px;
    cursor: pointer;
    transition: all 0.3s;
    text-decoration: none;
    width: 100%;
}

.btn-primary {
    background: linear-gradient(135deg, var(--primary) 0%, var(--primary-light) 100%);
    color: white;
    position: relative;
    overflow: hidden;
}

.btn-primary:hover {
    transform: translateY(-2px);
    box-shadow: var(--shadow-lg);
}

.btn-primary:active {
    transform: translateY(0);
}

.btn-icon {
    margin-right: 8px;
}

/* Dashboard Layout */
.dashboard-layout {
    display: flex;
    min-height: 100vh;
    background: var(--gray-100);
}

/* Sidebar */
.sidebar {
    width: 280px;
    background: white;
    box-shadow: var(--shadow-md);
    display: flex;
    flex-direction: column;
    position: fixed;
    height: 100vh;
    z-index: 100;
}

.sidebar-header {
    padding: 32px 24px;
    border-bottom: 1px solid var(--gray-200);
}

.brand {
    display: flex;
    align-items: center;
    gap: 12px;
}

.brand-icon {
    font-size: 24px;
    color: var(--primary);
}

.brand-text h2 {
    font-size: 20px;
    font-weight: 700;
    color: var(--primary-dark);
    line-height: 1.2;
}

.brand-text span {
    font-size: 12px;
    color: var(--gray-500);
    font-weight: 500;
}

.sidebar-nav {
    padding: 24px 16px;
    flex: 1;
    overflow-y: auto;
}

.nav-item {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 14px 16px;
    color: var(--gray-600);
    text-decoration: none;
    border-radius: 10px;
    margin-bottom: 8px;
    transition: all 0.3s;
    font-weight: 500;
}

.nav-item:hover {
    background: var(--gray-100);
    color: var(--primary);
    transform: translateX(4px);
}

.nav-item.active {
    background: linear-gradient(135deg, rgba(124, 58, 237, 0.1) 0%, rgba(139, 92, 246, 0.1) 100%);
    color: var(--primary);
    font-weight: 600;
}

.nav-item.active .nav-icon {
    background: var(--primary);
    color: white;
}

.nav-icon {
    width: 36px;
    height: 36px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--gray-100);
    border-radius: 10px;
    transition: all 0.3s;
}

.sidebar-footer {
    padding: 20px 24px;
    border-top: 1px solid var(--gray-200);
}

.user-info {
    display: flex;
    align-items: center;
    gap: 12px;
}

.user-avatar {
    width: 40px;
    height: 40px;
    background: linear-gradient(135deg, var(--primary) 0%, var(--primary-light) 100%);
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    color: white;
    font-weight: 600;
}

.user-details h4 {
    font-size: 14px;
    font-weight: 600;
    color: var(--gray-800);
}

.user-details span {
    font-size: 12px;
    color: var(--gray-500);
}

/* Main Content */
.main-content {
    flex: 1;
    margin-left: 280px;
    padding: 32px;
    min-height: 100vh;
}

/* Header */
.header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 32px;
    padding-bottom: 24px;
    border-bottom: 1px solid var(--gray-200);
}

.header-left h1 {
    font-size: 28px;
    font-weight: 700;
    color: var(--gray-900);
    margin-bottom: 8px;
}

.header-left p {
    color: var(--gray-500);
    font-size: 14px;
}

.header-actions {
    display: flex;
    gap: 12px;
    align-items: center;
}

/* Stats Grid */
.stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
    gap: 24px;
    margin-bottom: 32px;
}

.stat-card {
    background: white;
    border-radius: 16px;
    padding: 24px;
    box-shadow: var(--shadow);
    border: 1px solid var(--gray-200);
    transition: all 0.3s;
    position: relative;
    overflow: hidden;
}

.stat-card:hover {
    transform: translateY(-4px);
    box-shadow: var(--shadow-lg);
    border-color: var(--primary-light);
}

.stat-card::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    width: 4px;
    height: 100%;
    background: var(--primary);
}

.stat-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
}

.stat-icon {
    width: 48px;
    height: 48px;
    border-radius: 12px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 20px;
}

.stat-icon.users { background: rgba(16, 185, 129, 0.1); color: var(--secondary); }
.stat-icon.revenue { background: rgba(124, 58, 237, 0.1); color: var(--primary); }
.stat-icon.messages { background: rgba(59, 130, 246, 0.1); color: var(--info); }
.stat-icon.active { background: rgba(245, 158, 11, 0.1); color: var(--warning); }

.stat-trend {
    font-size: 12px;
    padding: 4px 8px;
    border-radius: 6px;
    font-weight: 600;
}

.trend-up { background: rgba(16, 185, 129, 0.1); color: var(--secondary); }
.trend-down { background: rgba(239, 68, 68, 0.1); color: var(--danger); }

.stat-value {
    font-size: 32px;
    font-weight: 800;
    color: var(--gray-900);
    margin: 8px 0;
    line-height: 1;
}

.stat-label {
    color: var(--gray-500);
    font-size: 14px;
    font-weight: 500;
}

/* Users Grid */
.users-grid {
    background: white;
    border-radius: 16px;
    padding: 32px;
    box-shadow: var(--shadow);
    margin-bottom: 32px;
}

.section-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 24px;
}

.section-header h2 {
    font-size: 20px;
    font-weight: 700;
    color: var(--gray-900);
}

.search-box {
    position: relative;
    width: 300px;
}

.search-box i {
    position: absolute;
    left: 16px;
    top: 50%;
    transform: translateY(-50%);
    color: var(--gray-400);
}

.search-box input {
    width: 100%;
    padding: 12px 16px 12px 44px;
    border: 2px solid var(--gray-200);
    border-radius: 10px;
    font-size: 14px;
    transition: all 0.3s;
}

.search-box input:focus {
    outline: none;
    border-color: var(--primary);
    box-shadow: 0 0 0 3px rgba(124, 58, 237, 0.1);
}

.users-list {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 16px;
}

.user-card {
    border: 1px solid var(--gray-200);
    border-radius: 12px;
    padding: 20px;
    transition: all 0.3s;
    cursor: pointer;
    background: white;
}

.user-card:hover {
    border-color: var(--primary);
    transform: translateY(-4px);
    box-shadow: var(--shadow-lg);
}

.user-card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
}

.user-identity {
    display: flex;
    align-items: center;
    gap: 12px;
}

.user-avatar-small {
    width: 40px;
    height: 40px;
    border-radius: 10px;
    background: linear-gradient(135deg, var(--primary) 0%, var(--primary-light) 100%);
    display: flex;
    align-items: center;
    justify-content: center;
    color: white;
    font-weight: 600;
    font-size: 14px;
}

.user-details-small h4 {
    font-size: 15px;
    font-weight: 600;
    color: var(--gray-900);
    margin-bottom: 2px;
}

.user-details-small span {
    font-size: 12px;
    color: var(--gray-500);
}

.user-status {
    padding: 6px 12px;
    border-radius: 20px;
    font-size: 12px;
    font-weight: 600;
    display: inline-flex;
    align-items: center;
    gap: 4px;
}

.status-online {
    background: rgba(16, 185, 129, 0.1);
    color: var(--secondary);
}

.status-offline {
    background: rgba(239, 68, 68, 0.1);
    color: var(--danger);
}

.user-stats {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 12px;
    margin-top: 16px;
    padding-top: 16px;
    border-top: 1px solid var(--gray-200);
}

.stat-item {
    text-align: center;
}

.stat-item .value {
    font-size: 18px;
    font-weight: 700;
    color: var(--gray-900);
    display: block;
}

.stat-item .label {
    font-size: 11px;
    color: var(--gray-500);
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

/* Chat Interface */
.chat-container {
    display: flex;
    height: calc(100vh - 120px);
    background: white;
    border-radius: 16px;
    overflow: hidden;
    box-shadow: var(--shadow-lg);
}

.chat-sidebar {
    width: 320px;
    border-right: 1px solid var(--gray-200);
    display: flex;
    flex-direction: column;
}

.chat-header {
    padding: 24px;
    border-bottom: 1px solid var(--gray-200);
    background: white;
}

.chat-messages {
    flex: 1;
    padding: 24px;
    overflow-y: auto;
    background: linear-gradient(180deg, #f8fafc 0%, #ffffff 100%);
}

.message {
    margin-bottom: 20px;
    animation: fadeIn 0.3s ease-out;
}

@keyframes fadeIn {
    from { opacity: 0; transform: translateY(10px); }
    to { opacity: 1; transform: translateY(0); }
}

.message-content {
    padding: 16px;
    border-radius: 16px;
    position: relative;
    max-width: 70%;
    word-wrap: break-word;
}

.message-user {
    margin-left: auto;
}

.message-user .message-content {
    background: linear-gradient(135deg, var(--primary) 0%, var(--primary-light) 100%);
    color: white;
    border-top-right-radius: 4px;
}

.message-sophia .message-content {
    background: white;
    border: 1px solid var(--gray-200);
    border-top-left-radius: 4px;
}

.message-sender {
    font-weight: 600;
    font-size: 13px;
    margin-bottom: 6px;
}

.message-user .message-sender {
    text-align: right;
    color: rgba(255, 255, 255, 0.9);
}

.message-sophia .message-sender {
    color: var(--primary);
}

.message-text {
    line-height: 1.5;
    font-size: 14.5px;
}

.message-time {
    font-size: 11px;
    color: var(--gray-400);
    margin-top: 6px;
    text-align: right;
}

.message-user .message-time {
    color: rgba(255, 255, 255, 0.7);
}

/* Responsive */
@media (max-width: 1024px) {
    .sidebar {
        width: 80px;
    }
    
    .sidebar .brand-text,
    .sidebar .nav-item span,
    .sidebar .user-details {
        display: none;
    }
    
    .main-content {
        margin-left: 80px;
    }
}

@media (max-width: 768px) {
    .dashboard-layout {
        flex-direction: column;
    }
    
    .sidebar {
        width: 100%;
        height: auto;
        position: relative;
    }
    
    .main-content {
        margin-left: 0;
        padding: 20px;
    }
    
    .stats-grid {
        grid-template-columns: 1fr;
    }
    
    .users-list {
        grid-template-columns: 1fr;
    }
    
    .search-box {
        width: 100%;
    }
}

/* Loading States */
.loading {
    opacity: 0.7;
    pointer-events: none;
}

.loading::after {
    content: '';
    display: block;
    width: 20px;
    height: 20px;
    border: 2px solid var(--gray-300);
    border-top-color: var(--primary);
    border-radius: 50%;
    animation: spin 1s linear infinite;
    margin: 20px auto;
}

@keyframes spin {
    to { transform: rotate(360deg); }
}

/* Toast Notifications */
.toast {
    position: fixed;
    top: 24px;
    right: 24px;
    padding: 16px 24px;
    background: white;
    border-radius: 12px;
    box-shadow: var(--shadow-lg);
    border-left: 4px solid var(--primary);
    display: flex;
    align-items: center;
    gap: 12px;
    z-index: 1000;
    animation: slideInRight 0.3s ease-out;
}

@keyframes slideInRight {
    from {
        opacity: 0;
        transform: translateX(100%);
    }
    to {
        opacity: 1;
        transform: translateX(0);
    }
}

.toast.success { border-left-color: var(--secondary); }
.toast.error { border-left-color: var(--danger); }
.toast.warning { border-left-color: var(--warning); }
.toast.info { border-left-color: var(--info); }

.toast-icon {
    font-size: 20px;
}

.toast.success .toast-icon { color: var(--secondary); }
.toast.error .toast-icon { color: var(--danger); }
.toast.warning .toast-icon { color: var(--warning); }
.toast.info .toast-icon { color: var(--info); }

.toast-content h4 {
    font-size: 14px;
    font-weight: 600;
    margin-bottom: 4px;
}

.toast-content p {
    font-size: 13px;
    color: var(--gray-500);
}
"""

# ================= UTILITIES =================
def check_redis():
    """Verifica conexão com Redis"""
    if not redis_client:
        return False
    try:
        redis_client.ping()
        return True
    except:
        return False

def get_users():
    """Obtém todos os usuários"""
    if not check_redis():
        return []
    
    users = set()
    try:
        for key in redis_client.scan_iter("chatlog:*"):
            parts = key.split(":")
            if len(parts) > 1:
                users.add(parts[1])
    except:
        pass
    return sorted(list(users), reverse=True)

def get_user_stats(uid):
    """Estatísticas do usuário"""
    stats = {
        "total_messages": 0,
        "user_messages": 0,
        "sophia_messages": 0,
        "last_activity": None,
        "status": "offline"
    }
    
    if not check_redis():
        return stats
    
    try:
        logs = redis_client.lrange(f"chatlog:{uid}", 0, -1)
        stats["total_messages"] = len(logs)
        
        if logs:
            for log in logs[-10:]:  # Verifica últimos 10 logs
                try:
                    msg = json.loads(log)
                    if msg["role"] == "user":
                        stats["user_messages"] += 1
                    else:
                        stats["sophia_messages"] += 1
                    
                    msg_time = datetime.fromisoformat(msg["ts"])
                    if not stats["last_activity"] or msg_time > stats["last_activity"]:
                        stats["last_activity"] = msg_time
                except:
                    continue
            
            # Verificar se está ativo (últimos 15 minutos)
            if stats["last_activity"]:
                time_diff = datetime.now() - stats["last_activity"]
                if time_diff < timedelta(minutes=15):
                    stats["status"] = "online"
    except:
        pass
    
    return stats

def get_revenue_data():
    """Dados de receita"""
    revenue = {
        "total": 0,
        "today": 0,
        "week": 0,
        "transactions": []
    }
    
    if not check_redis():
        return revenue
    
    try:
        logs = redis_client.lrange("revenue", 0, -1)
        today = datetime.now().date()
        week_ago = today - timedelta(days=7)
        
        for log in logs:
            try:
                if ":" in log:
                    amount_str, date_str = log.split(":", 1)
                    amount = float(amount_str.replace("R$", "").strip())
                    log_date = datetime.strptime(date_str.strip(), "%Y-%m-%d %H:%M:%S")
                    
                    revenue["total"] += amount
                    if log_date.date() == today:
                        revenue["today"] += amount
                    if log_date.date() >= week_ago:
                        revenue["week"] += amount
                    
                    revenue["transactions"].append({
                        "amount": amount,
                        "date": log_date,
                        "formatted": f"R${amount:.2f} em {log_date.strftime('%d/%m %H:%M')}"
                    })
            except:
                continue
        
        # Ordenar transações por data (mais recente primeiro)
        revenue["transactions"].sort(key=lambda x: x["date"], reverse=True)
    except:
        pass
    
    return revenue

# ================= ROUTES =================
@app.route("/")
def home():
    """Página inicial (redireciona para login)"""
    return redirect("/login")

@app.route("/login", methods=["GET", "POST"])
def login():
    """Página de login"""
    if request.method == "POST":
        password = request.form.get("password", "").strip()
        if password == ADMIN_PASSWORD:
            session["authenticated"] = True
            session["login_time"] = datetime.now().isoformat()
            session["user_agent"] = request.headers.get("User-Agent", "")
            return redirect("/dashboard")
        
        # Senha incorreta
        error_html = """
        <div class="login-container">
            <div class="login-card">
                <div class="logo">
                    <div class="logo-icon">
                        <i class="fas fa-brain"></i>
                    </div>
                    <h1>Sophia AI</h1>
                    <p>Painel Administrativo</p>
                </div>
                
                <div style="background: rgba(239, 68, 68, 0.1); padding: 16px; border-radius: 12px; margin-bottom: 24px; border: 1px solid rgba(239, 68, 68, 0.2);">
                    <div style="display: flex; align-items: center; gap: 12px; color: #ef4444;">
                        <i class="fas fa-exclamation-circle"></i>
                        <div>
                            <h4 style="font-size: 14px; font-weight: 600; margin-bottom: 4px;">Senha incorreta</h4>
                            <p style="font-size: 13px; opacity: 0.8;">Verifique a senha e tente novamente.</p>
                        </div>
                    </div>
                </div>
                
                <form method="post">
                    <div class="input-group">
                        <label for="password">
                            <i class="fas fa-key"></i> Senha Administrativa
                        </label>
                        <div class="input-wrapper">
                            <i class="fas fa-lock"></i>
                            <input type="password" id="password" name="password" placeholder="Digite sua senha" required autofocus>
                        </div>
                    </div>
                    <button type="submit" class="btn btn-primary">
                        <i class="fas fa-sign-in-alt btn-icon"></i>
                        Acessar Painel
                    </button>
                </form>
                
                <div style="margin-top: 32px; padding-top: 24px; border-top: 1px solid var(--gray-200); text-align: center;">
                    <p style="font-size: 12px; color: var(--gray-500);">
                        <i class="fas fa-info-circle"></i>
                        Sistema de monitoramento Sophia AI
                    </p>
                </div>
            </div>
        </div>
        """
        return render_template_string(BASE_TEMPLATE.format(
            title="Login",
            css=MODERN_CSS,
            content=error_html,
            scripts=""
        ))
    
    # GET request - mostrar formulário de login
    login_html = """
    <div class="login-container">
        <div class="login-card">
            <div class="logo">
                <div class="logo-icon">
                    <i class="fas fa-brain"></i>
                </div>
                <h1>Sophia AI</h1>
                <p>Painel Administrativo</p>
            </div>
            
            <form method="post">
                <div class="input-group">
                    <label for="password">
                        <i class="fas fa-key"></i> Senha Administrativa
                    </label>
                    <div class="input-wrapper">
                        <i class="fas fa-lock"></i>
                        <input type="password" id="password" name="password" placeholder="Digite sua senha" required autofocus>
                    </div>
                </div>
                <button type="submit" class="btn btn-primary">
                    <i class="fas fa-sign-in-alt btn-icon"></i>
                    Acessar Painel
                </button>
            </form>
            
            <div style="margin-top: 32px; padding-top: 24px; border-top: 1px solid var(--gray-200); text-align: center;">
                <p style="font-size: 12px; color: var(--gray-500);">
                    <i class="fas fa-info-circle"></i>
                    Sistema de monitoramento Sophia AI
                </p>
            </div>
        </div>
    </div>
    """
    
    return render_template_string(BASE_TEMPLATE.format(
        title="Login",
        css=MODERN_CSS,
        content=login_html,
        scripts="""
        // Foco automático no campo de senha
        document.addEventListener('DOMContentLoaded', function() {
            document.getElementById('password').focus();
        });
        """
    ))

@app.route("/dashboard")
def dashboard():
    """Dashboard principal"""
    if not session.get("authenticated"):
        return redirect("/login")
    
    users = get_users()
    revenue = get_revenue_data()
    
    # Calcular estatísticas
    total_users = len(users)
    online_users = sum(1 for uid in users if get_user_stats(uid)["status"] == "online")
    total_messages = sum(get_user_stats(uid)["total_messages"] for uid in users)
    
    # Gerar HTML dos usuários
    users_html = ""
    for uid in users[:50]:  # Limitar a 50 usuários por performance
        stats = get_user_stats(uid)
        status_class = "status-online" if stats["status"] == "online" else "status-offline"
        status_icon = "fas fa-circle" if stats["status"] == "online" else "far fa-circle"
        status_text = "Online" if stats["status"] == "online" else "Offline"
        
        last_active = stats["last_activity"]
        if last_active:
            time_diff = datetime.now() - last_active
            if time_diff < timedelta(minutes=1):
                last_seen = "Agora mesmo"
            elif time_diff < timedelta(hours=1):
                last_seen = f"{int(time_diff.seconds / 60)} min atrás"
            elif time_diff < timedelta(days=1):
                last_seen = f"{int(time_diff.seconds / 3600)}h atrás"
            else:
                last_seen = last_active.strftime("%d/%m %H:%M")
        else:
            last_seen = "Nunca"
        
        users_html += f"""
        <div class="user-card" onclick="window.location.href='/chat/{uid}'">
            <div class="user-card-header">
                <div class="user-identity">
                    <div class="user-avatar-small">
                        {uid[:2].upper()}
                    </div>
                    <div class="user-details-small">
                        <h4>User {uid[:8]}...</h4>
                        <span>{last_seen}</span>
                    </div>
                </div>
                <div class="user-status {status_class}">
                    <i class="{status_icon}"></i>
                    {status_text}
                </div>
            </div>
            <div class="user-stats">
                <div class="stat-item">
                    <span class="value">{stats['total_messages']}</span>
                    <span class="label">Total</span>
                </div>
                <div class="stat-item">
                    <span class="value">{stats['user_messages']}</span>
                    <span class="label">Usuário</span>
                </div>
                <div class="stat-item">
                    <span class="value">{stats['sophia_messages']}</span>
                    <span class="label">Sophia</span>
                </div>
            </div>
        </div>
        """
    
    # Se não houver usuários
    if not users_html:
        users_html = """
        <div style="text-align: center; padding: 60px 20px;">
            <i class="fas fa-users" style="font-size: 48px; color: var(--gray-300); margin-bottom: 16px;"></i>
            <h3 style="color: var(--gray-500); margin-bottom: 8px;">Nenhum usuário encontrado</h3>
            <p style="color: var(--gray-400);">Os usuários aparecerão aqui quando começarem a conversar com o bot.</p>
        </div>
        """
    
    dashboard_html = f"""
    <div class="dashboard-layout">
        <!-- Sidebar -->
        <div class="sidebar">
            <div class="sidebar-header">
                <div class="brand">
                    <div class="brand-icon">
                        <i class="fas fa-brain"></i>
                    </div>
                    <div class="brand-text">
                        <h2>Sophia AI</h2>
                        <span>Admin Panel</span>
                    </div>
                </div>
            </div>
            
            <div class="sidebar-nav">
                <a href="/dashboard" class="nav-item active">
                    <div class="nav-icon">
                        <i class="fas fa-tachometer-alt"></i>
                    </div>
                    <span>Dashboard</span>
                </a>
                <a href="/revenue" class="nav-item">
                    <div class="nav-icon">
                        <i class="fas fa-chart-line"></i>
                    </div>
                    <span>Receita</span>
                </a>
                <a href="/users" class="nav-item">
                    <div class="nav-icon">
                        <i class="fas fa-users"></i>
                    </div>
                    <span>Usuários</span>
                </a>
                <a href="/logs" class="nav-item">
                    <div class="nav-icon">
                        <i class="fas fa-history"></i>
                    </div>
                    <span>Logs</span>
                </a>
                <a href="/settings" class="nav-item">
                    <div class="nav-icon">
                        <i class="fas fa-cog"></i>
                    </div>
                    <span>Configurações</span>
                </a>
            </div>
            
            <div class="sidebar-footer">
                <div class="user-info">
                    <div class="user-avatar">
                        <i class="fas fa-user-shield"></i>
                    </div>
                    <div class="user-details">
                        <h4>Administrador</h4>
                        <span>{datetime.now().strftime('%H:%M')}</span>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- Main Content -->
        <div class="main-content">
            <div class="header">
                <div class="header-left">
                    <h1>Dashboard Sophia AI</h1>
                    <p>Monitoramento em tempo real • {datetime.now().strftime('%d/%m/%Y %H:%M')}</p>
                </div>
                <div class="header-actions">
                    <div style="display: flex; align-items: center; gap: 8px; background: white; padding: 8px 16px; border-radius: 10px; border: 1px solid var(--gray-200);">
                        <div style="width: 8px; height: 8px; border-radius: 50%; background: {'#10b981' if check_redis() else '#ef4444'};"></div>
                        <span style="font-size: 12px; font-weight: 500; color: var(--gray-600);">
                            {'Redis Conectado' if check_redis() else 'Redis Offline'}
                        </span>
                    </div>
                    <a href="/logout" class="btn" style="background: var(--gray-100); color: var(--gray-700); padding: 10px 20px;">
                        <i class="fas fa-sign-out-alt"></i>
                        Sair
                    </a>
                </div>
            </div>
            
            <!-- Stats Grid -->
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-header">
                        <div>
                            <div class="stat-label">Total de Usuários</div>
                        </div>
                        <div class="stat-icon users">
                            <i class="fas fa-users"></i>
                        </div>
                    </div>
                    <div class="stat-value">{total_users}</div>
                    <div class="stat-trend trend-up">+{online_users} online</div>
                </div>
                
                <div class="stat-card">
                    <div class="stat-header">
                        <div>
                            <div class="stat-label">Receita Total</div>
                        </div>
                        <div class="stat-icon revenue">
                            <i class="fas fa-money-bill-wave"></i>
                        </div>
                    </div>
                    <div class="stat-value">R${revenue['total']:.2f}</div>
                    <div class="stat-trend trend-up">+R${revenue['today']:.2f} hoje</div>
                </div>
                
                <div class="stat-card">
                    <div class="stat-header">
                        <div>
                            <div class="stat-label">Total Mensagens</div>
                        </div>
                        <div class="stat-icon messages">
                            <i class="fas fa-comments"></i>
                        </div>
                    </div>
                    <div class="stat-value">{total_messages}</div>
                    <div class="stat-label">Troca de mensagens</div>
                </div>
                
                <div class="stat-card">
                    <div class="stat-header">
                        <div>
                            <div class="stat-label">Usuários Ativos</div>
                        </div>
                        <div class="stat-icon active">
                            <i class="fas fa-bolt"></i>
                        </div>
                    </div>
                    <div class="stat-value">{online_users}</div>
                    <div class="stat-label">Últimos 15 minutos</div>
                </div>
            </div>
            
            <!-- Users Section -->
            <div class="users-grid">
                <div class="section-header">
                    <h2><i class="fas fa-comment-dots"></i> Conversas Ativas</h2>
                    <div class="search-box">
                        <i class="fas fa-search"></i>
                        <input type="text" id="searchUsers" placeholder="Buscar usuários..." 
                               onkeyup="filterUsers(this.value)">
                    </div>
                </div>
                <div class="users-list" id="usersList">
                    {users_html}
                </div>
            </div>
            
            <!-- Quick Stats -->
            <div style="display: grid; grid-template-columns: 2fr 1fr; gap: 24px;">
                <div style="background: white; border-radius: 16px; padding: 24px; box-shadow: var(--shadow);">
                    <h3 style="margin-bottom: 16px; font-size: 16px; font-weight: 600; color: var(--gray-800);">
                        <i class="fas fa-chart-bar"></i> Atividade Recente
                    </h3>
                    <div style="height: 200px; display: flex; align-items: center; justify-content: center; color: var(--gray-400);">
                        <div style="text-align: center;">
                            <i class="fas fa-chart-line" style="font-size: 48px; margin-bottom: 16px;"></i>
                            <p>Gráfico de atividade será implementado em breve</p>
                        </div>
                    </div>
                </div>
                
                <div style="background: white; border-radius: 16px; padding: 24px; box-shadow: var(--shadow);">
                    <h3 style="margin-bottom: 16px; font-size: 16px; font-weight: 600; color: var(--gray-800);">
                        <i class="fas fa-bell"></i> Sistema
                    </h3>
                    <div style="display: flex; flex-direction: column; gap: 12px;">
                        <div style="display: flex; align-items: center; gap: 12px; padding: 12px; background: var(--gray-50); border-radius: 10px;">
                            <div style="width: 8px; height: 8px; border-radius: 50%; background: #10b981;"></div>
                            <span style="font-size: 14px;">Painel operacional</span>
                        </div>
                        <div style="display: flex; align-items: center; gap: 12px; padding: 12px; background: var(--gray-50); border-radius: 10px;">
                            <div style="width: 8px; height: 8px; border-radius: 50%; background: {'#10b981' if check_redis() else '#ef4444'};"></div>
                            <span style="font-size: 14px;">{'Redis conectado' if check_redis() else 'Redis desconectado'}</span>
                        </div>
                        <div style="display: flex; align-items: center; gap: 12px; padding: 12px; background: var(--gray-50); border-radius: 10px;">
                            <div style="width: 8px; height: 8px; border-radius: 50%; background: #10b981;"></div>
                            <span style="font-size: 14px;">API online</span>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    """
    
    return render_template_string(BASE_TEMPLATE.format(
        title="Dashboard",
        css=MODERN_CSS,
        content=dashboard_html,
        scripts="""
        function filterUsers(search) {
            const users = document.querySelectorAll('.user-card');
            search = search.toLowerCase();
            
            users.forEach(user => {
                const text = user.textContent.toLowerCase();
                user.style.display = text.includes(search) ? 'block' : 'none';
            });
        }
        
        // Auto-refresh a cada 30 segundos
        setTimeout(() => {
            window.location.reload();
        }, 30000);
        
        // Mostrar notificação de atualização
        let refreshCount = 0;
        setInterval(() => {
            refreshCount++;
            if (refreshCount >= 30) {
                showToast('Atualizando dados...', 'info');
                refreshCount = 0;
            }
        }, 1000);
        
        function showToast(message, type = 'info') {
            const toast = document.createElement('div');
            toast.className = `toast ${type}`;
            toast.innerHTML = `
                <div class="toast-icon">
                    <i class="fas fa-${type === 'success' ? 'check-circle' : type === 'error' ? 'exclamation-circle' : type === 'warning' ? 'exclamation-triangle' : 'info-circle'}"></i>
                </div>
                <div class="toast-content">
                    <h4>${type.charAt(0).toUpperCase() + type.slice(1)}</h4>
                    <p>${message}</p>
                </div>
            `;
            
            document.body.appendChild(toast);
            
            setTimeout(() => {
                toast.remove();
            }, 3000);
        }
        """
    ))

@app.route("/chat/<uid>")
def chat_view(uid):
    """Visualização de chat específico"""
    if not session.get("authenticated"):
        return redirect("/login")
    
    if not check_redis():
        return "Redis não conectado", 500
    
    # Buscar mensagens
    messages = []
    try:
        logs = redis_client.lrange(f"chatlog:{uid}", 0, -1)
        for log in logs:
            try:
                msg = json.loads(log)
                messages.append(msg)
            except:
                continue
    except:
        pass
    
    # Gerar HTML das mensagens
    messages_html = ""
    for msg in messages[-100:]:  # Limitar a 100 últimas mensagens
        ts = datetime.fromisoformat(msg["ts"])
        time_str = ts.strftime("%H:%M")
        
        if msg["role"] == "user":
            messages_html += f"""
            <div class="message message-user">
                <div class="message-content">
                    <div class="message-sender">Usuário</div>
                    <div class="message-text">{msg["text"]}</div>
                    <div class="message-time">{time_str}</div>
                </div>
            </div>
            """
        else:
            messages_html += f"""
            <div class="message message-sophia">
                <div class="message-content">
                    <div class="message-sender">Sophia AI 💖</div>
                    <div class="message-text">{msg["text"]}</div>
                    <div class="message-time">{time_str}</div>
                </div>
            </div>
            """
    
    stats = get_user_stats(uid)
    
    chat_html = f"""
    <div class="dashboard-layout">
        <!-- Sidebar -->
        <div class="sidebar">
            <div class="sidebar-header">
                <div class="brand">
                    <div class="brand-icon">
                        <i class="fas fa-comments"></i>
                    </div>
                    <div class="brand-text">
                        <h2>Chat</h2>
                        <span>User: {uid[:8]}...</span>
                    </div>
                </div>
            </div>
            
            <div class="sidebar-nav">
                <a href="/dashboard" class="nav-item">
                    <div class="nav-icon">
                        <i class="fas fa-arrow-left"></i>
                    </div>
                    <span>Voltar</span>
                </a>
                <div class="nav-item active">
                    <div class="nav-icon">
                        <i class="fas fa-user"></i>
                    </div>
                    <span>Usuário</span>
                </div>
                <a href="#" class="nav-item" onclick="exportChat('{uid}')">
                    <div class="nav-icon">
                        <i class="fas fa-download"></i>
                    </div>
                    <span>Exportar</span>
                </a>
                <a href="#" class="nav-item" onclick="clearChat('{uid}')" style="color: var(--danger);">
                    <div class="nav-icon">
                        <i class="fas fa-trash"></i>
                    </div>
                    <span>Limpar Chat</span>
                </a>
            </div>
            
            <div class="sidebar-footer">
                <div class="user-info">
                    <div class="user-avatar" style="background: linear-gradient(135deg, #f59e0b 0%, #f97316 100%);">
                        {uid[:2].upper()}
                    </div>
                    <div class="user-details">
                        <h4>User {uid[:8]}...</h4>
                        <span>{'Online' if stats['status'] == 'online' else 'Offline'}</span>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- Main Content -->
        <div class="main-content" style="padding: 0;">
            <div class="chat-container">
                <div class="chat-header" style="background: linear-gradient(135deg, var(--primary) 0%, var(--primary-light) 100%); color: white; padding: 24px;">
                    <div>
                        <h3 style="font-size: 20px; font-weight: 700; margin-bottom: 4px;">
                            <i class="fas fa-user-circle"></i> Conversa com {uid}
                        </h3>
                        <div style="font-size: 14px; opacity: 0.9;">
                            {stats['total_messages']} mensagens • {stats['user_messages']} do usuário • {stats['sophia_messages']} da Sophia
                        </div>
                    </div>
                    <div style="display: flex; gap: 12px;">
                        <button class="btn" style="background: rgba(255,255,255,0.2); color: white;" onclick="location.reload()">
                            <i class="fas fa-sync-alt"></i> Atualizar
                        </button>
                        <a href="/dashboard" class="btn" style="background: rgba(255,255,255,0.1); color: white;">
                            <i class="fas fa-home"></i> Dashboard
                        </a>
                    </div>
                </div>
                
                <div class="chat-messages" id="chatMessages">
                    {messages_html if messages_html else '''
                    <div style="text-align: center; padding: 60px 20px;">
                        <i class="fas fa-comment-slash" style="font-size: 48px; color: var(--gray-300); margin-bottom: 16px;"></i>
                        <h3 style="color: var(--gray-500); margin-bottom: 8px;">Nenhuma mensagem</h3>
                        <p style="color: var(--gray-400);">Este usuário ainda não trocou mensagens com o bot.</p>
                    </div>
                    '''}
                </div>
            </div>
        </div>
    </div>
    """
    
    return render_template_string(BASE_TEMPLATE.format(
        title=f"Chat - {uid[:8]}...",
        css=MODERN_CSS,
        content=chat_html,
        scripts=f"""
        // Auto-scroll para o final
        const chatMessages = document.getElementById('chatMessages');
        if (chatMessages) {{
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }}
        
        // Auto-refresh a cada 10 segundos
        setInterval(() => {{
            location.reload();
        }}, 10000);
        
        function exportChat(uid) {{
            alert('Exportação do chat ' + uid + ' será implementada em breve.');
        }}
        
        function clearChat(uid) {{
            if (confirm('Tem certeza que deseja limpar todo o histórico deste chat?')) {{
                fetch('/api/chat/' + uid + '/clear', {{ method: 'POST' }})
                    .then(response => response.json())
                    .then(data => {{
                        if (data.success) {{
                            alert('Chat limpo com sucesso!');
                            location.reload();
                        }} else {{
                            alert('Erro ao limpar chat: ' + data.error);
                        }}
                    }});
            }}
        }}
        """
    ))

@app.route("/revenue")
def revenue():
    """Página de receita"""
    if not session.get("authenticated"):
        return redirect("/login")
    
    revenue_data = get_revenue_data()
    
    transactions_html = ""
    for tx in revenue_data["transactions"][:20]:  # Últimas 20 transações
        transactions_html += f"""
        <div style="display: flex; justify-content: space-between; align-items: center; padding: 16px; border-bottom: 1px solid var(--gray-200); transition: background 0.3s; border-radius: 8px;">
            <div>
                <div style="font-weight: 600; color: var(--gray-800);">Pagamento recebido</div>
                <div style="font-size: 12px; color: var(--gray-500);">{tx['date'].strftime('%d/%m/%Y %H:%M')}</div>
            </div>
            <div style="font-weight: 700; color: var(--secondary); font-size: 18px;">R${tx['amount']:.2f}</div>
        </div>
        """
    
    if not transactions_html:
        transactions_html = """
        <div style="text-align: center; padding: 60px 20px;">
            <i class="fas fa-money-bill-wave" style="font-size: 48px; color: var(--gray-300); margin-bottom: 16px;"></i>
            <h3 style="color: var(--gray-500); margin-bottom: 8px;">Nenhuma transação</h3>
            <p style="color: var(--gray-400);">As transações aparecerão aqui quando ocorrerem.</p>
        </div>
        """
    
    revenue_html = f"""
    <div class="dashboard-layout">
        <!-- Sidebar -->
        <div class="sidebar">
            <div class="sidebar-header">
                <div class="brand">
                    <div class="brand-icon">
                        <i class="fas fa-chart-line"></i>
                    </div>
                    <div class="brand-text">
                        <h2>Receita</h2>
                        <span>Financeiro</span>
                    </div>
                </div>
            </div>
            
            <div class="sidebar-nav">
                <a href="/dashboard" class="nav-item">
                    <div class="nav-icon">
                        <i class="fas fa-arrow-left"></i>
                    </div>
                    <span>Voltar</span>
                </a>
                <a href="/revenue" class="nav-item active">
                    <div class="nav-icon">
                        <i class="fas fa-chart-line"></i>
                    </div>
                    <span>Visão Geral</span>
                </a>
                <a href="/revenue/export" class="nav-item">
                    <div class="nav-icon">
                        <i class="fas fa-file-export"></i>
                    </div>
                    <span>Exportar</span>
                </a>
                <a href="/revenue/settings" class="nav-item">
                    <div class="nav-icon">
                        <i class="fas fa-cog"></i>
                    </div>
                    <span>Configurações</span>
                </a>
            </div>
        </div>
        
        <!-- Main Content -->
        <div class="main-content">
            <div class="header">
                <div class="header-left">
                    <h1>Relatório de Receita</h1>
                    <p>Análise financeira • Atualizado em {datetime.now().strftime('%H:%M')}</p>
                </div>
                <div class="header-actions">
                    <button class="btn btn-primary" onclick="window.print()">
                        <i class="fas fa-print"></i> Imprimir
                    </button>
                </div>
            </div>
            
            <!-- Stats -->
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-header">
                        <div>
                            <div class="stat-label">Receita Total</div>
                        </div>
                        <div class="stat-icon revenue">
                            <i class="fas fa-money-bill-wave"></i>
                        </div>
                    </div>
                    <div class="stat-value">R${revenue_data['total']:.2f}</div>
                    <div class="stat-label">Acumulado</div>
                </div>
                
                <div class="stat-card">
                    <div class="stat-header">
                        <div>
                            <div class="stat-label">Hoje</div>
                        </div>
                        <div class="stat-icon revenue">
                            <i class="fas fa-calendar-day"></i>
                        </div>
                    </div>
                    <div class="stat-value">R${revenue_data['today']:.2f}</div>
                    <div class="stat-label">Receita diária</div>
                </div>
                
                <div class="stat-card">
                    <div class="stat-header">
                        <div>
                            <div class="stat-label">Esta Semana</div>
                        </div>
                        <div class="stat-icon revenue">
                            <i class="fas fa-calendar-week"></i>
                        </div>
                    </div>
                    <div class="stat-value">R${revenue_data['week']:.2f}</div>
                    <div class="stat-label">Últimos 7 dias</div>
                </div>
            </div>
            
            <!-- Transactions -->
            <div style="background: white; border-radius: 16px; padding: 32px; box-shadow: var(--shadow); margin-top: 32px;">
                <div class="section-header">
                    <h2><i class="fas fa-history"></i> Transações Recentes</h2>
                    <div class="search-box">
                        <i class="fas fa-search"></i>
                        <input type="text" placeholder="Buscar transações...">
                    </div>
                </div>
                <div style="margin-top: 24px; max-height: 500px; overflow-y: auto;">
                    {transactions_html}
                </div>
            </div>
        </div>
    </div>
    """
    
    return render_template_string(BASE_TEMPLATE.format(
        title="Receita",
        css=MODERN_CSS,
        content=revenue_html,
        scripts=""
    ))

@app.route("/logout")
def logout():
    """Logout do sistema"""
    session.clear()
    return redirect("/login")

@app.route("/health")
def health():
    """Endpoint de saúde para Railway"""
    return jsonify({
        "status": "healthy" if check_redis() else "degraded",
        "redis": "connected" if check_redis() else "disconnected",
        "timestamp": datetime.now().isoformat(),
        "service": "sophia-admin-panel"
    })

# ================= API ENDPOINTS =================
@app.route("/api/users")
def api_users():
    """API para listar usuários"""
    if not session.get("authenticated"):
        return jsonify({"error": "Unauthorized"}), 401
    
    users = get_users()
    return jsonify({
        "count": len(users),
        "users": [{"id": uid, "stats": get_user_stats(uid)} for uid in users[:100]]
    })

@app.route("/api/chat/<uid>/messages")
def api_chat_messages(uid):
    """API para mensagens do chat"""
    if not session.get("authenticated"):
        return jsonify({"error": "Unauthorized"}), 401
    
    if not check_redis():
        return jsonify({"error": "Redis not connected"}), 500
    
    messages = []
    try:
        logs = redis_client.lrange(f"chatlog:{uid}", 0, -1)
        for log in logs:
            try:
                messages.append(json.loads(log))
            except:
                continue
    except:
        pass
    
    return jsonify({
        "user_id": uid,
        "count": len(messages),
        "messages": messages[-50:]  # Últimas 50 mensagens
    })

@app.route("/api/stats")
def api_stats():
    """API para estatísticas gerais"""
    if not session.get("authenticated"):
        return jsonify({"error": "Unauthorized"}), 401
    
    users = get_users()
    revenue = get_revenue_data()
    
    return jsonify({
        "users": {
            "total": len(users),
            "online": sum(1 for uid in users if get_user_stats(uid)["status"] == "online"),
            "offline": sum(1 for uid in users if get_user_stats(uid)["status"] == "offline")
        },
        "revenue": revenue,
        "messages": {
            "total": sum(get_user_stats(uid)["total_messages"] for uid in users),
            "user": sum(get_user_stats(uid)["user_messages"] for uid in users),
            "sophia": sum(get_user_stats(uid)["sophia_messages"] for uid in users)
        },
        "system": {
            "redis": check_redis(),
            "timestamp": datetime.now().isoformat()
        }
    })

# ================= ERROR HANDLERS =================
@app.errorhandler(404)
def not_found(error):
    return render_template_string(BASE_TEMPLATE.format(
        title="404 - Página não encontrada",
        css=MODERN_CSS,
        content="""
        <div class="login-container">
            <div class="login-card">
                <div class="logo">
                    <div class="logo-icon" style="color: var(--danger);">
                        <i class="fas fa-exclamation-triangle"></i>
                    </div>
                    <h1>404</h1>
                    <p>Página não encontrada</p>
                </div>
                <div style="text-align: center; margin-top: 32px;">
                    <p style="color: var(--gray-500); margin-bottom: 24px;">
                        A página que você está procurando não existe ou foi movida.
                    </p>
                    <a href="/dashboard" class="btn btn-primary" style="width: auto; padding: 12px 24px;">
                        <i class="fas fa-home"></i> Voltar ao Dashboard
                    </a>
                </div>
            </div>
        </div>
        """,
        scripts=""
    )), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template_string(BASE_TEMPLATE.format(
        title="500 - Erro interno",
        css=MODERN_CSS,
        content="""
        <div class="login-container">
            <div class="login-card">
                <div class="logo">
                    <div class="logo-icon" style="color: var(--danger);">
                        <i class="fas fa-server"></i>
                    </div>
                    <h1>500</h1>
                    <p>Erro interno do servidor</p>
                </div>
                <div style="text-align: center; margin-top: 32px;">
                    <p style="color: var(--gray-500); margin-bottom: 24px;">
                        Ocorreu um erro interno. Tente novamente em alguns instantes.
                    </p>
                    <div style="display: flex; gap: 12px; justify-content: center;">
                        <a href="/dashboard" class="btn btn-primary" style="width: auto; padding: 12px 24px;">
                            <i class="fas fa-redo"></i> Tentar novamente
                        </a>
                        <a href="/" class="btn" style="width: auto; padding: 12px 24px; background: var(--gray-100); color: var(--gray-700);">
                            <i class="fas fa-home"></i> Página inicial
                        </a>
                    </div>
                </div>
            </div>
        </div>
        """,
        scripts=""
    )), 500

# ================= MAIN =================
if __name__ == "__main__":
    logger.info(f"🚀 Iniciando Sophia Admin Panel na porta {PORT}")
    logger.info(f"📊 Redis: {'✅ Conectado' if check_redis() else '❌ Desconectado'}")
    logger.info(f"🔐 Admin Password: {ADMIN_PASSWORD[:3]}...")
    
    app.run(
        host="0.0.0.0",
        port=PORT,
        debug=False  # Debug desligado para produção
    )
