#!/usr/bin/env python3
"""
🎯 Sophia Admin Panel - Conversas em Tempo Real
Visualize todas as conversas dos usuários com a IA
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

# ================= STYLES =================
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
.status-online { 
    background: #10b981; 
    color: white; 
}
.status-offline { 
    background: #ef4444; 
    color: white; 
}
.status-idle { 
    background: #f59e0b; 
    color: white; 
}
.badge-vip {
    background: gold;
    color: #333;
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
    margin-bottom: 15px; 
    padding: 12px 16px; 
    border-radius: 18px; 
    max-width: 70%;
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
.message-system {
    background: #fff3cd;
    color: #856404;
    border: 1px solid #ffc107;
    margin: 0 auto;
    text-align: center;
    font-size: 12px;
    padding: 8px 12px;
}
.message-sender { 
    font-weight: bold; 
    margin-bottom: 5px; 
    font-size: 12px;
    opacity: 0.8;
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
    box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
}
.btn-secondary {
    background: #6c757d;
}
.btn-secondary:hover {
    background: #5a6268;
}
.search-box { 
    width: 100%; 
    padding: 12px 20px; 
    border: 2px solid #e0e0e0; 
    border-radius: 10px; 
    margin-bottom: 20px;
    font-size: 14px;
    transition: all 0.3s;
}
.search-box:focus {
    outline: none;
    border-color: #667eea;
    box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
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
    color: #333;
}
.form-group input {
    width: 100%;
    padding: 12px;
    border: 2px solid #e0e0e0;
    border-radius: 8px;
    font-size: 14px;
    transition: all 0.3s;
}
.form-group input:focus {
    outline: none;
    border-color: #667eea;
    box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
}
.empty-state {
    text-align: center;
    padding: 60px 20px;
    color: #666;
}
.empty-state i {
    font-size: 64px;
    margin-bottom: 20px;
    opacity: 0.3;
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
    """Busca todos os usuários que têm logs de chat"""
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
    """Busca todas as mensagens de um usuário"""
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
        logger.error(f"Erro ao buscar mensagens do usuário {uid}: {e}")
    
    return messages

def parse_chat_message(log_line):
    """Parseia uma linha de chat: [HH:MM:SS] ROLE: message"""
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
                    
                    # Mapeia roles
                    if role == "user":
                        role = "user"
                    elif role == "sophia":
                        role = "assistant"
                    else:
                        role = "system"
                    
                    return {
                        "role": role,
                        "text": text,
                        "time": timestamp_str
                    }
    except Exception as e:
        logger.error(f"Erro ao parsear: {e}")
    
    return None

def get_user_stats(uid):
    """Retorna estatísticas do usuário"""
    stats = {
        "total_messages": 0,
        "user_messages": 0,
        "sophia_messages": 0,
        "last_activity": None,
        "status": "offline",
        "is_vip": False
    }
    
    # Verifica VIP
    try:
        vip_key = f"vip:{uid}"
        vip_until = redis_client.get(vip_key)
        if vip_until:
            vip_date = datetime.fromisoformat(vip_until)
            stats["is_vip"] = vip_date > datetime.now()
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
        
        # Última atividade (última mensagem do usuário)
        if role == "user":
            time_str = msg.get("time", "")
            try:
                now = datetime.now()
                parts = time_str.split(':')
                if len(parts) >= 2:
                    hour = int(parts[0])
                    minute = int(parts[1])
                    second = int(parts[2]) if len(parts) > 2 else 0
                    msg_time = datetime(now.year, now.month, now.day, hour, minute, second)
                    
                    if not stats["last_activity"] or msg_time > stats["last_activity"]:
                        stats["last_activity"] = msg_time
            except:
                pass
    
    # Define status baseado na última atividade
    if stats["last_activity"]:
        time_diff = datetime.now() - stats["last_activity"]
        if time_diff < timedelta(minutes=5):
            stats["status"] = "online"
        elif time_diff < timedelta(minutes=30):
            stats["status"] = "idle"
        else:
            stats["status"] = "offline"
    
    return stats

def get_global_stats():
    """Estatísticas globais do sistema"""
    users = get_all_users()
    total_users = len(users)
    vip_count = 0
    online_count = 0
    total_messages = 0
    
    for uid in users:
        stats = get_user_stats(uid)
        if stats["is_vip"]:
            vip_count += 1
        if stats["status"] == "online":
            online_count += 1
        total_messages += stats["total_messages"]
    
    return {
        "total_users": total_users,
        "vip_users": vip_count,
        "online_users": online_count,
        "total_messages": total_messages
    }

# ================= ROUTES =================
@app.route("/")
def home():
    return redirect("/login")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        password = request.form.get("password", "").strip()
        if password == ADMIN_PASSWORD:
            session["authenticated"] = True
            session.permanent = True
            return redirect("/dashboard")
        else:
            error = "Senha incorreta!"
    else:
        error = None
    
    html_content = f"""
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
                    <h1 style="color: #667eea; margin-bottom: 10px;">
                        <i class="fas fa-robot"></i> Sophia AI
                    </h1>
                    <p style="color: #666;">Painel de Monitoramento</p>
                </div>
                {f'<div style="background: #fee; color: #c33; padding: 10px; border-radius: 5px; margin-bottom: 20px; text-align: center;">{error}</div>' if error else ''}
                <form method="post">
                    <div class="form-group">
                        <label for="password"><i class="fas fa-lock"></i> Senha:</label>
                        <input type="password" id="password" name="password" 
                               placeholder="Digite a senha" required autofocus>
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
    
    return html_content

