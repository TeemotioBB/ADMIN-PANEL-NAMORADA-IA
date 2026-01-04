#!/usr/bin/env python3
"""
🎯 Sophia Admin Panel v2 - Conversas em Tempo Real
Visualize TODAS as conversas, ações e eventos dos usuários
INCLUI: Mensagens após trava, cliques em botões, erros, etc.
"""

import os
import json
import redis
from datetime import datetime, timedelta
from flask import Flask, request, redirect, session, jsonify
import logging
import time
import html

# ================= CONFIG =================
REDIS_URL = os.environ.get("REDIS_URL", "redis://default:DcddfJOHLXZdFPjEhRjHeodNgdtrsevl@shuttle.proxy.rlwy.net:12241")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")
SECRET_KEY = os.environ.get("SECRET_KEY", "sophia-secret-" + str(int(time.time())))
PORT = int(os.environ.get("PORT", 8081))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Inicializar Redis
redis_client = None
try:
    redis_client = redis.from_url(REDIS_URL, decode_responses=True, socket_connect_timeout=5, socket_timeout=5)
    redis_client.ping()
    logger.info("✅ Redis conectado com sucesso")
except Exception as e:
    logger.error(f"❌ Erro ao conectar ao Redis: {e}")
    redis_client = None

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=2)

