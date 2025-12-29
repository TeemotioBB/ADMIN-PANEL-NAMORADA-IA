#!/usr/bin/env python3
"""
🎯 Sophia Admin Panel - Chat Fix
"""

import os
import json
import redis
from datetime import datetime, timedelta
from flask import Flask, request, redirect, session, jsonify, render_template_string
import logging
import time

# ================= CONFIG =================
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

# ================= UTILITIES FIXED =================
def check_redis():
    """Verifica conexão com Redis"""
    if not redis_client:
        return False
    try:
        redis_client.ping()
        return True
    except:
        return False

def get_all_users():
    """Obtém todos os usuários do Redis - FIXED VERSION"""
    if not check_redis():
        return []
    
    users = set()
    try:
        # Scan por todas as chaves do tipo chatlog
        cursor = 0
        pattern = "chatlog:*"
        
        while True:
            cursor, keys = redis_client.scan(cursor=cursor, match=pattern, count=100)
            for key in keys:
                parts = key.split(":")
                if len(parts) > 1:
                    users.add(parts[1])
            if cursor == 0:
                break
    except Exception as e:
        logger.error(f"Erro ao buscar usuários: {e}")
    
    return sorted(list(users), reverse=True)

def get_user_messages(uid):
    """Obtém mensagens de um usuário específico - FIXED VERSION"""
    if not check_redis():
        return []
    
    messages = []
    try:
        # Tenta diferentes formatos de chave
        possible_keys = [
            f"chatlog:{uid}",
            f"chat:{uid}",
            f"user:{uid}:messages",
            f"messages:{uid}",
            f"conversation:{uid}"
        ]
        
        for key in possible_keys:
            if redis_client.exists(key):
                logs = redis_client.lrange(key, 0, -1)
                logger.info(f"Encontradas {len(logs)} mensagens na chave {key}")
                
                for log in logs:
                    try:
                        # Tenta parsear como JSON
                        if isinstance(log, str) and log.strip().startswith('{'):
                            msg = json.loads(log)
                            # Garante que temos os campos necessários
                            if "role" in msg and "text" in msg:
                                messages.append(msg)
                            elif "message" in msg or "content" in msg:
                                # Adapta diferentes formatos
                                msg_dict = {
                                    "role": msg.get("role", "user"),
                                    "text": msg.get("text", msg.get("message", msg.get("content", ""))),
                                    "ts": msg.get("ts", msg.get("timestamp", datetime.now().isoformat()))
                                }
                                messages.append(msg_dict)
                        else:
                            # Se não for JSON, trata como texto simples
                            msg_dict = {
                                "role": "user" if ": user:" in log.lower() or log.startswith("user:") else "assistant",
                                "text": log,
                                "ts": datetime.now().isoformat()
                            }
                            messages.append(msg_dict)
                    except json.JSONDecodeError:
                        # Formato simples: "role: text"
                        if ":" in log:
                            parts = log.split(":", 1)
                            if len(parts) == 2:
                                role = parts[0].strip().lower()
                                text = parts[1].strip()
                                msg_dict = {
                                    "role": "user" if role in ["user", "usuário"] else "assistant",
                                    "text": text,
                                    "ts": datetime.now().isoformat()
                                }
                                messages.append(msg_dict)
                        else:
                            # Mensagem sem formatação
                            msg_dict = {
                                "role": "user",
                                "text": log,
                                "ts": datetime.now().isoformat()
                            }
                            messages.append(msg_dict)
                    except Exception as e:
                        logger.error(f"Erro ao processar mensagem: {e}, log: {log}")
                        continue
                break  # Para no primeiro formato que encontrar mensagens
    except Exception as e:
        logger.error(f"Erro ao buscar mensagens do usuário {uid}: {e}")
    
    return messages

def get_user_stats(uid):
    """Estatísticas do usuário - FIXED VERSION"""
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
        try:
            role = msg.get("role", "").lower()
            if role == "user":
                stats["user_messages"] += 1
            else:
                stats["sophia_messages"] += 1
            
            # Tenta obter timestamp
            ts = msg.get("ts")
            if ts:
                if isinstance(ts, str):
                    msg_time = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                else:
                    msg_time = datetime.now()
            else:
                msg_time = datetime.now()
                
            if not stats["last_activity"] or msg_time > stats["last_activity"]:
                stats["last_activity"] = msg_time
        except Exception as e:
            logger.error(f"Erro ao processar mensagem para stats: {e}")
            continue
    
    # Verificar se está ativo (últimos 5 minutos)
    if stats["last_activity"]:
        time_diff = datetime.now() - stats["last_activity"]
        if time_diff < timedelta(minutes=5):
            stats["status"] = "online"
        elif time_diff < timedelta(minutes=30):
            stats["status"] = "idle"  # Ocioso
        else:
            stats["status"] = "offline"
    
    return stats

