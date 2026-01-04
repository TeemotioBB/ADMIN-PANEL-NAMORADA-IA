#!/usr/bin/env python3
"""
🎯 Sophia Admin Panel v2 - Conversas em Tempo Real (CORRIGIDO)
Visualize TODAS as conversas, ações e eventos dos usuários
CORREÇÕES: Auto-refresh inteligente, filtros corretos, status online preciso
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

# NOVOS PARÂMETROS
ONLINE_THRESHOLD = 20  # minutos para considerar online
IDLE_THRESHOLD = 40    # minutos para considerar idle (ausente)
OFFLINE_THRESHOLD = 60 # minutos para considerar offline
RECENT_THRESHOLD = 24  # horas para filtro "recentes"

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

# ================= STYLES (MELHORADO) =================
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
    position: relative;
}
.user-card:hover { 
    transform: translateY(-5px); 
    box-shadow: 0 10px 30px rgba(0,0,0,0.2); 
}
.user-card.online {
    border-left-color: #10b981;
}
.user-card.idle {
    border-left-color: #f59e0b;
}
.user-card.offline {
    border-left-color: #ef4444;
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
.last-message {
    font-size: 12px;
    color: #999;
    margin-top: 8px;
    font-style: italic;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
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
.message-user { 
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white; 
    margin-left: auto; 
    border-bottom-right-radius: 4px; 
}
.message-sophia { 
    background: white; 
    color: #333; 
    border: 1px solid #e0e0e0;
    border-bottom-left-radius: 4px; 
}
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
.auto-refresh-control {
    background: white;
    padding: 15px;
    border-radius: 10px;
    margin-bottom: 20px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 15px;
}
.toggle-switch {
    position: relative;
    display: inline-block;
    width: 50px;
    height: 24px;
}
.toggle-switch input {
    opacity: 0;
    width: 0;
    height: 0;
}
.slider {
    position: absolute;
    cursor: pointer;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background-color: #ccc;
    transition: .4s;
    border-radius: 24px;
}
.slider:before {
    position: absolute;
    content: "";
    height: 18px;
    width: 18px;
    left: 3px;
    bottom: 3px;
    background-color: white;
    transition: .4s;
    border-radius: 50%;
}
input:checked + .slider {
    background-color: #667eea;
}
input:checked + .slider:before {
    transform: translateX(26px);
}
.pagination {
    display: flex;
    justify-content: center;
    gap: 10px;
    margin: 20px 0;
}
.pagination a {
    padding: 8px 16px;
    background: white;
    border-radius: 8px;
    text-decoration: none;
    color: #667eea;
    transition: all 0.3s;
}
.pagination a:hover {
    background: #667eea;
    color: white;
}
.pagination a.active {
    background: #667eea;
    color: white;
}
</style>
"""

# ================= UTILITIES (CORRIGIDO) =================
def check_redis():
    if not redis_client:
        return False
    try:
        redis_client.ping()
        return True
    except:
        return False

def get_all_users():
    """Retorna lista de usuários únicos com timestamp"""
    if not check_redis():
        return []
    users = {}
    try:
        for key in redis_client.scan_iter("chatlog:*"):
            parts = key.split(":")
            if len(parts) > 1:
                uid = parts[1]
                if uid not in users:
                    users[uid] = None
    except Exception as e:
        logger.error(f"Erro ao buscar usuários: {e}")
    return list(users.keys())

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
                    
                    # Tenta converter timestamp para datetime
                    try:
                        now = datetime.now()
                        parts = timestamp_str.split(':')
                        if len(parts) >= 2:
                            msg_time = datetime(now.year, now.month, now.day, 
                                              int(parts[0]), int(parts[1]), 
                                              int(parts[2]) if len(parts) > 2 else 0)
                            # Se a hora for no futuro (passou da meia-noite), assume dia anterior
                            if msg_time > now:
                                msg_time -= timedelta(days=1)
                        else:
                            msg_time = None
                    except:
                        msg_time = None
                    
                    return {
                        "role": role_map.get(role, "system"),
                        "original_role": role,
                        "text": text,
                        "time": timestamp_str,
                        "datetime": msg_time
                    }
    except:
        pass
    return None