@app.route("/dashboard")
def dashboard():
    if not session.get("authenticated"):
        return redirect("/login")
    
    if not check_redis():
        return "<h1>❌ Erro: Redis não conectado</h1>", 500
    
    users = get_all_users()
    global_stats = get_global_stats()
    
    # Gerar cards dos usuários
    users_html = ""
    for uid in users[:50]:  # Primeiros 50 usuários
        stats = get_user_stats(uid)
        status_class = f"status-{stats['status']}"
        status_text = {
            "online": "🟢 ONLINE",
            "idle": "🟡 AUSENTE",
            "offline": "🔴 OFFLINE"
        }.get(stats['status'], "OFFLINE")
        
        vip_badge = '<span class="badge-vip">👑 VIP</span>' if stats['is_vip'] else ''
        
        last_seen = "Nunca"
        if stats['last_activity']:
            time_diff = datetime.now() - stats['last_activity']
            if time_diff < timedelta(minutes=1):
                last_seen = "Agora mesmo"
            elif time_diff < timedelta(hours=1):
                last_seen = f"{int(time_diff.seconds / 60)}min atrás"
            elif time_diff < timedelta(days=1):
                last_seen = f"{int(time_diff.seconds / 3600)}h atrás"
            else:
                last_seen = stats['last_activity'].strftime("%d/%m %H:%M")
        
        users_html += f"""
        <div class="user-card" onclick="window.location.href='/chat/{uid}'">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                <div class="user-id">
                    <i class="fas fa-user-circle"></i> {uid[:16]}{'...' if len(uid) > 16 else ''}
                    {vip_badge}
                </div>
                <span class="status {status_class}">{status_text}</span>
            </div>
            <div class="user-stats">
                <span><i class="fas fa-comments"></i> {stats['total_messages']} msgs</span>
                <span><i class="fas fa-clock"></i> {last_seen}</span>
            </div>
        </div>
        """
    
    if not users_html:
        users_html = """
        <div class="empty-state">
            <i class="fas fa-users"></i>
            <h3>Nenhuma conversa registrada</h3>
            <p>Aguardando usuários iniciarem conversas com a IA</p>
        </div>
        """
    
    html_content = f"""
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
                        <h1><i class="fas fa-chart-line"></i> Dashboard Sophia AI</h1>
                        <p style="margin-top: 5px; opacity: 0.8;">Monitoramento em Tempo Real • {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}</p>
                    </div>
                    <a href="/logout" class="btn btn-secondary">
                        <i class="fas fa-sign-out-alt"></i> Sair
                    </a>
                </div>
            </div>
            
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-number">{global_stats['total_users']}</div>
                    <div class="stat-label"><i class="fas fa-users"></i> Total de Usuários</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number" style="color: #10b981;">{global_stats['online_users']}</div>
                    <div class="stat-label"><i class="fas fa-circle"></i> Online Agora</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number" style="color: #f59e0b;">{global_stats['vip_users']}</div>
                    <div class="stat-label"><i class="fas fa-crown"></i> Usuários VIP</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number" style="color: #667eea;">{global_stats['total_messages']}</div>
                    <div class="stat-label"><i class="fas fa-comment-dots"></i> Total de Mensagens</div>
                </div>
            </div>
            
            <div style="background: white; border-radius: 10px; padding: 20px; margin-bottom: 20px; box-shadow: 0 5px 15px rgba(0,0,0,0.1);">
                <input type="text" class="search-box" placeholder="🔍 Buscar usuário por ID..." 
                       onkeyup="filterUsers(this.value)">
            </div>
            
            <div class="user-list" id="userList">
                {users_html}
            </div>
            
            <div style="text-align: center; margin-top: 30px;">
                <button class="btn" onclick="location.reload()">
                    <i class="fas fa-sync-alt"></i> Atualizar Dados
                </button>
            </div>
        </div>
        
        <script>
        function filterUsers(search) {{
            const cards = document.querySelectorAll('.user-card');
            search = search.toLowerCase();
            
            cards.forEach(card => {{
                const text = card.textContent.toLowerCase();
                card.style.display = text.includes(search) ? 'block' : 'none';
            }});
        }}
        
        // Auto-refresh a cada 30 segundos
        setTimeout(() => {{ location.reload(); }}, 30000);
        </script>
    </body>
    </html>
    """
    
    return html_content