def debug_redis_keys():
    """Debug: mostra todas as chaves do Redis"""
    if not check_redis():
        return []
    
    try:
        cursor = 0
        all_keys = []
        while True:
            cursor, keys = redis_client.scan(cursor=cursor, count=100)
            all_keys.extend(keys)
            if cursor == 0:
                break
        
        logger.info(f"Total de chaves no Redis: {len(all_keys)}")
        chat_keys = [k for k in all_keys if 'chat' in k.lower() or 'message' in k.lower()]
        logger.info(f"Chaves relacionadas a chat: {chat_keys}")
        
        # Inspecionar algumas chaves
        for key in chat_keys[:5]:
            try:
                value = redis_client.lrange(key, 0, 2)  # Primeiras 3 mensagens
                logger.info(f"Chave: {key}, Primeiras mensagens: {value}")
            except:
                value = redis_client.get(key)
                logger.info(f"Chave: {key}, Valor: {value}")
        
        return all_keys
    except Exception as e:
        logger.error(f"Erro no debug do Redis: {e}")
        return []

# ================= HTML TEMPLATES (SIMPLIFIED) =================
BASE_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - Sophia Admin</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif; background: #f0f2f5; color: #333; }
        .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
        .header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 10px; margin-bottom: 20px; }
        .card { background: white; border-radius: 10px; padding: 20px; margin-bottom: 20px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .btn { display: inline-block; padding: 10px 20px; background: #667eea; color: white; text-decoration: none; border-radius: 5px; border: none; cursor: pointer; }
        .btn:hover { background: #5a67d8; }
        .user-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 15px; }
        .user-card { padding: 15px; border: 1px solid #ddd; border-radius: 8px; cursor: pointer; transition: all 0.3s; }
        .user-card:hover { border-color: #667eea; transform: translateY(-2px); box-shadow: 0 5px 15px rgba(0,0,0,0.1); }
        .status { display: inline-block; padding: 3px 8px; border-radius: 12px; font-size: 12px; font-weight: bold; }
        .status-online { background: #10b981; color: white; }
        .status-offline { background: #ef4444; color: white; }
        .status-idle { background: #f59e0b; color: white; }
        .chat-container { display: flex; height: 80vh; gap: 20px; }
        .chat-sidebar { width: 300px; background: white; border-radius: 10px; padding: 20px; overflow-y: auto; }
        .chat-messages { flex: 1; background: white; border-radius: 10px; padding: 20px; overflow-y: auto; display: flex; flex-direction: column; }
        .message { margin-bottom: 15px; max-width: 70%; padding: 10px 15px; border-radius: 15px; }
        .message-user { background: #667eea; color: white; align-self: flex-end; border-bottom-right-radius: 5px; }
        .message-sophia { background: #f0f0f0; color: #333; align-self: flex-start; border-bottom-left-radius: 5px; }
        .message-time { font-size: 11px; opacity: 0.7; margin-top: 5px; }
        .search-box { width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 5px; margin-bottom: 15px; }
    </style>
</head>
<body>
    {content}
</body>
</html>
"""

# ================= ROUTES FIXED =================
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
    
    login_html = """
    <div style="display: flex; justify-content: center; align-items: center; height: 100vh;">
        <div style="background: white; padding: 40px; border-radius: 10px; box-shadow: 0 10px 40px rgba(0,0,0,0.1); width: 100%; max-width: 400px;">
            <div style="text-align: center; margin-bottom: 30px;">
                <h1 style="color: #667eea; margin-bottom: 10px;">
                    <i class="fas fa-brain"></i> Sophia AI
                </h1>
                <p style="color: #666;">Painel Administrativo</p>
            </div>
            <form method="post">
                <div style="margin-bottom: 20px;">
                    <label style="display: block; margin-bottom: 5px; font-weight: bold;">Senha:</label>
                    <input type="password" name="password" style="width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 5px;" 
                           placeholder="Digite a senha" required>
                </div>
                <button type="submit" style="width: 100%; padding: 12px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                        color: white; border: none; border-radius: 5px; cursor: pointer; font-weight: bold;">
                    <i class="fas fa-sign-in-alt"></i> Entrar
                </button>
            </form>
        </div>
    </div>
    """
    
    return BASE_TEMPLATE.format(title="Login", content=login_html)

@app.route("/dashboard")
def dashboard():
    if not session.get("authenticated"):
        return redirect("/login")
    
    # Executar debug para ver chaves
    debug_redis_keys()
    
    users = get_all_users()
    logger.info(f"Total de usuários encontrados: {len(users)}")
    
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
    
    dashboard_html = f"""
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
            <a href="/debug" class="btn" style="background: #f59e0b; margin-left: 10px;">
                <i class="fas fa-bug"></i> Debug
            </a>
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
    """
    
    return BASE_TEMPLATE.format(title="Dashboard", content=dashboard_html)

@app.route("/chat/<uid>")
def chat_view(uid):
    if not session.get("authenticated"):
        return redirect("/login")
    
    # Buscar mensagens
    messages = get_user_messages(uid)
    stats = get_user_stats(uid)
    
    logger.info(f"Chat do usuário {uid}: {len(messages)} mensagens encontradas")
    
    # Gerar HTML das mensagens
    messages_html = ""
    if messages:
        for msg in messages[-100:]:  # Últimas 100 mensagens
            try:
                role = msg.get("role", "").lower()
                text = msg.get("text", msg.get("message", msg.get("content", str(msg))))
                
                # Formatar timestamp
                ts = msg.get("ts")
                if ts:
                    try:
                        if isinstance(ts, str):
                            time_obj = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                        else:
                            time_obj = datetime.now()
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
            except Exception as e:
                logger.error(f"Erro ao renderizar mensagem: {e}")
                continue
    else:
        messages_html = """
        <div style="text-align: center; padding: 40px; color: #666;">
            <i class="fas fa-comment-slash" style="font-size: 48px; margin-bottom: 20px; opacity: 0.3;"></i>
            <h3>Nenhuma mensagem encontrada</h3>
            <p>Este usuário ainda não trocou mensagens com o bot</p>
        </div>
        """
    
    chat_html = f"""
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
                
                <h3 style="margin-bottom: 15px; color: #667eea;">
                    <i class="fas fa-cog"></i> Ações
                </h3>
                <div>
                    <button class="btn" style="width: 100%; margin-bottom: 10px;" onclick="exportChat()">
                        <i class="fas fa-download"></i> Exportar Chat
                    </button>
                    <button class="btn" style="width: 100%; background: #ef4444;" onclick="clearChat()">
                        <i class="fas fa-trash"></i> Limpar Chat
                    </button>
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
    
    function exportChat() {{
        alert('Exportando chat do usuário {uid}...');
        // Implementar exportação aqui
    }}
    
    function clearChat() {{
        if (confirm('Tem certeza que deseja limpar todo o histórico deste chat?')) {{
            fetch('/api/chat/{uid}/clear', {{ method: 'POST' }})
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
    </script>
    """
    
    return BASE_TEMPLATE.format(title=f"Chat - {uid[:12]}...", content=chat_html)

@app.route("/debug")
def debug_page():
    """Página de debug para verificar o Redis"""
    if not session.get("authenticated"):
        return redirect("/login")
    
    all_keys = debug_redis_keys()
    
    # Verificar alguns usuários específicos
    users = get_all_users()[:10]  # Primeiros 10 usuários
    
    debug_info = ""
    for uid in users:
        stats = get_user_stats(uid)
        debug_info += f"""
        <div style="background: white; padding: 15px; border-radius: 5px; margin-bottom: 10px;">
            <strong>Usuário:</strong> {uid}<br>
            <strong>Status:</strong> {stats['status']}<br>
            <strong>Mensagens:</strong> {stats['total_messages']}<br>
            <strong>Última atividade:</strong> {stats['last_activity']}<br>
            <a href="/chat/{uid}" style="color: #667eea;">Ver chat</a>
        </div>
        """
    
    debug_html = f"""
    <div class="container">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
            <h1><i class="fas fa-bug"></i> Debug do Sistema</h1>
            <a href="/dashboard" class="btn">Voltar ao Dashboard</a>
        </div>
        
        <div class="card">
            <h2 style="margin-bottom: 15px; color: #667eea;">
                <i class="fas fa-database"></i> Status do Redis
            </h2>
            <p><strong>Conexão:</strong> {'✅ Conectado' if check_redis() else '❌ Desconectado'}</p>
            <p><strong>Total de chaves:</strong> {len(all_keys)}</p>
        </div>
        
        <div class="card">
            <h2 style="margin-bottom: 15px; color: #667eea;">
                <i class="fas fa-users"></i> Usuários (amostra)
            </h2>
            <div style="max-height: 400px; overflow-y: auto;">
                {debug_info if debug_info else '<p>Nenhum usuário encontrado</p>'}
            </div>
        </div>
        
        <div class="card">
            <h2 style="margin-bottom: 15px; color: #667eea;">
                <i class="fas fa-tools"></i> Ferramentas
            </h2>
            <div>
                <button class="btn" onclick="clearAllChats()" style="background: #ef4444;">
                    <i class="fas fa-trash"></i> Limpar TODOS os chats
                </button>
                <button class="btn" onclick="testRedis()" style="margin-left: 10px; background: #10b981;">
                    <i class="fas fa-vial"></i> Testar Redis
                </button>
            </div>
        </div>
    </div>
    
    <script>
    function clearAllChats() {{
        if (confirm('ATENÇÃO: Isso irá limpar TODOS os chats de TODOS os usuários. Tem certeza?')) {{
            fetch('/api/clear_all', {{ method: 'POST' }})
                .then(response => response.json())
                .then(data => {{
                    if (data.success) {{
                        alert('Todos os chats foram limpos!');
                        location.reload();
                    }} else {{
                        alert('Erro: ' + data.error);
                    }}
                }});
        }}
    }}
    
    function testRedis() {{
        fetch('/api/test_redis')
            .then(response => response.json())
            .then(data => {{
                alert('Teste do Redis:\\nStatus: ' + data.status + '\\nMensagem: ' + data.message);
            }});
    }}
    </script>
    """
    
    return BASE_TEMPLATE.format(title="Debug", content=debug_html)

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# ================= API ENDPOINTS =================
@app.route("/api/test_redis")
def api_test_redis():
    """Testa a conexão com Redis"""
    if check_redis():
        # Tenta escrever e ler uma chave de teste
        try:
            test_key = "test:connection"
            redis_client.set(test_key, "OK", ex=10)
            value = redis_client.get(test_key)
            return jsonify({
                "status": "success",
                "message": f"Redis conectado. Teste: {value}",
                "connected": True
            })
        except Exception as e:
            return jsonify({
                "status": "error",
                "message": f"Erro ao testar Redis: {str(e)}",
                "connected": False
            })
    else:
        return jsonify({
            "status": "error",
            "message": "Redis não conectado",
            "connected": False
        })

@app.route("/api/chat/<uid>/messages")
def api_chat_messages(uid):
    """API para obter mensagens de um usuário"""
    if not session.get("authenticated"):
        return jsonify({"error": "Unauthorized"}), 401
    
    messages = get_user_messages(uid)
    return jsonify({
        "user_id": uid,
        "count": len(messages),
        "messages": messages
    })

@app.route("/api/chat/<uid>/clear", methods=["POST"])
def api_clear_chat(uid):
    """Limpa o chat de um usuário"""
    if not session.get("authenticated"):
        return jsonify({"error": "Unauthorized"}), 401
    
    try:
        # Tenta remover várias possíveis chaves
        keys_to_delete = [
            f"chatlog:{uid}",
            f"chat:{uid}",
            f"user:{uid}:messages",
            f"messages:{uid}",
            f"conversation:{uid}"
        ]
        
        deleted_count = 0
        for key in keys_to_delete:
            if redis_client.exists(key):
                redis_client.delete(key)
                deleted_count += 1
        
        return jsonify({
            "success": True,
            "message": f"Chat do usuário {uid} limpo",
            "deleted_keys": deleted_count
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route("/api/clear_all", methods=["POST"])
def api_clear_all():
    """Limpa TODOS os chats - APENAS PARA DEBUG"""
    if not session.get("authenticated"):
        return jsonify({"error": "Unauthorized"}), 401
    
    try:
        # Busca todas as chaves de chat
        cursor = 0
        chat_keys = []
        patterns = ["chatlog:*", "chat:*", "user:*:messages", "messages:*", "conversation:*"]
        
        for pattern in patterns:
            cursor = 0
            while True:
                cursor, keys = redis_client.scan(cursor=cursor, match=pattern, count=100)
                chat_keys.extend(keys)
                if cursor == 0:
                    break
        
        # Remove chaves duplicadas
        chat_keys = list(set(chat_keys))
        
        # Deleta todas as chaves
        if chat_keys:
            redis_client.delete(*chat_keys)
        
        return jsonify({
            "success": True,
            "message": f"Todos os chats foram limpos",
            "deleted_count": len(chat_keys),
            "deleted_keys": chat_keys
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

# ================= ERROR HANDLERS =================
@app.errorhandler(404)
def not_found(error):
    return "Página não encontrada", 404

@app.errorhandler(500)
def internal_error(error):
    return "Erro interno do servidor", 500

# ================= MAIN =================
if __name__ == "__main__":
    logger.info(f"🚀 Iniciando Sophia Admin Panel na porta {PORT}")
    logger.info(f"📊 Redis: {'✅ Conectado' if check_redis() else '❌ Desconectado'}")
    
    # Testar conexão e mostrar algumas chaves
    if check_redis():
        debug_redis_keys()
    
    app.run(
        host="0.0.0.0",
        port=PORT,
        debug=True  # Mantenha True para ver logs de erro
    )