# ================= STYLES (ATUALIZADO COM NOVOS TIPOS) =================
STYLES = """
<style>
* { 
    margin: 0; 
    padding: 0; 
    box-sizing: border-box; 
}
body { 
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: #333; 
    min-height: 100vh;
}
.container { 
    max-width: 1400px; 
    margin: 0 auto; 
    padding: 20px; 
}
.header { 
    background: rgba(255,255,255,0.95); 
    color: #667eea; 
    padding: 25px; 
    border-radius: 15px; 
    margin-bottom: 20px; 
    box-shadow: 0 10px 40px rgba(0,0,0,0.2);
}
.stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 15px;
    margin-bottom: 20px;
}
.stat-card {
    background: white;
    padding: 20px;
    border-radius: 10px;
    box-shadow: 0 5px 15px rgba(0,0,0,0.1);
    text-align: center;
}
.stat-number {
    font-size: 32px;
    font-weight: bold;
    color: #667eea;
}
.stat-label {
    color: #666;
    font-size: 14px;
    margin-top: 5px;
}
.user-list { 
    display: grid; 
    grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); 
    gap: 15px;
    margin-bottom: 20px;
}
.user-card { 
    background: white;
    padding: 20px; 
    border-radius: 12px; 
    cursor: pointer; 
    transition: all 0.3s; 
    box-shadow: 0 5px 15px rgba(0,0,0,0.1);
    border-left: 4px solid #667eea;
}
.user-card:hover { 
    transform: translateY(-5px); 
    box-shadow: 0 10px 30px rgba(0,0,0,0.2); 
}
.user-id {
    font-weight: bold;
    color: #667eea;
    font-size: 16px;
    margin-bottom: 10px;
    word-break: break-all;
}
.user-stats {
    display: flex;
    justify-content: space-between;
    font-size: 13px;
    color: #666;
    margin-top: 10px;
    padding-top: 10px;
    border-top: 1px solid #eee;
}
.status { 
    display: inline-block; 
    padding: 4px 12px; 
    border-radius: 20px; 
    font-size: 11px; 
    font-weight: bold; 
    text-transform: uppercase;
}
.status-online { background: #10b981; color: white; }
.status-offline { background: #ef4444; color: white; }
.status-idle { background: #f59e0b; color: white; }
.badge-vip {
    background: gold;
    color: #333;
    padding: 3px 8px;
    border-radius: 12px;
    font-size: 10px;
    font-weight: bold;
    margin-left: 5px;
}
.badge-locked {
    background: #ef4444;
    color: white;
    padding: 3px 8px;
    border-radius: 12px;
    font-size: 10px;
    font-weight: bold;
    margin-left: 5px;
}
.chat-view {
    background: white;
    border-radius: 15px;
    padding: 0;
    box-shadow: 0 10px 40px rgba(0,0,0,0.2);
    height: calc(100vh - 200px);
    display: flex;
    flex-direction: column;
}
.chat-header {
    padding: 20px;
    border-bottom: 2px solid #f0f0f0;
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.chat-messages { 
    flex: 1; 
    padding: 20px; 
    overflow-y: auto; 
    background: #f8f9fa;
}
.message { 
    margin-bottom: 12px; 
    padding: 12px 16px; 
    border-radius: 18px; 
    max-width: 80%;
    word-wrap: break-word;
    animation: slideIn 0.3s ease-out;
}
@keyframes slideIn {
    from { opacity: 0; transform: translateY(10px); }
    to { opacity: 1; transform: translateY(0); }
}
/* Mensagem do usuário */
.message-user { 
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white; 
    margin-left: auto; 
    border-bottom-right-radius: 4px; 
}
/* Resposta da Sophia */
.message-sophia { 
    background: white; 
    color: #333; 
    border: 1px solid #e0e0e0;
    border-bottom-left-radius: 4px; 
}
/* Ações do usuário (cliques, /start, etc) */
.message-action {
    background: #e3f2fd;
    color: #1565c0;
    border: 1px solid #90caf9;
    margin: 0 auto;
    text-align: center;
    font-size: 12px;
    max-width: 90%;
    border-radius: 8px;
}
/* Informações do sistema */
.message-info {
    background: #f3e5f5;
    color: #7b1fa2;
    border: 1px solid #ce93d8;
    margin: 0 auto;
    text-align: center;
    font-size: 12px;
    max-width: 90%;
    border-radius: 8px;
}
/* Erros */
.message-error {
    background: #ffebee;
    color: #c62828;
    border: 1px solid #ef9a9a;
    margin: 0 auto;
    text-align: center;
    font-size: 12px;
    max-width: 90%;
    border-radius: 8px;
}
/* Bloqueios */
.message-blocked {
    background: #fff3e0;
    color: #e65100;
    border: 1px solid #ffcc80;
    margin: 0 auto;
    text-align: center;
    font-size: 12px;
    max-width: 90%;
    border-radius: 8px;
}
/* Sistema genérico */
.message-system {
    background: #fff3cd;
    color: #856404;
    border: 1px solid #ffc107;
    margin: 0 auto;
    text-align: center;
    font-size: 12px;
    max-width: 90%;
    border-radius: 8px;
}
.message-sender { 
    font-weight: bold; 
    margin-bottom: 5px; 
    font-size: 12px;
    opacity: 0.9;
}
.message-time { 
    font-size: 10px; 
    opacity: 0.7; 
    margin-top: 5px; 
}
.btn { 
    display: inline-block; 
    padding: 12px 24px; 
    background: #667eea; 
    color: white; 
    text-decoration: none; 
    border-radius: 8px; 
    border: none; 
    cursor: pointer; 
    font-weight: 500;
    transition: all 0.3s;
}
.btn:hover { 
    background: #5a67d8; 
    transform: translateY(-2px);
}
.btn-secondary { background: #6c757d; }
.btn-secondary:hover { background: #5a6268; }
.search-box { 
    width: 100%; 
    padding: 12px 20px; 
    border: 2px solid #e0e0e0; 
    border-radius: 10px; 
    margin-bottom: 20px;
    font-size: 14px;
}
.search-box:focus {
    outline: none;
    border-color: #667eea;
}
.login-container {
    display: flex;
    justify-content: center;
    align-items: center;
    height: 100vh;
}
.login-card {
    background: white;
    padding: 40px;
    border-radius: 15px;
    box-shadow: 0 20px 60px rgba(0,0,0,0.3);
    width: 100%;
    max-width: 400px;
}
.form-group {
    margin-bottom: 20px;
}
.form-group label {
    display: block;
    margin-bottom: 8px;
    font-weight: 600;
}
.form-group input {
    width: 100%;
    padding: 12px;
    border: 2px solid #e0e0e0;
    border-radius: 8px;
    font-size: 14px;
}
.form-group input:focus {
    outline: none;
    border-color: #667eea;
}
.empty-state {
    text-align: center;
    padding: 60px 20px;
    color: #666;
}
.legend {
    background: white;
    padding: 15px;
    border-radius: 10px;
    margin-bottom: 15px;
    display: flex;
    flex-wrap: wrap;
    gap: 15px;
    justify-content: center;
    font-size: 12px;
}
.legend-item {
    display: flex;
    align-items: center;
    gap: 5px;
}
.legend-color {
    width: 16px;
    height: 16px;
    border-radius: 4px;
}
</style>
"""