def get_user_stats(uid):
    """Calcula estatísticas precisas do usuário"""
    stats = {
        "total_messages": 0,
        "user_messages": 0,
        "sophia_messages": 0,
        "actions": 0,
        "last_activity": None,
        "last_message_preview": None,
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
    
    last_user_msg = None
    
    for msg in messages:
        role = msg.get("role", "")
        if role == "user":
            stats["user_messages"] += 1
            last_user_msg = msg.get("text", "")
        elif role == "assistant":
            stats["sophia_messages"] += 1
        elif role in ["action", "info"]:
            stats["actions"] += 1
        
        # Atualiza última atividade APENAS com mensagens do usuário
        if role == "user" and msg.get("datetime"):
            if not stats["last_activity"] or msg["datetime"] > stats["last_activity"]:
                stats["last_activity"] = msg["datetime"]
    
    # Preview da última mensagem
    if last_user_msg:
        stats["last_message_preview"] = last_user_msg[:50] + "..." if len(last_user_msg) > 50 else last_user_msg
    
    # Calcula status PRECISO baseado na última atividade
    if stats["last_activity"]:
        diff = datetime.now() - stats["last_activity"]
        minutes_diff = diff.total_seconds() / 60
        
        if minutes_diff < ONLINE_THRESHOLD:
            stats["status"] = "online"
        elif minutes_diff < IDLE_THRESHOLD:
            stats["status"] = "idle"
        elif minutes_diff < OFFLINE_THRESHOLD:
            stats["status"] = "offline"
        else:
            stats["status"] = "offline"
    
    return stats

def get_global_stats():
    users = get_all_users()
    total = len(users)
    vips = online = idle = msgs = locked = 0
    
    for uid in users:
        s = get_user_stats(uid)
        if s["is_vip"]: vips += 1
        if s["status"] == "online": online += 1
        elif s["status"] == "idle": idle += 1
        if s["is_locked"]: locked += 1
        msgs += s["total_messages"]
    
    return {
        "total_users": total,
        "vip_users": vips,
        "online_users": online,
        "idle_users": idle,
        "locked_users": locked,
        "total_messages": msgs
    }

def format_last_seen(last_activity):
    """Formata timestamp de última atividade"""
    if not last_activity:
        return "Nunca"
    
    diff = datetime.now() - last_activity
    seconds = diff.total_seconds()
    
    if seconds < 60:
        return "Agora"
    elif seconds < 3600:
        return f"{int(seconds/60)}min"
    elif seconds < 86400:
        return f"{int(seconds/3600)}h"
    elif seconds < 604800:
        dias = int(seconds/86400)
        return f"{dias}d"
    else:
        return last_activity.strftime("%d/%m")

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
                    <p style="color: #666;">Painel de Monitoramento v2.1</p>
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
    
    filter_type = request.args.get('filter', 'online')
    page = int(request.args.get('page', 1))
    per_page = 24
    
    all_users = get_all_users()
    stats = get_global_stats()
    
    # Calcula stats de todos os usuários primeiro
    users_with_stats = []
    for uid in all_users:
        s = get_user_stats(uid)
        users_with_stats.append((uid, s))
    
    # Aplica filtros
    filtered = []
    for uid, s in users_with_stats:
        if filter_type == 'vip' and not s['is_vip']:
            continue
        elif filter_type == 'online' and s['status'] != 'online':
            continue
        elif filter_type == 'idle' and s['status'] != 'idle':
            continue
        elif filter_type == 'locked' and not s['is_locked']:
            continue
        elif filter_type == 'recent':
            if s['last_activity']:
                hours_ago = (datetime.now() - s['last_activity']).total_seconds() / 3600
                if hours_ago > RECENT_THRESHOLD:
                    continue
            else:
                continue
        
        filtered.append((uid, s))
    
    # Ordena por última atividade (mais recente primeiro)
    filtered.sort(key=lambda x: x[1]['last_activity'] or datetime.min, reverse=True)
    
    total_pages = max(1, (len(filtered) + per_page - 1) // per_page)
    page = min(page, total_pages)  # Garante que a página não exceda o total
    page_users = filtered[(page-1)*per_page : page*per_page]
    
    users_html = ""
    for uid, s in page_users:
        status_class = f"status-{s['status']}"
        card_class = s['status']
        status_emoji = {"online": "🟢", "idle": "🟡", "offline": "🔴"}.get(s['status'], "🔴")
        vip_badge = '<span class="badge-vip">👑 VIP</span>' if s['is_vip'] else ''
        locked_badge = '<span class="badge-locked">🔒 TRAVADO</span>' if s['is_locked'] else ''
        
        last_seen = format_last_seen(s['last_activity'])
        
        last_msg_html = ""
        if s['last_message_preview']:
            last_msg_html = f'<div class="last-message">💬 {html.escape(s["last_message_preview"])}</div>'
        
        users_html += f"""
        <div class="user-card {card_class}" onclick="window.location.href='/chat/{uid}'">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div class="user-id">
                    <i class="fas fa-user-circle"></i> {uid[:16]}{'...' if len(uid) > 16 else ''}
                    {vip_badge}{locked_badge}
                </div>
                <span class="status {status_class}">{status_emoji}</span>
            </div>
            {last_msg_html}
            <div class="user-stats">
                <span><i class="fas fa-comments"></i> {s['total_messages']}</span>
                <span><i class="fas fa-bolt"></i> {s['actions']}</span>
                <span><i class="fas fa-clock"></i> {last_seen}</span>
            </div>
        </div>
        """
    
    if not users_html:
        users_html = f'<div class="empty-state"><h3>😔 Nenhum usuário {filter_type}</h3><p>Tente outro filtro</p></div>'
    
    # Paginação
    pagination_html = '<div class="pagination">'
    if page > 1:
        pagination_html += f'<a href="/dashboard?filter={filter_type}&page={page-1}"><i class="fas fa-chevron-left"></i></a>'
    
    # Mostra 5 páginas ao redor da atual
    start_page = max(1, page - 2)
    end_page = min(total_pages, page + 2)
    
    for p in range(start_page, end_page + 1):
        active = 'active' if p == page else ''
        pagination_html += f'<a href="/dashboard?filter={filter_type}&page={p}" class="{active}">{p}</a>'
    
    if page < total_pages:
        pagination_html += f'<a href="/dashboard?filter={filter_type}&page={page+1}"><i class="fas fa-chevron-right"></i></a>'
    pagination_html += '</div>'
    
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
                        <h1><i class="fas fa-chart-line"></i> Dashboard Sophia AI v2.1</h1>
                        <p style="margin-top: 5px; opacity: 0.8;">Monitoramento em Tempo Real • {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}</p>
                    </div>
                    <a href="/logout" class="btn btn-secondary"><i class="fas fa-sign-out-alt"></i> Sair</a>
                </div>
            </div>
            
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-number">{stats['total_users']}</div>
                    <div class="stat-label"><i class="fas fa-users"></i> Total de Usuários</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number" style="color: #10b981;">{stats['online_users']}</div>
                    <div class="stat-label"><i class="fas fa-circle"></i> Online Agora</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number" style="color: #f59e0b;">{stats['idle_users']}</div>
                    <div class="stat-label"><i class="fas fa-moon"></i> Ausentes</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number" style="color: #f59e0b;">{stats['vip_users']}</div>
                    <div class="stat-label"><i class="fas fa-crown"></i> VIPs Ativos</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number" style="color: #ef4444;">{stats['locked_users']}</div>
                    <div class="stat-label"><i class="fas fa-lock"></i> Travados Hoje</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number" style="color: #667eea;">{stats['total_messages']}</div>
                    <div class="stat-label"><i class="fas fa-comment-dots"></i> Total de Msgs</div>
                </div>
            </div>
            
            <div style="background: white; border-radius: 10px; padding: 20px; margin-bottom: 20px;">
                <div style="display: flex; gap: 10px; flex-wrap: wrap; justify-content: center;">
                    <a href="/dashboard?filter=online" class="btn {'btn-secondary' if filter_type != 'online' else ''}">
                        <i class="fas fa-circle"></i> Online ({stats['online_users']})
                    </a>
                    <a href="/dashboard?filter=idle" class="btn {'btn-secondary' if filter_type != 'idle' else ''}">
                        <i class="fas fa-moon"></i> Ausentes ({stats['idle_users']})
                    </a>
                    <a href="/dashboard?filter=recent" class="btn {'btn-secondary' if filter_type != 'recent' else ''}">
                        <i class="fas fa-clock"></i> Recentes (24h)
                    </a>
                    <a href="/dashboard?filter=vip" class="btn {'btn-secondary' if filter_type != 'vip' else ''}">
                        <i class="fas fa-crown"></i> VIPs ({stats['vip_users']})
                    </a>
                    <a href="/dashboard?filter=locked" class="btn {'btn-secondary' if filter_type != 'locked' else ''}">
                        <i class="fas fa-lock"></i> Travados ({stats['locked_users']})
                    </a>
                    <a href="/dashboard?filter=all" class="btn {'btn-secondary' if filter_type != 'all' else ''}">
                        <i class="fas fa-list"></i> Todos ({stats['total_users']})
                    </a>
                </div>
            </div>
            
            <div class="user-list">{users_html}</div>
            
            {pagination_html if len(filtered) > per_page else ''}
            
            <div style="text-align: center; margin-top: 20px;">
                <button class="btn" onclick="location.reload()">
                    <i class="fas fa-sync-alt"></i> Atualizar Manualmente
                </button>
            </div>
        </div>
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
        messages_html = '<div class="empty-state"><h3>📭 Nenhuma mensagem ainda</h3><p>Este usuário ainda não interagiu com a Sophia</p></div>'
    
    vip_badge = '👑 VIP' if stats['is_vip'] else '💬 FREE'
    locked_badge = '🔒 TRAVADO' if stats['is_locked'] else '✅ ATIVO'
    status_emoji = {"online": "🟢", "idle": "🟡", "offline": "🔴"}.get(stats['status'], "🔴")
    status_text = {"online": "ONLINE", "idle": "AUSENTE", "offline": "OFFLINE"}.get(stats['status'], "OFFLINE")
    
    last_seen = format_last_seen(stats['last_activity'])
    
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
                <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 15px;">
                    <div style="flex: 1; min-width: 300px;">
                        <h1 style="font-size: 18px; margin-bottom: 8px;"><i class="fas fa-comments"></i> {uid[:30]}{'...' if len(uid) > 30 else ''}</h1>
                        <div style="display: flex; gap: 15px; flex-wrap: wrap; font-size: 13px;">
                            <span>{status_emoji} <strong>{status_text}</strong></span>
                            <span>📊 {stats['total_messages']} mensagens</span>
                            <span>👤 {stats['user_messages']} do usuário</span>
                            <span>🤖 {stats['sophia_messages']} da Sophia</span>
                            <span>⚡ {stats['actions']} ações</span>
                            <span>🕐 Visto: {last_seen}</span>
                        </div>
                        <div style="margin-top: 8px;">
                            <span class="badge-vip" style="margin-left: 0;">{vip_badge}</span>
                            <span class="{'badge-locked' if stats['is_locked'] else 'badge-vip'}" style="background: {'#ef4444' if stats['is_locked'] else '#10b981'};">{locked_badge}</span>
                        </div>
                    </div>
                    <div style="display: flex; gap: 10px;">
                        <a href="/dashboard" class="btn btn-secondary"><i class="fas fa-arrow-left"></i> Voltar</a>
                        <button class="btn" onclick="location.reload()"><i class="fas fa-sync-alt"></i> Atualizar</button>
                    </div>
                </div>
            </div>
            
            <div class="legend">
                <div class="legend-item"><div class="legend-color" style="background: linear-gradient(135deg, #667eea, #764ba2);"></div> Usuário</div>
                <div class="legend-item"><div class="legend-color" style="background: white; border: 1px solid #ccc;"></div> Sophia</div>
                <div class="legend-item"><div class="legend-color" style="background: #e3f2fd;"></div> Ações (cliques, comandos)</div>
                <div class="legend-item"><div class="legend-color" style="background: #f3e5f5;"></div> Informações</div>
                <div class="legend-item"><div class="legend-color" style="background: #ffebee;"></div> Erros</div>
                <div class="legend-item"><div class="legend-color" style="background: #fff3e0;"></div> Bloqueios</div>
                <div class="legend-item"><div class="legend-color" style="background: #fff3cd;"></div> Sistema</div>
            </div>
            
            <div style="background: white; border-radius: 10px; padding: 15px; margin-bottom: 15px; text-align: center;">
                <span style="color: #666; font-size: 13px;">
                    <i class="fas fa-info-circle"></i> Atualização automática em 30 segundos • Use o botão "Atualizar" para refresh manual
                </span>
            </div>
            
            <div class="chat-view">
                <div class="chat-header">
                    <div>
                        <strong>ID Completo:</strong>
                        <code style="font-size: 11px; background: #f0f0f0; padding: 4px 8px; border-radius: 4px;">{uid}</code>
                    </div>
                    <span style="font-size: 12px; color: #666;">{datetime.now().strftime('%H:%M:%S')}</span>
                </div>
                <div class="chat-messages" id="chat">{messages_html}</div>
            </div>
        </div>
        <script>
            // Scroll para o final
            const chatDiv = document.getElementById('chat');
            chatDiv.scrollTop = chatDiv.scrollHeight;
            
            // Auto-refresh a cada 30 segundos (reduzido de 10s)
            setTimeout(() => location.reload(), 30000);
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
    redis_ok = check_redis()
    return jsonify({
        "status": "healthy" if redis_ok else "degraded",
        "redis": "connected" if redis_ok else "disconnected",
        "timestamp": datetime.now().isoformat(),
        "total_users": len(get_all_users()) if redis_ok else 0
    })

if __name__ == "__main__":
    logger.info(f"🚀 Sophia Admin Panel v2.1 - Porta {PORT}")
    logger.info(f"⚙️  Configurações de Status:")
    logger.info(f"   🟢 Online: < {ONLINE_THRESHOLD} minutos")
    logger.info(f"   🟡 Ausente: {ONLINE_THRESHOLD}-{IDLE_THRESHOLD} minutos")
    logger.info(f"   🔴 Offline: > {OFFLINE_THRESHOLD} minutos")
    logger.info(f"   📅 Recentes: < {RECENT_THRESHOLD} horas")
    app.run(host="0.0.0.0", port=PORT, debug=False)