@app.route("/chat/<uid>")
def chat_view(uid):
    if not session.get("authenticated"):
        return redirect("/login")
    
    messages = get_user_messages(uid)
    stats = get_user_stats(uid)
    
    # Gerar HTML das mensagens
    messages_html = ""
    if messages:
        for msg in messages:
            role = msg.get("role", "user")
            text = html.escape(msg.get("text", ""))
            time_str = msg.get("time", "??:??:??")
            
            if role == "user":
                messages_html += f"""
                <div class="message message-user">
                    <div class="message-sender">👤 Usuário</div>
                    <div>{text}</div>
                    <div class="message-time">{time_str}</div>
                </div>
                """
            elif role == "assistant":
                messages_html += f"""
                <div class="message message-sophia">
                    <div class="message-sender">🤖 Sophia AI</div>
                    <div>{text}</div>
                    <div class="message-time">{time_str}</div>
                </div>
                """
            else:  # system
                messages_html += f"""
                <div class="message message-system">
                    <i class="fas fa-info-circle"></i> {text}
                    <div class="message-time">{time_str}</div>
                </div>
                """
    else:
        messages_html = """
        <div class="empty-state">
            <i class="fas fa-comment-slash"></i>
            <h3>Nenhuma mensagem encontrada</h3>
            <p>Este usuário ainda não iniciou uma conversa</p>
        </div>
        """
    
    vip_badge = '👑 VIP' if stats['is_vip'] else '💬 FREE'
    status_emoji = {"online": "🟢", "idle": "🟡", "offline": "🔴"}.get(stats['status'], "🔴")
    
    html_content = f"""
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Conversa - {uid[:12]}</title>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
        {STYLES}
    </head>
    <body>
        <div class="container">
            <div class="header">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <h1><i class="fas fa-comments"></i> Conversa com {uid[:20]}{'...' if len(uid) > 20 else ''}</h1>
                        <p style="margin-top: 5px;">
                            {status_emoji} {stats['status'].upper()} • 
                            {vip_badge} • 
                            {stats['total_messages']} mensagens
                        </p>
                    </div>
                    <div>
                        <a href="/dashboard" class="btn btn-secondary" style="margin-right: 10px;">
                            <i class="fas fa-arrow-left"></i> Voltar
                        </a>
                        <button class="btn" onclick="location.reload()">
                            <i class="fas fa-sync-alt"></i> Atualizar
                        </button>
                    </div>
                </div>
            </div>
            
            <div class="chat-view">
                <div class="chat-header">
                    <div>
                        <strong>ID Completo:</strong> <code>{uid}</code>
                    </div>
                    <div style="font-size: 12px; color: #666;">
                        Última atualização: {datetime.now().strftime('%H:%M:%S')}
                    </div>
                </div>
                <div class="chat-messages" id="chatMessages">
                    {messages_html}
                </div>
            </div>
        </div>
        
        <script>
        // Auto-scroll para o final
        const chatMessages = document.getElementById('chatMessages');
        if (chatMessages) {{
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }}
        
        // Auto-refresh a cada 10 segundos
        setTimeout(() => {{ location.reload(); }}, 10000);
        </script>
    </body>
    </html>
    """
    
    return html_content

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

@app.route("/health")
def health():
    return jsonify({
        "status": "healthy" if check_redis() else "degraded",
        "redis": "connected" if check_redis() else "disconnected",
        "timestamp": datetime.now().isoformat(),
        "service": "sophia-admin-panel",
        "users_count": len(get_all_users()) if check_redis() else 0
    })

# ================= MAIN =================
if __name__ == "__main__":
    logger.info(f"🚀 Iniciando Sophia Admin Panel na porta {PORT}")
    logger.info(f"📊 Redis: {'✅ Conectado' if check_redis() else '❌ Desconectado'}")
    logger.info(f"🔑 Senha admin: {ADMIN_PASSWORD}")
    
    app.run(
        host="0.0.0.0",
        port=PORT,
        debug=False
    )
