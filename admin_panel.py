#!/usr/bin/env python3
"""
🎯 Sophia Admin Panel - Fixed Version
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
PORT = int(os.environ.get("PORT", 8080))

# Configurar logging
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
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif; 
    background: #f0f2f5; 
    color: #333; 
}
.container { 
    max-width: 1200px; 
    margin: 0 auto; 
    padding: 20px; 
}
.header { 
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
    color: white; 
    padding: 20px; 
    border-radius: 10px; 
    margin-bottom: 20px; 
}
.card { 
    background: white; 
    border-radius: 10px; 
    padding: 20px; 
    margin-bottom: 20px; 
    box-shadow: 0 2px 10px rgba(0,0,0,0.1); 
}
.btn { 
    display: inline-block; 
    padding: 10px 20px; 
    background: #667eea; 
    color: white; 
    text-decoration: none; 
    border-radius: 5px; 
    border: none; 
    cursor: pointer; 
}
.btn:hover { 
    background: #5a67d8; 
}
.user-list { 
    display: grid; 
    grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); 
    gap: 15px; 
}
.user-card { 
    padding: 15px; 
    border: 1px solid #ddd; 
    border-radius: 8px; 
    cursor: pointer; 
    transition: all 0.3s; 
}
.user-card:hover { 
    border-color: #667eea; 
    transform: translateY(-2px); 
    box-shadow: 0 5px 15px rgba(0,0,0,0.1); 
}
.status { 
    display: inline-block; 
    padding: 3px 8px; 
    border-radius: 12px; 
    font-size: 12px; 
    font-weight: bold; 
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
.chat-container { 
    display: flex; 
    height: 80vh; 
    gap: 20px; 
}
.chat-sidebar { 
    width: 300px; 
    background: white; 
    border-radius: 10px; 
    padding: 20px; 
    overflow-y: auto; 
}
.chat-messages { 
    flex: 1; 
    background: white; 
    border-radius: 10px; 
    padding: 20px; 
    overflow-y: auto; 
    display: flex; 
    flex-direction: column; 
}
.message { 
    margin-bottom: 15px; 
    max-width: 70%; 
    padding: 10px 15px; 
    border-radius: 15px; 
}
.message-user { 
    background: #667eea; 
    color: white; 
    align-self: flex-end; 
    border-bottom-right-radius: 5px; 
}
.message-sophia { 
    background: #f0f0f0; 
    color: #333; 
    align-self: flex-start; 
    border-bottom-left-radius: 5px; 
}
.message-time { 
    font-size: 11px; 
    opacity: 0.7; 
    margin-top: 5px; 
}
.search-box { 
    width: 100%; 
    padding: 10px; 
    border: 1px solid #ddd; 
    border-radius: 5px; 
    margin-bottom: 15px; 
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
    border-radius: 10px;
    box-shadow: 0 10px 40px rgba(0,0,0,0.1);
    width: 100%;
    max-width: 400px;
}
.form-group {
    margin-bottom: 20px;
}
.form-group label {
    display: block;
    margin-bottom: 5px;
    font-weight: bold;
}
.form-group input {
    width: 100%;
    padding: 10px;
    border: 1px solid #ddd;
    border-radius: 5px;
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

def parse_chat_message(log_line):
    """Parseia uma linha de chat do formato [HH:MM:SS] ROLE: message"""
    try:
        # Remove colchetes do timestamp
        if log_line.startswith('['):
            end_bracket = log_line.find(']')
            if end_bracket > 0:
                timestamp_str = log_line[1:end_bracket]
                remaining = log_line[end_bracket+2:]  # +2 para pular "] "
                
                # Encontra a separação entre role e mensagem
                colon_pos = remaining.find(':')
                if colon_pos > 0:
                    role = remaining[:colon_pos].strip()
                    text = remaining[colon_pos+1:].strip()
                    
                    # Tenta parsear o timestamp
                    try:
                        # Adiciona a data atual ao tempo
                        now = datetime.now()
                        time_parts = timestamp_str.split(':')
                        if len(time_parts) >= 2:
                            hour = int(time_parts[0])
                            minute = int(time_parts[1])
                            second = int(time_parts[2]) if len(time_parts) > 2 else 0
                            
                            ts = datetime(now.year, now.month, now.day, hour, minute, second)
                        else:
                            ts = datetime.now()
                    except:
                        ts = datetime.now()
                    
                    return {
                        "role": "user" if role.upper() == "USER" else "assistant",
                        "text": text,
                        "ts": ts.isoformat()
                    }
    except Exception as e:
        logger.error(f"Erro ao parsear mensagem: {e}, linha: {log_line}")
    
    # Fallback: retorna como mensagem do usuário
    return {
        "role": "user",
        "text": log_line,
        "ts": datetime.now().isoformat()
    }

def get_user_messages(uid):
    if not check_redis():
        return []
    
    messages = []
    try:
        key = f"chatlog:{uid}"
        logs = redis_client.lrange(key, 0, -1)
        
        for log in logs:
            msg = parse_chat_message(log)
            messages.append(msg)
            
    except Exception as e:
        logger.error(f"Erro ao buscar mensagens do usuário {uid}: {e}")
    
    return messages

def get_user_stats(uid):
    stats = {
        "total_messages": 0,
        "user_messages": 0,
        "sophia_messages": 0,
        "last_activity": None,
        "status": "offline"
    }
    
    messages = get_user_messages(uid)
    stats["total_messages"] = len(messages)
    
    for msg in messages:
        role = msg.get("role", "").lower()
        if role == "user":
            stats["user_messages"] += 1
        else:
            stats["sophia_messages"] += 1
        
        # Tenta obter timestamp
        ts = msg.get("ts")
        if ts:
            try:
                msg_time = datetime.fromisoformat(ts)
                if not stats["last_activity"] or msg_time > stats["last_activity"]:
                    stats["last_activity"] = msg_time
            except:
                pass
    
    # Verificar se está ativo (últimos 5 minutos)
    if stats["last_activity"]:
        time_diff = datetime.now() - stats["last_activity"]
        if time_diff < timedelta(minutes=5):
            stats["status"] = "online"
        elif time_diff < timedelta(minutes=30):
            stats["status"] = "idle"
        else:
            stats["status"] = "offline"
    
    return stats

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
            return redirect("/dashboard")
    
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
                        <i class="fas fa-brain"></i> Sophia AI
                    </h1>
                    <p style="color: #666;">Painel Administrativo</p>
                </div>
                <form method="post">
                    <div class="form-group">
                        <label for="password">Senha:</label>
                        <input type="password" id="password" name="password" 
                               placeholder="Digite a senha" required>
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
    
    users = get_all_users()
    
    # Gerar HTML dos usuários
    users_html = ""
    for uid in users[:100]:  # Limitar a 100 usuários
        stats = get_user_stats(uid)
        status_class = f"status-{stats['status']}"
        status_text = stats['status'].upper()
        
        last_active = stats['last_activity']
        if last_active:
            time_diff = datetime.now() - last_active
            if time_diff < timedelta(minutes=1):
                last_seen = "Agora"
            elif time_diff < timedelta(hours=1):
                last_seen = f"{int(time_diff.seconds / 60)}min"
            elif time_diff < timedelta(days=1):
                last_seen = f"{int(time_diff.seconds / 3600)}h"
            else:
                last_seen = last_active.strftime("%d/%m")
        else:
            last_seen = "Nunca"
        
        users_html += f"""
        <div class="user-card" onclick="window.location.href='/chat/{uid}'">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                <div style="font-weight: bold; color: #667eea;">
                    <i class="fas fa-user"></i> {uid[:12]}{'...' if len(uid) > 12 else ''}
                </div>
                <span class="status {status_class}">{status_text}</span>
            </div>
            <div style="display: flex; justify-content: space-between; font-size: 14px; color: #666;">
                <span><i class="fas fa-comment"></i> {stats['total_messages']} msg</span>
                <span><i class="fas fa-clock"></i> {last_seen}</span>
            </div>
        </div>
        """
    
    if not users_html:
        users_html = """
        <div style="text-align: center; padding: 40px; color: #666;">
            <i class="fas fa-users" style="font-size: 48px; margin-bottom: 20px; opacity: 0.3;"></i>
            <h3>Nenhum usuário encontrado</h3>
            <p>Os usuários aparecerão aqui quando conversarem com o bot</p>
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
                        <h1><i class="fas fa-tachometer-alt"></i> Dashboard Sophia AI</h1>
                        <p>Usuários ativos: {len(users)} • {datetime.now().strftime('%d/%m/%Y %H:%M')}</p>
                    </div>
                    <div>
                        <a href="/logout" class="btn" style="background: rgba(255,255,255,0.2);">
                            <i class="fas fa-sign-out-alt"></i> Sair
                        </a>
                    </div>
                </div>
            </div>
            
            <div style="margin-bottom: 20px;">
                <input type="text" class="search-box" placeholder="Buscar usuários..." 
                       onkeyup="filterUsers(this.value)">
            </div>
            
            <div class="user-list" id="userList">
                {users_html}
            </div>
            
            <div style="margin-top: 20px; text-align: center;">
                <button class="btn" onclick="location.reload()">
                    <i class="fas fa-sync-alt"></i> Atualizar
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
        for msg in messages[-100:]:  # Últimas 100 mensagens
            role = msg.get("role", "").lower()
            text = html.escape(msg.get("text", ""))
            
            # Formatar timestamp
            ts = msg.get("ts")
            if ts:
                try:
                    time_obj = datetime.fromisoformat(ts)
                    time_str = time_obj.strftime("%H:%M")
                except:
                    time_str = "??:??"
            else:
                time_str = "??:??"
            
            if role == "user":
                messages_html += f"""
                <div class="message message-user">
                    <div style="font-weight: bold; margin-bottom: 5px;">Usuário</div>
                    <div>{text}</div>
                    <div class="message-time">{time_str}</div>
                </div>
                """
            else:
                messages_html += f"""
                <div class="message message-sophia">
                    <div style="font-weight: bold; margin-bottom: 5px; color: #667eea;">Sophia AI 💖</div>
                    <div>{text}</div>
                    <div class="message-time">{time_str}</div>
                </div>
                """
    else:
        messages_html = """
        <div style="text-align: center; padding: 40px; color: #666;">
            <i class="fas fa-comment-slash" style="font-size: 48px; margin-bottom: 20px; opacity: 0.3;"></i>
            <h3>Nenhuma mensagem encontrada</h3>
            <p>Este usuário ainda não trocou mensagens com o bot</p>
        </div>
        """
    
    html_content = f"""
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Chat - Sophia Admin</title>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
        {STYLES}
    </head>
    <body>
        <div class="container">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
                <div>
                    <h1><i class="fas fa-comments"></i> Chat com {uid[:12]}{'...' if len(uid) > 12 else ''}</h1>
                    <p>Status: <span class="status status-{stats['status']}">{stats['status'].upper()}</span> • 
                       {stats['total_messages']} mensagens • Última: {stats['last_activity'].strftime('%H:%M') if stats['last_activity'] else 'Nunca'}</p>
                </div>
                <div>
                    <a href="/dashboard" class="btn">
                        <i class="fas fa-arrow-left"></i> Voltar
                    </a>
                    <button class="btn" onclick="location.reload()" style="margin-left: 10px;">
                        <i class="fas fa-sync-alt"></i> Atualizar
                    </button>
                </div>
            </div>
            
            <div class="chat-container">
                <div class="chat-sidebar">
                    <h3 style="margin-bottom: 15px; color: #667eea;">
                        <i class="fas fa-info-circle"></i> Informações
                    </h3>
                    <div style="margin-bottom: 20px;">
                        <p><strong>ID do Usuário:</strong><br>{uid}</p>
                        <p><strong>Total Mensagens:</strong> {stats['total_messages']}</p>
                        <p><strong>Mensagens Usuário:</strong> {stats['user_messages']}</p>
                        <p><strong>Mensagens Sophia:</strong> {stats['sophia_messages']}</p>
                        <p><strong>Última Atividade:</strong><br>{stats['last_activity'].strftime('%d/%m/%Y %H:%M') if stats['last_activity'] else 'Nunca'}</p>
                        <p><strong>Status:</strong> <span class="status status-{stats['status']}">{stats['status'].upper()}</span></p>
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
        setInterval(() => {{ location.reload(); }}, 10000);
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
        "service": "sophia-admin-panel"
    })

# ================= ERROR HANDLERS =================
@app.errorhandler(404)
def not_found(error):
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>404 - Sophia Admin</title>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
        {STYLES}
    </head>
    <body>
        <div class="login-container">
            <div class="login-card">
                <div style="text-align: center;">
                    <h1 style="color: #667eea; margin-bottom: 20px;">
                        <i class="fas fa-exclamation-triangle"></i> 404
                    </h1>
                    <p style="margin-bottom: 30px;">Página não encontrada</p>
                    <a href="/dashboard" class="btn">
                        <i class="fas fa-home"></i> Voltar ao Dashboard
                    </a>
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    return html_content, 404

@app.errorhandler(500)
def internal_error(error):
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>500 - Sophia Admin</title>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
        {STYLES}
    </head>
    <body>
        <div class="login-container">
            <div class="login-card">
                <div style="text-align: center;">
                    <h1 style="color: #ef4444; margin-bottom: 20px;">
                        <i class="fas fa-server"></i> 500
                    </h1>
                    <p style="margin-bottom: 30px;">Erro interno do servidor</p>
                    <a href="/dashboard" class="btn">
                        <i class="fas fa-redo"></i> Tentar novamente
                    </a>
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    return html_content, 500

# ================= MAIN =================
if __name__ == "__main__":
    logger.info(f"🚀 Iniciando Sophia Admin Panel na porta {PORT}")
    logger.info(f"📊 Redis: {'✅ Conectado' if check_redis() else '❌ Desconectado'}")
    
    app.run(
        host="0.0.0.0",
        port=PORT,
        debug=False
    )