# ================= UTILITIES =================
def check_redis():
    if not redis_client:
        return False
    try:
        redis_client.ping()
        return True
    except:
        return False

def get_all_users():
    if not check_redis():
        return []
    users = set()
    try:
        for key in redis_client.scan_iter("chatlog:*"):
            parts = key.split(":")
            if len(parts) > 1:
                users.add(parts[1])
    except Exception as e:
        logger.error(f"Erro ao buscar usuários: {e}")
    return sorted(list(users), reverse=True)

def get_user_messages(uid):
    if not check_redis():
        return []
    messages = []
    try:
        key = f"chatlog:{uid}"
        logs = redis_client.lrange(key, 0, -1)
        for log in logs:
            msg = parse_chat_message(log)
            if msg:
                messages.append(msg)
    except Exception as e:
        logger.error(f"Erro ao buscar mensagens: {e}")
    return messages

def parse_chat_message(log_line):
    """Parseia linha: [HH:MM:SS] ROLE: message"""
    try:
        if log_line.startswith('['):
            end_bracket = log_line.find(']')
            if end_bracket > 0:
                timestamp_str = log_line[1:end_bracket]
                remaining = log_line[end_bracket+2:]
                
                colon_pos = remaining.find(':')
                if colon_pos > 0:
                    role = remaining[:colon_pos].strip().lower()
                    text = remaining[colon_pos+1:].strip()
                    
                    # Mapeia roles para tipos visuais
                    role_map = {
                        "user": "user",
                        "sophia": "assistant",
                        "system": "system",
                        "action": "action",
                        "info": "info",
                        "error": "error",
                        "blocked": "blocked",
                    }
                    
                    return {
                        "role": role_map.get(role, "system"),
                        "original_role": role,
                        "text": text,
                        "time": timestamp_str
                    }
    except:
        pass
    return None

def get_user_stats(uid):
    stats = {
        "total_messages": 0,
        "user_messages": 0,
        "sophia_messages": 0,
        "actions": 0,
        "last_activity": None,
        "status": "offline",
        "is_vip": False,
        "is_locked": False
    }
    
    # Verifica VIP
    try:
        vip_until = redis_client.get(f"vip:{uid}")
        if vip_until:
            stats["is_vip"] = datetime.fromisoformat(vip_until) > datetime.now()
    except:
        pass
    
    # Verifica se está travado
    try:
        from datetime import date
        count = int(redis_client.get(f"count:{uid}:{date.today()}") or 0)
        stats["is_locked"] = count >= 15 and not stats["is_vip"]
    except:
        pass
    
    messages = get_user_messages(uid)
    stats["total_messages"] = len(messages)
    
    for msg in messages:
        role = msg.get("role", "")
        if role == "user":
            stats["user_messages"] += 1
        elif role == "assistant":
            stats["sophia_messages"] += 1
        elif role in ["action", "info"]:
            stats["actions"] += 1
        
        if role == "user":
            try:
                now = datetime.now()
                parts = msg.get("time", "").split(':')
                if len(parts) >= 2:
                    msg_time = datetime(now.year, now.month, now.day, 
                                       int(parts[0]), int(parts[1]), 
                                       int(parts[2]) if len(parts) > 2 else 0)
                    if not stats["last_activity"] or msg_time > stats["last_activity"]:
                        stats["last_activity"] = msg_time
            except:
                pass
    
    if stats["last_activity"]:
        diff = datetime.now() - stats["last_activity"]
        if diff < timedelta(minutes=5):
            stats["status"] = "online"
        elif diff < timedelta(minutes=30):
            stats["status"] = "idle"
    
    return stats

def get_global_stats():
    users = get_all_users()
    total = len(users)
    vips = online = msgs = locked = 0
    
    for uid in users:
        s = get_user_stats(uid)
        if s["is_vip"]: vips += 1
        if s["status"] == "online": online += 1
        if s["is_locked"]: locked += 1
        msgs += s["total_messages"]
    
    return {
        "total_users": total,
        "vip_users": vips,
        "online_users": online,
        "locked_users": locked,
        "total_messages": msgs
    }

# ================= ROUTES =================
@app.route("/")
def home():
    return redirect("/login")

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        if request.form.get("password", "").strip() == ADMIN_PASSWORD:
            session["authenticated"] = True
            session.permanent = True
            return redirect("/dashboard")
        error = "Senha incorreta!"
    
    return f"""
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Login - Sophia Admin</title>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
        {STYLES}
    </head>
    <body>
        <div class="login-container">
            <div class="login-card">
                <div style="text-align: center; margin-bottom: 30px;">
                    <h1 style="color: #667eea;"><i class="fas fa-robot"></i> Sophia AI</h1>
                    <p style="color: #666;">Painel de Monitoramento v2</p>
                </div>
                {f'<div style="background: #fee; color: #c33; padding: 10px; border-radius: 5px; margin-bottom: 20px;">{error}</div>' if error else ''}
                <form method="post">
                    <div class="form-group">
                        <label><i class="fas fa-lock"></i> Senha:</label>
                        <input type="password" name="password" placeholder="Digite a senha" required autofocus>
                    </div>
                    <button type="submit" class="btn" style="width: 100%;">
                        <i class="fas fa-sign-in-alt"></i> Entrar
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
        return redirect("/login")
    
    if not check_redis():
        return "<h1>❌ Redis não conectado</h1>", 500
    
    filter_type = request.args.get('filter', 'recent')
    page = int(request.args.get('page', 1))
    per_page = 20
    
    all_users = get_all_users()
    stats = get_global_stats()
    
    filtered = []
    for uid in all_users:
        s = get_user_stats(uid)
        
        if filter_type == 'vip' and not s['is_vip']:
            continue
        elif filter_type == 'online' and s['status'] != 'online':
            continue
        elif filter_type == 'locked' and not s['is_locked']:
            continue
        elif filter_type == 'recent':
            if s['last_activity']:
                if datetime.now() - s['last_activity'] > timedelta(hours=24):
                    continue
            else:
                continue
        
        filtered.append((uid, s))
    
    filtered.sort(key=lambda x: x[1]['last_activity'] or datetime.min, reverse=True)
    
    total_pages = (len(filtered) + per_page - 1) // per_page
    page_users = filtered[(page-1)*per_page : page*per_page]
    
    users_html = ""
    for uid, s in page_users:
        status_class = f"status-{s['status']}"
        status_emoji = {"online": "🟢", "idle": "🟡", "offline": "🔴"}.get(s['status'], "🔴")
        vip_badge = '<span class="badge-vip">👑 VIP</span>' if s['is_vip'] else ''
        locked_badge = '<span class="badge-locked">🔒 TRAVADO</span>' if s['is_locked'] else ''
        
        last_seen = "Nunca"
        if s['last_activity']:
            diff = datetime.now() - s['last_activity']
            if diff < timedelta(minutes=1):
                last_seen = "Agora"
            elif diff < timedelta(hours=1):
                last_seen = f"{int(diff.seconds/60)}min"
            elif diff < timedelta(days=1):
                last_seen = f"{int(diff.seconds/3600)}h"
            else:
                last_seen = s['last_activity'].strftime("%d/%m %H:%M")
        
        users_html += f"""
        <div class="user-card" onclick="window.location.href='/chat/{uid}'">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div class="user-id">
                    <i class="fas fa-user-circle"></i> {uid[:16]}{'...' if len(uid) > 16 else ''}
                    {vip_badge}{locked_badge}
                </div>
                <span class="status {status_class}">{status_emoji}</span>
            </div>
            <div class="user-stats">
                <span><i class="fas fa-comments"></i> {s['total_messages']} msgs</span>
                <span><i class="fas fa-bolt"></i> {s['actions']} ações</span>
                <span><i class="fas fa-clock"></i> {last_seen}</span>
            </div>
        </div>
        """
    
    if not users_html:
        users_html = '<div class="empty-state"><h3>Nenhum usuário encontrado</h3></div>'
    
    return f"""
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Dashboard - Sophia Admin</title>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
        {STYLES}
    </head>
    <body>
        <div class="container">
            <div class="header">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <h1><i class="fas fa-chart-line"></i> Dashboard Sophia AI v2</h1>
                        <p style="margin-top: 5px; opacity: 0.8;">Monitoramento Completo • {datetime.now().strftime('%d/%m/%Y %H:%M')}</p>
                    </div>
                    <a href="/logout" class="btn btn-secondary"><i class="fas fa-sign-out-alt"></i> Sair</a>
                </div>
            </div>
            
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-number">{stats['total_users']}</div>
                    <div class="stat-label"><i class="fas fa-users"></i> Total</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number" style="color: #10b981;">{stats['online_users']}</div>
                    <div class="stat-label"><i class="fas fa-circle"></i> Online</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number" style="color: #f59e0b;">{stats['vip_users']}</div>
                    <div class="stat-label"><i class="fas fa-crown"></i> VIPs</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number" style="color: #ef4444;">{stats['locked_users']}</div>
                    <div class="stat-label"><i class="fas fa-lock"></i> Travados</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number" style="color: #667eea;">{stats['total_messages']}</div>
                    <div class="stat-label"><i class="fas fa-comment-dots"></i> Mensagens</div>
                </div>
            </div>
            
            <div style="background: white; border-radius: 10px; padding: 20px; margin-bottom: 20px;">
                <div style="display: flex; gap: 10px; flex-wrap: wrap;">
                    <a href="/dashboard?filter=recent" class="btn {'btn-secondary' if filter_type != 'recent' else ''}">
                        <i class="fas fa-clock"></i> Recentes
                    </a>
                    <a href="/dashboard?filter=online" class="btn {'btn-secondary' if filter_type != 'online' else ''}">
                        <i class="fas fa-circle"></i> Online
                    </a>
                    <a href="/dashboard?filter=locked" class="btn {'btn-secondary' if filter_type != 'locked' else ''}">
                        <i class="fas fa-lock"></i> Travados
                    </a>
                    <a href="/dashboard?filter=vip" class="btn {'btn-secondary' if filter_type != 'vip' else ''}">
                        <i class="fas fa-crown"></i> VIPs
                    </a>
                    <a href="/dashboard?filter=all" class="btn {'btn-secondary' if filter_type != 'all' else ''}">
                        <i class="fas fa-list"></i> Todos
                    </a>
                </div>
            </div>
            
            <div class="user-list">{users_html}</div>
            
            <div style="text-align: center;">
                <button class="btn" onclick="location.reload()">
                    <i class="fas fa-sync-alt"></i> Atualizar
                </button>
            </div>
        </div>
        <script>setTimeout(() => location.reload(), 30000);</script>
    </body>
    </html>
    """

@app.route("/chat/<uid>")
def chat_view(uid):
    if not session.get("authenticated"):
        return redirect("/login")
    
    messages = get_user_messages(uid)
    stats = get_user_stats(uid)
    
    # Gerar HTML das mensagens
    messages_html = ""
    for msg in messages:
        role = msg.get("role", "system")
        text = html.escape(msg.get("text", ""))
        time_str = msg.get("time", "")
        
        if role == "user":
            messages_html += f"""
            <div class="message message-user">
                <div class="message-sender">👤 USUÁRIO</div>
                <div>{text}</div>
                <div class="message-time">{time_str}</div>
            </div>
            """
        elif role == "assistant":
            messages_html += f"""
            <div class="message message-sophia">
                <div class="message-sender">🤖 SOPHIA</div>
                <div>{text}</div>
                <div class="message-time">{time_str}</div>
            </div>
            """
        elif role == "action":
            messages_html += f"""
            <div class="message message-action">
                <strong>⚡ AÇÃO:</strong> {text}
                <div class="message-time">{time_str}</div>
            </div>
            """
        elif role == "info":
            messages_html += f"""
            <div class="message message-info">
                <strong>ℹ️ INFO:</strong> {text}
                <div class="message-time">{time_str}</div>
            </div>
            """
        elif role == "error":
            messages_html += f"""
            <div class="message message-error">
                <strong>❌ ERRO:</strong> {text}
                <div class="message-time">{time_str}</div>
            </div>
            """
        elif role == "blocked":
            messages_html += f"""
            <div class="message message-blocked">
                <strong>🚫 BLOQUEADO:</strong> {text}
                <div class="message-time">{time_str}</div>
            </div>
            """
        else:
            messages_html += f"""
            <div class="message message-system">
                <strong>📋 SISTEMA:</strong> {text}
                <div class="message-time">{time_str}</div>
            </div>
            """
    
    if not messages_html:
        messages_html = '<div class="empty-state"><h3>Nenhuma mensagem</h3></div>'
    
    vip_badge = '👑 VIP' if stats['is_vip'] else '💬 FREE'
    locked_badge = '🔒 TRAVADO' if stats['is_locked'] else '✅ ATIVO'
    status_emoji = {"online": "🟢", "idle": "🟡", "offline": "🔴"}.get(stats['status'], "🔴")
    
    return f"""
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Chat - {uid[:12]}</title>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
        {STYLES}
    </head>
    <body>
        <div class="container">
            <div class="header">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <h1><i class="fas fa-comments"></i> {uid[:20]}{'...' if len(uid) > 20 else ''}</h1>
                        <p>{status_emoji} {stats['status'].upper()} • {vip_badge} • {locked_badge} • {stats['total_messages']} msgs</p>
                    </div>
                    <div>
                        <a href="/dashboard" class="btn btn-secondary"><i class="fas fa-arrow-left"></i> Voltar</a>
                        <button class="btn" onclick="location.reload()"><i class="fas fa-sync-alt"></i></button>
                    </div>
                </div>
            </div>
            
            <div class="legend">
                <div class="legend-item"><div class="legend-color" style="background: linear-gradient(135deg, #667eea, #764ba2);"></div> Usuário</div>
                <div class="legend-item"><div class="legend-color" style="background: white; border: 1px solid #ccc;"></div> Sophia</div>
                <div class="legend-item"><div class="legend-color" style="background: #e3f2fd;"></div> Ações</div>
                <div class="legend-item"><div class="legend-color" style="background: #f3e5f5;"></div> Info</div>
                <div class="legend-item"><div class="legend-color" style="background: #ffebee;"></div> Erros</div>
                <div class="legend-item"><div class="legend-color" style="background: #fff3e0;"></div> Bloqueios</div>
            </div>
            
            <div class="chat-view">
                <div class="chat-header">
                    <code>{uid}</code>
                    <span style="font-size: 12px; color: #666;">Atualiza a cada 10s</span>
                </div>
                <div class="chat-messages" id="chat">{messages_html}</div>
            </div>
        </div>
        <script>
            document.getElementById('chat').scrollTop = document.getElementById('chat').scrollHeight;
            setTimeout(() => location.reload(), 10000);
        </script>
    </body>
    </html>
    """

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

@app.route("/health")
def health():
    return jsonify({
        "status": "healthy" if check_redis() else "degraded",
        "redis": "connected" if check_redis() else "disconnected",
        "timestamp": datetime.now().isoformat()
    })

if __name__ == "__main__":
    logger.info(f"🚀 Admin Panel v2 na porta {PORT}")
    app.run(host="0.0.0.0", port=PORT, debug=False)
