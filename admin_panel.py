#!/usr/bin/env python3
"""
🎯 Sophia Admin Panel v5 - FULL FEATURED
==========================================
📊 Analytics - Gráficos e métricas
📢 Broadcast - Envio em massa com filtros
💰 Financeiro - Comprovantes e receita
📸 Galeria - Banco de fotos
📝 Logs - Histórico de ações
⚙️ Config - Configurações editáveis
🔔 Alertas - Notificações em tempo real
⭐ Favoritos - Usuários marcados
🏷️ Tags/Notas - CRM básico
"""

import os
import json
import redis
import urllib.request
import urllib.parse
import urllib.error
import base64
from datetime import datetime, timedelta, date
from flask import Flask, request, redirect, session, jsonify, send_file
from io import BytesIO
import logging
import time
import html
import hashlib

# ================= CONFIG =================
REDIS_URL = os.environ.get("REDIS_URL", "redis://default:DcddfJOHLXZdFPjEhRjHeodNgdtrsevl@shuttle.proxy.rlwy.net:12241")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8528168785:AAFfgtaB0vEagd1cdfZ3hWDyL9PKFZrmRjk")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")
SECRET_KEY = os.environ.get("SECRET_KEY", "sophia-secret-" + str(int(time.time())))
PORT = int(os.environ.get("PORT", 8081))

ONLINE_THRESHOLD = 20
IDLE_THRESHOLD = 40
OFFLINE_THRESHOLD = 60

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

redis_client = None
try:
    redis_client = redis.from_url(REDIS_URL, decode_responses=True, socket_connect_timeout=5, socket_timeout=5)
    redis_client.ping()
    logger.info("✅ Redis conectado")
except Exception as e:
    logger.error(f"❌ Redis erro: {e}")
    redis_client = None

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=8)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max

# ================= REDIS KEYS =================
def admin_log_key(): return "admin:logs"
def admin_config_key(): return "admin:config"
def admin_gallery_key(): return "admin:gallery"
def admin_favorites_key(): return "admin:favorites"
def admin_notes_key(uid): return f"admin:notes:{uid}"
def admin_tags_key(uid): return f"admin:tags:{uid}"
def admin_alerts_key(): return "admin:alerts"
def daily_stats_key(d): return f"stats:daily:{d}"
def pix_pending_list_key(): return "admin:pix_pending"
def broadcast_history_key(): return "admin:broadcast_history"
def admin_takeover_key(uid): return f"admin:takeover:{uid}"    

# ================= TELEGRAM API =================
def send_telegram_message(chat_id, text, parse_mode="Markdown"):
    if not TELEGRAM_TOKEN:
        return False, "Token não configurado"
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    
    try:
        data = json.dumps({
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode
        }).encode('utf-8')
        
        req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'}, method='POST')
        
        with urllib.request.urlopen(req, timeout=10) as response:
            result = json.loads(response.read().decode('utf-8'))
            return (True, "Enviado") if result.get("ok") else (False, result.get("description", "Erro"))
                
    except Exception as e:
        return False, str(e)

def send_telegram_photo(chat_id, photo_data, caption=""):
    if not TELEGRAM_TOKEN:
        return False, "Token não configurado"
    
    import uuid
    boundary = str(uuid.uuid4())
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    
    try:
        body = b''
        body += f'--{boundary}\r\n'.encode()
        body += b'Content-Disposition: form-data; name="chat_id"\r\n\r\n'
        body += f'{chat_id}\r\n'.encode()
        
        if caption:
            body += f'--{boundary}\r\n'.encode()
            body += b'Content-Disposition: form-data; name="caption"\r\n\r\n'
            body += f'{caption}\r\n'.encode()
        
        body += f'--{boundary}\r\n'.encode()
        body += b'Content-Disposition: form-data; name="photo"; filename="photo.jpg"\r\n'
        body += b'Content-Type: image/jpeg\r\n\r\n'
        body += photo_data
        body += b'\r\n'
        body += f'--{boundary}--\r\n'.encode()
        
        req = urllib.request.Request(url, data=body, headers={
            'Content-Type': f'multipart/form-data; boundary={boundary}'
        }, method='POST')
        
        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode('utf-8'))
            return (True, "Foto enviada") if result.get("ok") else (False, result.get("description", "Erro"))
                
    except Exception as e:
        return False, str(e)

def send_telegram_photo_by_url(chat_id, photo_url, caption=""):
    """Envia foto por URL (para galeria)"""
    if not TELEGRAM_TOKEN:
        return False, "Token não configurado"
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    
    try:
        data = json.dumps({
            "chat_id": chat_id,
            "photo": photo_url,
            "caption": caption
        }).encode('utf-8')
        
        req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'}, method='POST')
        
        with urllib.request.urlopen(req, timeout=15) as response:
            result = json.loads(response.read().decode('utf-8'))
            return (True, "Enviado") if result.get("ok") else (False, result.get("description", "Erro"))
    except Exception as e:
        return False, str(e)

# ================= ADMIN LOGGING =================
def log_admin_action(action, details="", uid=None):
    """Registra ação do admin"""
    try:
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "details": details,
            "uid": uid
        }
        redis_client.lpush(admin_log_key(), json.dumps(log_entry))
        redis_client.ltrim(admin_log_key(), 0, 999)  # Mantém últimos 1000 logs
    except:
        pass

def get_admin_logs(limit=100):
    """Retorna logs de ações"""
    try:
        logs = redis_client.lrange(admin_log_key(), 0, limit - 1)
        return [json.loads(log) for log in logs]
    except:
        return []

# ================= CONFIG SYSTEM =================
DEFAULT_CONFIG = {
    "limite_diario": 15,
    "dias_vip": 15,
    "preco_vip_stars": 250,
    "preco_pix": "14.99",
    "preco_pix_desconto": "9.99",
    "pix_key": "mayaoficialbr@outlook.com",
    "msg_limite": "💔 Seu limite diário acabou.\nVolte amanhã ou vire VIP 💖",
    "msg_vip_ativado": "💖 Pagamento aprovado!\nVIP ativo por {dias} dias 😘",
    "msg_bom_dia": "Bom dia amor! ☀️ Como você dormiu? 💕",
    "msg_boa_noite": "Boa noite! 🌙 Durma bem, vou sonhar com você 💕",
    "msg_saudade": "Senti sua falta... 🥺 Volta pra mim? 💕",
    "horario_bom_dia": "08:00",
    "horario_boa_noite": "22:00",
}

def get_config():
    """Retorna configurações"""
    try:
        config = redis_client.get(admin_config_key())
        if config:
            saved = json.loads(config)
            # Merge with defaults
            return {**DEFAULT_CONFIG, **saved}
        return DEFAULT_CONFIG.copy()
    except:
        return DEFAULT_CONFIG.copy()

def save_config(config):
    """Salva configurações"""
    try:
        redis_client.set(admin_config_key(), json.dumps(config))
        log_admin_action("CONFIG_UPDATED", "Configurações atualizadas")
        return True
    except:
        return False

# ================= GALLERY SYSTEM =================
def get_gallery():
    """Retorna fotos da galeria"""
    try:
        photos = redis_client.lrange(admin_gallery_key(), 0, -1)
        return [json.loads(p) for p in photos]
    except:
        return []

def add_to_gallery(name, data_b64, thumbnail_b64=None):
    """Adiciona foto à galeria"""
    try:
        photo = {
            "id": hashlib.md5(f"{name}{time.time()}".encode()).hexdigest()[:12],
            "name": name,
            "data": data_b64,
            "thumbnail": thumbnail_b64 or data_b64,
            "created_at": datetime.now().isoformat()
        }
        redis_client.lpush(admin_gallery_key(), json.dumps(photo))
        log_admin_action("GALLERY_ADD", f"Foto adicionada: {name}")
        return True, photo["id"]
    except Exception as e:
        return False, str(e)

def remove_from_gallery(photo_id):
    """Remove foto da galeria"""
    try:
        photos = get_gallery()
        for i, p in enumerate(photos):
            if p["id"] == photo_id:
                redis_client.lrem(admin_gallery_key(), 1, json.dumps(p))
                log_admin_action("GALLERY_REMOVE", f"Foto removida: {p['name']}")
                return True
        return False
    except:
        return False

# ================= FAVORITES SYSTEM =================
def get_favorites():
    """Retorna lista de favoritos"""
    try:
        return list(redis_client.smembers(admin_favorites_key()))
    except:
        return []

def toggle_favorite(uid):
    """Adiciona/remove dos favoritos"""
    try:
        if redis_client.sismember(admin_favorites_key(), uid):
            redis_client.srem(admin_favorites_key(), uid)
            log_admin_action("FAVORITE_REMOVE", uid, uid)
            return False
        else:
            redis_client.sadd(admin_favorites_key(), uid)
            log_admin_action("FAVORITE_ADD", uid, uid)
            return True
    except:
        return False

def is_favorite(uid):
    try:
        return redis_client.sismember(admin_favorites_key(), uid)
    except:
        return False

# ================= NOTES/TAGS SYSTEM =================
def get_user_notes(uid):
    """Retorna notas do usuário"""
    try:
        return redis_client.get(admin_notes_key(uid)) or ""
    except:
        return ""

def save_user_notes(uid, notes):
    """Salva notas do usuário"""
    try:
        if notes.strip():
            redis_client.set(admin_notes_key(uid), notes)
        else:
            redis_client.delete(admin_notes_key(uid))
        log_admin_action("NOTES_UPDATE", f"Notas atualizadas", uid)
        return True
    except:
        return False

def get_user_tags(uid):
    """Retorna tags do usuário"""
    try:
        return list(redis_client.smembers(admin_tags_key(uid)))
    except:
        return []

def add_user_tag(uid, tag):
    """Adiciona tag ao usuário"""
    try:
        redis_client.sadd(admin_tags_key(uid), tag)
        log_admin_action("TAG_ADD", f"Tag: {tag}", uid)
        return True
    except:
        return False

def remove_user_tag(uid, tag):
    """Remove tag do usuário"""
    try:
        redis_client.srem(admin_tags_key(uid), tag)
        log_admin_action("TAG_REMOVE", f"Tag: {tag}", uid)
        return True
    except:
        return False

# ================= ALERTS SYSTEM =================
def add_alert(alert_type, message, uid=None, priority="normal"):
    """Adiciona alerta"""
    try:
        alert = {
            "id": hashlib.md5(f"{message}{time.time()}".encode()).hexdigest()[:10],
            "type": alert_type,
            "message": message,
            "uid": uid,
            "priority": priority,
            "created_at": datetime.now().isoformat(),
            "read": False
        }
        redis_client.lpush(admin_alerts_key(), json.dumps(alert))
        redis_client.ltrim(admin_alerts_key(), 0, 99)  # Mantém últimos 100
        return True
    except:
        return False

def get_alerts(unread_only=False):
    """Retorna alertas"""
    try:
        alerts = redis_client.lrange(admin_alerts_key(), 0, -1)
        result = [json.loads(a) for a in alerts]
        if unread_only:
            result = [a for a in result if not a.get("read")]
        return result
    except:
        return []

def mark_alert_read(alert_id):
    """Marca alerta como lido"""
    try:
        alerts = get_alerts()
        for i, a in enumerate(alerts):
            if a["id"] == alert_id:
                a["read"] = True
                # Atualiza no Redis
                redis_client.lset(admin_alerts_key(), i, json.dumps(a))
                return True
        return False
    except:
        return False

def mark_all_alerts_read():
    """Marca todos alertas como lidos"""
    try:
        alerts = get_alerts()
        redis_client.delete(admin_alerts_key())
        for a in alerts:
            a["read"] = True
            redis_client.rpush(admin_alerts_key(), json.dumps(a))
        return True
    except:
        return False

def get_unread_count():
    """Retorna contagem de não lidos"""
    return len(get_alerts(unread_only=True))

# ================= PIX PENDING SYSTEM =================
def add_pix_pending(uid, username, amount, has_discount=False):
    """Adiciona PIX pendente"""
    try:
        entry = {
            "uid": uid,
            "username": username,
            "amount": amount,
            "has_discount": has_discount,
            "created_at": datetime.now().isoformat()
        }
        redis_client.hset(pix_pending_list_key(), uid, json.dumps(entry))
        add_alert("pix", f"💳 Novo comprovante PIX de {username or uid}", uid, "high")
        return True
    except:
        return False

def get_pix_pending():
    """Retorna PIX pendentes"""
    try:
        pending = redis_client.hgetall(pix_pending_list_key())
        return [json.loads(v) for v in pending.values()]
    except:
        return []

def remove_pix_pending(uid):
    """Remove PIX pendente (aprovado/rejeitado)"""
    try:
        redis_client.hdel(pix_pending_list_key(), uid)
        return True
    except:
        return False

# ================= STATISTICS SYSTEM =================
def record_daily_stat(stat_type, increment=1):
    """Registra estatística diária"""
    try:
        today = date.today().isoformat()
        key = daily_stats_key(today)
        redis_client.hincrby(key, stat_type, increment)
        redis_client.expire(key, 86400 * 90)  # 90 dias
    except:
        pass

def get_daily_stats(d):
    """Retorna stats de um dia"""
    try:
        stats = redis_client.hgetall(daily_stats_key(d))
        return {k: int(v) for k, v in stats.items()}
    except:
        return {}

def get_stats_range(days=30):
    """Retorna stats dos últimos X dias"""
    result = []
    for i in range(days):
        d = (date.today() - timedelta(days=i)).isoformat()
        stats = get_daily_stats(d)
        stats["date"] = d
        result.append(stats)
    return list(reversed(result))

# ================= BROADCAST SYSTEM =================
def save_broadcast_history(message, filters, sent_count, failed_count):
    """Salva histórico de broadcast"""
    try:
        entry = {
            "message": message[:200],
            "filters": filters,
            "sent": sent_count,
            "failed": failed_count,
            "created_at": datetime.now().isoformat()
        }
        redis_client.lpush(broadcast_history_key(), json.dumps(entry))
        redis_client.ltrim(broadcast_history_key(), 0, 49)  # Últimos 50
        return True
    except:
        return False

def get_broadcast_history():
    """Retorna histórico de broadcasts"""
    try:
        history = redis_client.lrange(broadcast_history_key(), 0, -1)
        return [json.loads(h) for h in history]
    except:
        return []

# ================= TAKEOVER SYSTEM =================
def start_takeover(uid):
    """Admin assume controle da conversa"""
    try:
        # Salva estado atual de pausa/trava para restaurar depois
        current_paused = redis_client.get(f"paused:{uid}")
        current_ignored = redis_client.get(f"ignored:{uid}")
        
        redis_client.hset(admin_takeover_key(uid), mapping={
            "active": "1",
            "started_at": datetime.now().isoformat(),
            "prev_paused": current_paused or "",
            "prev_ignored": current_ignored or ""
        })
        
        # Pausa a IA
        redis_client.set(f"paused:{uid}", "admin_takeover")
        
        log_admin_action("TAKEOVER_START", "Admin assumiu controle", uid)
        return True
    except Exception as e:
        return False

def end_takeover(uid):
    """Admin libera controle da conversa"""
    try:
        takeover_data = redis_client.hgetall(admin_takeover_key(uid))
        
        # Restaura estado anterior
        prev_paused = takeover_data.get("prev_paused", "")
        prev_ignored = takeover_data.get("prev_ignored", "")
        
        if prev_paused:
            redis_client.set(f"paused:{uid}", prev_paused)
        else:
            redis_client.delete(f"paused:{uid}")
            
        if prev_ignored:
            redis_client.set(f"ignored:{uid}", prev_ignored)
        else:
            redis_client.delete(f"ignored:{uid}")
        
        # Remove takeover
        redis_client.delete(admin_takeover_key(uid))
        
        log_admin_action("TAKEOVER_END", "Admin liberou controle", uid)
        return True
    except Exception as e:
        return False

def is_takeover_active(uid):
    """Verifica se admin está no controle"""
    try:
        return redis_client.hget(admin_takeover_key(uid), "active") == "1"
    except:
        return False

# ================= AÇÕES ADMIN =================
def save_admin_message(uid, text):
    try:
        timestamp = datetime.now().strftime("%H:%M:%S")
        redis_client.rpush(f"chatlog:{uid}", f"[{timestamp}] ADMIN: {text[:100]}")
        redis_client.ltrim(f"chatlog:{uid}", -200, -1)
        return True
    except:
        return False

def activate_vip(uid, days=15):
    try:
        vip_until = datetime.now() + timedelta(days=days)
        redis_client.set(f"vip:{uid}", vip_until.isoformat())
        for key in ["pix_pending", "pix_clicked", "pix_interest", "flash_discount"]:
            redis_client.delete(f"{key}:{uid}")
        remove_pix_pending(uid)
        record_daily_stat("vips_activated")
        log_admin_action("VIP_ACTIVATED", f"{days} dias", uid)
        return True, f"VIP até {vip_until.strftime('%d/%m/%Y')}"
    except Exception as e:
        return False, str(e)

def reset_daily_limit(uid):
    try:
        redis_client.delete(f"count:{uid}:{date.today()}")
        log_admin_action("LIMIT_RESET", "", uid)
        return True, "Limite resetado"
    except Exception as e:
        return False, str(e)

def give_bonus_messages(uid, amount=5):
    try:
        current = int(redis_client.get(f"bonus:{uid}") or 0)
        redis_client.set(f"bonus:{uid}", current + amount)
        redis_client.expire(f"bonus:{uid}", 86400 * 7)
        log_admin_action("BONUS_GIVEN", f"+{amount}", uid)
        return True, f"+{amount} msgs (total: {current + amount})"
    except Exception as e:
        return False, str(e)

def clear_user_memory(uid):
    try:
        redis_client.delete(f"memory:{uid}")
        log_admin_action("MEMORY_CLEARED", "", uid)
        return True, "Memória limpa"
    except Exception as e:
        return False, str(e)

def unpause_user(uid):
    try:
        redis_client.delete(f"paused:{uid}")
        redis_client.delete(f"ignored:{uid}")
        log_admin_action("USER_UNPAUSED", "", uid)
        return True, "Gatilhos reativados"
    except Exception as e:
        return False, str(e)

def blacklist_user(uid):
    try:
        redis_client.sadd("blacklist", str(uid))
        log_admin_action("USER_BLACKLISTED", "", uid)
        return True, "Usuário bloqueado"
    except Exception as e:
        return False, str(e)

def unblacklist_user(uid):
    try:
        redis_client.srem("blacklist", str(uid))
        log_admin_action("USER_UNBLACKLISTED", "", uid)
        return True, "Usuário desbloqueado"
    except Exception as e:
        return False, str(e)

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
        # Também pega do all_users set
        all_users = redis_client.smembers("all_users")
        users.update(all_users)
    except:
        pass
    return list(users)

def get_user_messages(uid):
    if not check_redis():
        return []
    messages = []
    seen = set()
    try:
        logs = redis_client.lrange(f"chatlog:{uid}", 0, -1)
        for log in logs:
            msg = parse_chat_message(log)
            if msg:
                # Cria chave única para detectar duplicatas
                msg_key = f"{msg['role']}:{msg['time']}:{msg['text']}"
                if msg_key not in seen:
                    seen.add(msg_key)
                    messages.append(msg)
    except:
        pass
    return messages

def parse_chat_message(log_line):
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
                    role_map = {
                        "user": "user", "sophia": "assistant", "admin": "admin",
                        "system": "system", "action": "action", "info": "info",
                        "error": "error", "blocked": "blocked",
                    }
                    return {
                        "role": role_map.get(role, "system"),
                        "text": text,
                        "time": timestamp_str
                    }
    except:
        pass
    return None

def get_user_stats(uid):
    stats = {
        "total_messages": 0, "user_messages": 0, "sophia_messages": 0,
        "last_activity": None, "last_message_preview": None,
        "status": "offline", "is_vip": False, "is_locked": False,
        "vip_until": None, "today_count": 0
    }
    
    try:
        vip_until = redis_client.get(f"vip:{uid}")
        if vip_until:
            vip_dt = datetime.fromisoformat(vip_until)
            stats["is_vip"] = vip_dt > datetime.now()
            stats["vip_until"] = vip_dt.strftime("%d/%m/%Y") if stats["is_vip"] else None
    except:
        pass
    
    try:
        count = int(redis_client.get(f"count:{uid}:{date.today()}") or 0)
        stats["today_count"] = count
        stats["is_locked"] = count >= 15 and not stats["is_vip"]
    except:
        pass
    
    messages = get_user_messages(uid)
    stats["total_messages"] = len(messages)
    
    last_user_msg = None
    for msg in messages:
        if msg["role"] == "user":
            stats["user_messages"] += 1
            last_user_msg = msg["text"]
        elif msg["role"] == "assistant":
            stats["sophia_messages"] += 1
    
    if last_user_msg:
        stats["last_message_preview"] = last_user_msg[:60] + "..." if len(last_user_msg) > 60 else last_user_msg
    
    try:
        last_act = redis_client.get(f"last_activity:{uid}")
        if last_act:
            stats["last_activity"] = datetime.fromisoformat(last_act)
    except:
        pass
    
    if stats["last_activity"]:
        diff = (datetime.now() - stats["last_activity"]).total_seconds() / 60
        if diff < ONLINE_THRESHOLD:
            stats["status"] = "online"
        elif diff < IDLE_THRESHOLD:
            stats["status"] = "idle"
        else:
            stats["status"] = "offline"
    
    return stats

def get_global_stats():
    users = get_all_users()
    total = len(users)
    vips = online = idle = locked = 0
    
    for uid in users:
        s = get_user_stats(uid)
        if s["is_vip"]: vips += 1
        if s["status"] == "online": online += 1
        elif s["status"] == "idle": idle += 1
        if s["is_locked"]: locked += 1
    
    return {"total": total, "vips": vips, "online": online, "idle": idle, "locked": locked}

def format_time_ago(dt):
    if not dt:
        return "Nunca"
    diff = (datetime.now() - dt).total_seconds()
    if diff < 60: return "Agora"
    if diff < 3600: return f"{int(diff/60)}min"
    if diff < 86400: return f"{int(diff/3600)}h"
    return f"{int(diff/86400)}d"

# ================= MAIN STYLES =================
STYLES = """
<style>
:root {
    --primary: #667eea;
    --primary-dark: #5a67d8;
    --secondary: #764ba2;
    --success: #10b981;
    --warning: #f59e0b;
    --danger: #ef4444;
    --dark-bg: #0f0f1a;
    --dark-card: #1a1a2e;
    --dark-border: #2d2d44;
    --light-bg: #f0f2f5;
    --light-card: #ffffff;
    --radius: 16px;
    --shadow: 0 4px 20px rgba(0,0,0,0.08);
}

* { margin: 0; padding: 0; box-sizing: border-box; }

body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: var(--light-bg);
    color: #333;
    min-height: 100vh;
    transition: all 0.3s;
}

body.dark {
    background: var(--dark-bg);
    color: #e4e4e7;
}

body.dark .card, body.dark .sidebar, body.dark .chat-header-bar,
body.dark .chat-input-area, body.dark .bottom-sheet, body.dark .modal-content {
    background: var(--dark-card);
    border-color: var(--dark-border);
}

body.dark .search-input, body.dark .form-input, body.dark .chat-input {
    background: var(--dark-bg);
    border-color: var(--dark-border);
    color: #e4e4e7;
}

/* ===== SIDEBAR ===== */
.sidebar {
    position: fixed;
    top: 0;
    left: -280px;
    width: 280px;
    height: 100vh;
    background: var(--light-card);
    z-index: 1000;
    transition: left 0.3s ease;
    box-shadow: 5px 0 30px rgba(0,0,0,0.1);
    display: flex;
    flex-direction: column;
}

.sidebar.open { left: 0; }

.sidebar-header {
    padding: 25px 20px;
    background: linear-gradient(135deg, var(--primary), var(--secondary));
    color: white;
}

.sidebar-header h2 { font-size: 20px; }
.sidebar-header p { opacity: 0.8; font-size: 12px; margin-top: 5px; }

.sidebar-menu {
    flex: 1;
    overflow-y: auto;
    padding: 15px 0;
}

.menu-item {
    display: flex;
    align-items: center;
    gap: 15px;
    padding: 15px 25px;
    color: inherit;
    text-decoration: none;
    transition: all 0.2s;
    border-left: 3px solid transparent;
}

.menu-item:hover, .menu-item.active {
    background: rgba(102, 126, 234, 0.1);
    border-left-color: var(--primary);
}

.menu-item .icon { font-size: 20px; width: 24px; text-align: center; }
.menu-item .badge {
    margin-left: auto;
    background: var(--danger);
    color: white;
    padding: 2px 8px;
    border-radius: 10px;
    font-size: 11px;
}

.sidebar-footer {
    padding: 15px 20px;
    border-top: 1px solid rgba(0,0,0,0.1);
}

.overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0,0,0,0.5);
    z-index: 999;
    opacity: 0;
    visibility: hidden;
    transition: all 0.3s;
}

.overlay.active { opacity: 1; visibility: visible; }

/* ===== HEADER ===== */
.header {
    position: sticky;
    top: 0;
    z-index: 100;
    background: linear-gradient(135deg, var(--primary), var(--secondary));
    color: white;
    padding: 15px 20px;
    display: flex;
    align-items: center;
    gap: 15px;
}

.hamburger {
    display: flex;
    flex-direction: column;
    gap: 5px;
    cursor: pointer;
    padding: 5px;
}

.hamburger span {
    width: 24px;
    height: 3px;
    background: white;
    border-radius: 3px;
    transition: all 0.3s;
}

.header h1 { font-size: 18px; flex: 1; }

.header-actions { display: flex; gap: 15px; align-items: center; }

.header-icon {
    position: relative;
    font-size: 20px;
    cursor: pointer;
    padding: 5px;
}

.header-icon .badge {
    position: absolute;
    top: -5px;
    right: -5px;
    background: var(--danger);
    color: white;
    width: 18px;
    height: 18px;
    border-radius: 50%;
    font-size: 10px;
    display: flex;
    align-items: center;
    justify-content: center;
}

.theme-toggle {
    width: 50px;
    height: 26px;
    background: rgba(255,255,255,0.2);
    border-radius: 13px;
    position: relative;
    cursor: pointer;
}

.theme-toggle::after {
    content: '☀️';
    position: absolute;
    left: 3px;
    top: 3px;
    width: 20px;
    height: 20px;
    background: white;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 12px;
    transition: all 0.3s;
}

body.dark .theme-toggle::after {
    content: '🌙';
    left: 27px;
}

/* ===== CONTAINER ===== */
.container { max-width: 1400px; margin: 0 auto; padding: 15px; }

/* ===== CARDS ===== */
.card {
    background: var(--light-card);
    border-radius: var(--radius);
    padding: 20px;
    box-shadow: var(--shadow);
    margin-bottom: 15px;
}

.card-title {
    font-size: 16px;
    font-weight: 600;
    margin-bottom: 15px;
    display: flex;
    align-items: center;
    gap: 10px;
}

/* ===== STATS ===== */
.stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    gap: 12px;
}

.stat-card {
    background: var(--light-card);
    padding: 20px;
    border-radius: var(--radius);
    text-align: center;
    box-shadow: var(--shadow);
}

.stat-number {
    font-size: 32px;
    font-weight: 700;
    background: linear-gradient(135deg, var(--primary), var(--secondary));
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}

.stat-label { font-size: 12px; color: #888; margin-top: 5px; }

/* ===== SEARCH ===== */
.search-container { position: relative; margin-bottom: 15px; }

.search-input {
    width: 100%;
    padding: 14px 20px 14px 50px;
    border: 2px solid #e0e0e0;
    border-radius: var(--radius);
    font-size: 16px;
    transition: all 0.3s;
}

.search-input:focus { outline: none; border-color: var(--primary); }

.search-icon {
    position: absolute;
    left: 18px;
    top: 50%;
    transform: translateY(-50%);
    color: #999;
}

/* ===== CHIPS ===== */
.chips {
    display: flex;
    gap: 8px;
    overflow-x: auto;
    padding: 10px 0;
    -webkit-overflow-scrolling: touch;
}

.chip {
    flex: 0 0 auto;
    padding: 10px 18px;
    background: var(--light-card);
    border-radius: 25px;
    font-size: 13px;
    cursor: pointer;
    transition: all 0.2s;
    box-shadow: var(--shadow);
    white-space: nowrap;
}

.chip:active { transform: scale(0.95); }
.chip.active {
    background: linear-gradient(135deg, var(--primary), var(--secondary));
    color: white;
}

/* ===== USER CARDS ===== */
.user-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
    gap: 15px;
}

.user-card {
    background: var(--light-card);
    border-radius: var(--radius);
    padding: 18px;
    box-shadow: var(--shadow);
    cursor: pointer;
    transition: all 0.3s;
    border-left: 4px solid var(--primary);
}

.user-card:active { transform: scale(0.98); }
.user-card.online { border-left-color: var(--success); }
.user-card.idle { border-left-color: var(--warning); }
.user-card.offline { border-left-color: var(--danger); }

.user-header { display: flex; justify-content: space-between; align-items: flex-start; }

.user-id { font-weight: 600; font-size: 14px; color: var(--primary); }

.user-badges { display: flex; gap: 5px; flex-wrap: wrap; margin-top: 5px; }

.badge {
    padding: 3px 8px;
    border-radius: 12px;
    font-size: 10px;
    font-weight: 600;
}

.badge-vip { background: linear-gradient(135deg, #ffd700, #ffb300); color: #333; }
.badge-locked { background: var(--danger); color: white; }
.badge-online { background: var(--success); color: white; }
.badge-idle { background: var(--warning); color: white; }
.badge-offline { background: #ccc; color: #666; }
.badge-favorite { background: #ff6b6b; color: white; }

.user-preview {
    font-size: 13px;
    color: #888;
    margin: 10px 0;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
}

.user-meta {
    display: flex;
    justify-content: space-between;
    font-size: 12px;
    color: #999;
    padding-top: 10px;
    border-top: 1px solid rgba(0,0,0,0.05);
}

/* ===== BUTTONS ===== */
.btn {
    padding: 12px 24px;
    border-radius: 12px;
    border: none;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s;
    display: inline-flex;
    align-items: center;
    gap: 8px;
}

.btn:active { transform: scale(0.95); }

.btn-primary {
    background: linear-gradient(135deg, var(--primary), var(--secondary));
    color: white;
}

.btn-success { background: var(--success); color: white; }
.btn-warning { background: var(--warning); color: white; }
.btn-danger { background: var(--danger); color: white; }
.btn-secondary { background: #e0e0e0; color: #333; }

.btn-sm { padding: 8px 16px; font-size: 12px; }

/* ===== FORM ===== */
.form-group { margin-bottom: 20px; }
.form-label { display: block; margin-bottom: 8px; font-weight: 500; font-size: 14px; }

.form-input, .form-textarea, .form-select {
    width: 100%;
    padding: 14px 18px;
    border: 2px solid #e0e0e0;
    border-radius: 12px;
    font-size: 16px;
    transition: all 0.3s;
}

.form-input:focus, .form-textarea:focus, .form-select:focus {
    outline: none;
    border-color: var(--primary);
}

.form-textarea { min-height: 120px; resize: vertical; }

/* ===== TABLE ===== */
.table-container { overflow-x: auto; }

table { width: 100%; border-collapse: collapse; }

th, td {
    padding: 12px 15px;
    text-align: left;
    border-bottom: 1px solid rgba(0,0,0,0.05);
}

th { font-weight: 600; font-size: 12px; color: #888; text-transform: uppercase; }

/* ===== CHAT ===== */
.chat-container {
    display: flex;
    flex-direction: column;
    height: calc(100vh - 60px);
}

.chat-header-bar {
    background: var(--light-card);
    padding: 15px;
    display: flex;
    align-items: center;
    gap: 15px;
    box-shadow: var(--shadow);
}

.chat-back {
    width: 40px;
    height: 40px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--light-bg);
    border-radius: 50%;
    cursor: pointer;
}

.chat-user-info { flex: 1; }
.chat-user-name { font-weight: 600; }
.chat-user-status { font-size: 12px; color: #888; }

.chat-messages {
    flex: 1;
    overflow-y: auto;
    padding: 15px;
    display: flex;
    flex-direction: column;
    gap: 10px;
}

.message {
    max-width: 85%;
    padding: 12px 16px;
    border-radius: 18px;
    animation: slideUp 0.3s ease;
}

@keyframes slideUp {
    from { opacity: 0; transform: translateY(10px); }
    to { opacity: 1; transform: translateY(0); }
}

.message-user {
    align-self: flex-end;
    background: linear-gradient(135deg, var(--primary), var(--secondary));
    color: white;
    border-bottom-right-radius: 4px;
}

.message-sophia {
    align-self: flex-start;
    background: var(--light-card);
    box-shadow: var(--shadow);
    border-bottom-left-radius: 4px;
}

.message-admin {
    align-self: flex-start;
    background: linear-gradient(135deg, var(--warning), #d97706);
    color: white;
    border-bottom-left-radius: 4px;
}

.message-system {
    align-self: center;
    background: rgba(0,0,0,0.05);
    color: #888;
    font-size: 12px;
    padding: 8px 16px;
    border-radius: 20px;
}

.message-time { font-size: 10px; opacity: 0.7; margin-top: 5px; }
.message-label { font-size: 10px; font-weight: 600; margin-bottom: 4px; opacity: 0.8; }

.chat-input-area {
    background: var(--light-card);
    padding: 15px;
    box-shadow: 0 -4px 20px rgba(0,0,0,0.05);
}

.chat-input-row { display: flex; gap: 10px; align-items: flex-end; }

.chat-input {
    flex: 1;
    padding: 14px 18px;
    border: 2px solid #e0e0e0;
    border-radius: 25px;
    font-size: 16px;
    resize: none;
    max-height: 120px;
}

.send-btn {
    width: 50px;
    height: 50px;
    border-radius: 50%;
    background: linear-gradient(135deg, var(--primary), var(--secondary));
    color: white;
    border: none;
    font-size: 20px;
    cursor: pointer;
}

.send-btn:active { transform: scale(0.9); }

/* ===== QUICK REPLIES ===== */
.quick-replies {
    display: flex;
    gap: 8px;
    overflow-x: auto;
    padding: 10px 15px;
}

.quick-reply {
    flex: 0 0 auto;
    padding: 10px 16px;
    background: var(--light-bg);
    border-radius: 20px;
    font-size: 13px;
    cursor: pointer;
}

.quick-reply:active { background: var(--primary); color: white; }

/* ===== FAB ===== */
.fab {
    position: fixed;
    bottom: 90px;
    right: 20px;
    width: 60px;
    height: 60px;
    border-radius: 50%;
    background: linear-gradient(135deg, var(--primary), var(--secondary));
    color: white;
    border: none;
    font-size: 24px;
    cursor: pointer;
    box-shadow: 0 4px 20px rgba(102, 126, 234, 0.4);
    z-index: 90;
}

.fab:active { transform: scale(0.9); }

/* ===== BOTTOM SHEET ===== */
.bottom-sheet-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0,0,0,0.5);
    z-index: 200;
    opacity: 0;
    visibility: hidden;
    transition: all 0.3s;
}

.bottom-sheet-overlay.active { opacity: 1; visibility: visible; }

.bottom-sheet {
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    background: var(--light-card);
    border-radius: 24px 24px 0 0;
    padding: 20px;
    z-index: 201;
    transform: translateY(100%);
    transition: transform 0.3s ease;
    max-height: 80vh;
    overflow-y: auto;
}

.bottom-sheet.active { transform: translateY(0); }

.bottom-sheet-handle {
    width: 40px;
    height: 4px;
    background: #ddd;
    border-radius: 2px;
    margin: 0 auto 20px;
}

.bottom-sheet-title { font-size: 18px; font-weight: 600; margin-bottom: 20px; text-align: center; }

.action-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 12px;
}

.action-btn {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 8px;
    padding: 20px 10px;
    background: var(--light-bg);
    border-radius: var(--radius);
    border: none;
    cursor: pointer;
    font-size: 12px;
}

.action-btn:active { transform: scale(0.95); }
.action-btn .icon { font-size: 28px; }
.action-btn.danger { color: var(--danger); }
.action-btn.success { color: var(--success); }
.action-btn.warning { color: var(--warning); }

/* ===== MODAL ===== */
.modal-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0,0,0,0.5);
    z-index: 300;
    display: none;
    align-items: center;
    justify-content: center;
    padding: 20px;
}

.modal-overlay.active { display: flex; }

.modal-content {
    background: var(--light-card);
    border-radius: var(--radius);
    width: 100%;
    max-width: 500px;
    max-height: 90vh;
    overflow-y: auto;
}

.modal-header {
    padding: 20px;
    border-bottom: 1px solid rgba(0,0,0,0.05);
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.modal-header h3 { font-size: 18px; }
.modal-close { font-size: 24px; cursor: pointer; padding: 5px; }
.modal-body { padding: 20px; }
.modal-footer { padding: 15px 20px; border-top: 1px solid rgba(0,0,0,0.05); display: flex; gap: 10px; justify-content: flex-end; }

/* ===== TOAST ===== */
.toast {
    position: fixed;
    bottom: 100px;
    left: 50%;
    transform: translateX(-50%) translateY(100px);
    padding: 14px 28px;
    border-radius: 30px;
    color: white;
    font-weight: 500;
    z-index: 1000;
    opacity: 0;
    transition: all 0.3s;
}

.toast.show { transform: translateX(-50%) translateY(0); opacity: 1; }
.toast.success { background: var(--success); }
.toast.error { background: var(--danger); }

/* ===== GALLERY ===== */
.gallery-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
    gap: 12px;
}

.gallery-item {
    position: relative;
    aspect-ratio: 1;
    border-radius: 12px;
    overflow: hidden;
    cursor: pointer;
}

.gallery-item img {
    width: 100%;
    height: 100%;
    object-fit: cover;
}

.gallery-item .delete-btn {
    position: absolute;
    top: 5px;
    right: 5px;
    width: 28px;
    height: 28px;
    background: var(--danger);
    color: white;
    border: none;
    border-radius: 50%;
    cursor: pointer;
    display: none;
}

.gallery-item:hover .delete-btn { display: flex; align-items: center; justify-content: center; }

/* ===== ALERTS LIST ===== */
.alert-item {
    display: flex;
    gap: 15px;
    padding: 15px;
    border-bottom: 1px solid rgba(0,0,0,0.05);
    cursor: pointer;
}

.alert-item:hover { background: rgba(0,0,0,0.02); }
.alert-item.unread { background: rgba(102, 126, 234, 0.05); }

.alert-icon { font-size: 24px; }
.alert-content { flex: 1; }
.alert-message { font-size: 14px; }
.alert-time { font-size: 11px; color: #888; margin-top: 5px; }

/* ===== CHART ===== */
.chart-container { height: 300px; position: relative; }

/* ===== LOGIN ===== */
.login-page {
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    background: linear-gradient(135deg, var(--primary), var(--secondary));
    padding: 20px;
}

.login-card {
    background: white;
    padding: 40px 30px;
    border-radius: var(--radius);
    width: 100%;
    max-width: 380px;
}

.login-logo { text-align: center; margin-bottom: 30px; }
.login-logo h1 { color: var(--primary); font-size: 28px; }
.login-logo p { color: #888; font-size: 14px; }

.error-msg {
    background: #fee;
    color: var(--danger);
    padding: 12px;
    border-radius: 8px;
    margin-bottom: 20px;
    font-size: 14px;
}

/* ===== EMPTY ===== */
.empty-state { text-align: center; padding: 60px 20px; color: #888; }
.empty-state .icon { font-size: 60px; margin-bottom: 20px; }

/* ===== RESPONSIVE ===== */
@media (max-width: 768px) {
    .stats-grid { grid-template-columns: repeat(2, 1fr); }
    .user-grid { grid-template-columns: 1fr; }
    .action-grid { grid-template-columns: repeat(3, 1fr); }
}

/* ===== PHOTO UPLOAD ===== */
.photo-upload-btn {
    width: 50px;
    height: 50px;
    border-radius: 50%;
    background: var(--light-bg);
    border: none;
    font-size: 20px;
    cursor: pointer;
}

.photo-preview-container {
    display: none;
    padding: 10px;
    background: var(--light-bg);
    border-radius: var(--radius);
    margin-bottom: 10px;
    align-items: center;
    gap: 10px;
}

.photo-preview-container.active { display: flex; }

.photo-preview-img { width: 60px; height: 60px; object-fit: cover; border-radius: 8px; }

.photo-preview-remove {
    margin-left: auto;
    background: var(--danger);
    color: white;
    border: none;
    width: 30px;
    height: 30px;
    border-radius: 50%;
    cursor: pointer;
}

/* ===== BROADCAST FILTERS ===== */
.filter-option {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px;
    background: var(--light-bg);
    border-radius: 8px;
    margin-bottom: 10px;
    cursor: pointer;
}

.filter-option input { width: 20px; height: 20px; }
</style>
"""

# ================= JAVASCRIPT COMMON =================
JS_COMMON = """
<script>
// Theme
if (localStorage.getItem('theme') === 'dark') document.body.classList.add('dark');

function toggleTheme() {
    document.body.classList.toggle('dark');
    localStorage.setItem('theme', document.body.classList.contains('dark') ? 'dark' : 'light');
}

// Sidebar
function toggleSidebar() {
    document.getElementById('sidebar').classList.toggle('open');
    document.getElementById('sidebarOverlay').classList.toggle('active');
}

// Toast
function showToast(message, type = 'success') {
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.className = 'toast ' + type + ' show';
    setTimeout(() => toast.classList.remove('show'), 3000);
}

// Modal
function openModal(id) {
    document.getElementById(id).classList.add('active');
}

function closeModal(id) {
    document.getElementById(id).classList.remove('active');
}
</script>
"""

# ================= SIDEBAR TEMPLATE =================
def render_sidebar(active_page):
    unread = get_unread_count()
    pix_count = len(get_pix_pending())
    
    return f"""
    <div class="overlay" id="sidebarOverlay" onclick="toggleSidebar()"></div>
    <div class="sidebar" id="sidebar">
        <div class="sidebar-header">
            <h2>🤖 Sophia Admin</h2>
            <p>Painel v5.0</p>
        </div>
        <div class="sidebar-menu">
            <a href="/dashboard" class="menu-item {'active' if active_page == 'dashboard' else ''}">
                <span class="icon">🏠</span> Dashboard
            </a>
            <a href="/analytics" class="menu-item {'active' if active_page == 'analytics' else ''}">
                <span class="icon">📊</span> Analytics
            </a>
            <a href="/broadcast" class="menu-item {'active' if active_page == 'broadcast' else ''}">
                <span class="icon">📢</span> Broadcast
            </a>
            <a href="/financeiro" class="menu-item {'active' if active_page == 'financeiro' else ''}">
                <span class="icon">💰</span> Financeiro
                {f'<span class="badge">{pix_count}</span>' if pix_count > 0 else ''}
            </a>
            <a href="/galeria" class="menu-item {'active' if active_page == 'galeria' else ''}">
                <span class="icon">📸</span> Galeria
            </a>
            <a href="/favoritos" class="menu-item {'active' if active_page == 'favoritos' else ''}">
                <span class="icon">⭐</span> Favoritos
            </a>
            <a href="/alertas" class="menu-item {'active' if active_page == 'alertas' else ''}">
                <span class="icon">🔔</span> Alertas
                {f'<span class="badge">{unread}</span>' if unread > 0 else ''}
            </a>
            <a href="/logs" class="menu-item {'active' if active_page == 'logs' else ''}">
                <span class="icon">📝</span> Logs
            </a>
            <a href="/exportar-txt" class="menu-item">
                <span class="icon">📥</span> Exportar Conversas
            </a>
            <a href="/config" class="menu-item {'active' if active_page == 'config' else ''}">
                <span class="icon">⚙️</span> Configurações
            </a>
        </div>
        <div class="sidebar-footer">
            <a href="/logout" class="btn btn-secondary" style="width: 100%; justify-content: center;">
                <i class="fas fa-sign-out-alt"></i> Sair
            </a>
        </div>
    </div>
    """

# ================= HEADER TEMPLATE =================
def render_header(title):
    unread = get_unread_count()
    return f"""
    <header class="header">
        <div class="hamburger" onclick="toggleSidebar()">
            <span></span><span></span><span></span>
        </div>
        <h1>{title}</h1>
        <div class="header-actions">
            <a href="/alertas" class="header-icon" style="color: white;">
                🔔
                {f'<span class="badge">{unread}</span>' if unread > 0 else ''}
            </a>
            <div class="theme-toggle" onclick="toggleTheme()"></div>
        </div>
    </header>
    """

# ================= BASE TEMPLATE =================
def render_page(title, content, active_page="dashboard"):
    return f"""
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
        <title>{title} - Sophia Admin</title>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        {STYLES}
    </head>
    <body>
        {render_sidebar(active_page)}
        {render_header(title)}
        {content}
        <div class="toast" id="toast"></div>
        {JS_COMMON}
    </body>
    </html>
    """

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
            log_admin_action("LOGIN", "Admin logou")
            return redirect("/dashboard")
        error = "Senha incorreta"
    
    return f"""
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Login - Sophia Admin</title>
        {STYLES}
    </head>
    <body>
        <div class="login-page">
            <div class="login-card">
                <div class="login-logo">
                    <h1>🤖 Sophia AI</h1>
                    <p>Painel Administrativo v5.0</p>
                </div>
                {f'<div class="error-msg">{error}</div>' if error else ''}
                <form method="post">
                    <div class="form-group">
                        <label class="form-label">Senha</label>
                        <input type="password" name="password" class="form-input" placeholder="Digite a senha" required autofocus>
                    </div>
                    <button type="submit" class="btn btn-primary" style="width: 100%; justify-content: center;">
                        Entrar
                    </button>
                </form>
            </div>
        </div>
    </body>
    </html>
    """

@app.route("/logout")
def logout():
    log_admin_action("LOGOUT", "Admin deslogou")
    session.clear()
    return redirect("/login")

# ================= DASHBOARD =================
@app.route("/dashboard")
def dashboard():
    if not session.get("authenticated"):
        return redirect("/login")
    
    filter_type = request.args.get('filter', 'all')
    search = request.args.get('q', '').strip()
    
    all_users = get_all_users()
    stats = get_global_stats()
    favorites = get_favorites()
    
    users_with_stats = [(uid, get_user_stats(uid)) for uid in all_users]
    
    filtered = []
    for uid, s in users_with_stats:
        if search and search.lower() not in uid.lower():
            continue
        if filter_type == 'vip' and not s['is_vip']:
            continue
        if filter_type == 'online' and s['status'] != 'online':
            continue
        if filter_type == 'idle' and s['status'] != 'idle':
            continue
        if filter_type == 'locked' and not s['is_locked']:
            continue
        if filter_type == 'favorites' and uid not in favorites:
            continue
        filtered.append((uid, s))
    
    filtered.sort(key=lambda x: x[1]['last_activity'] or datetime.min, reverse=True)
    
    users_html = ""
    for uid, s in filtered[:50]:
        status_badge = {"online": "badge-online", "idle": "badge-idle", "offline": "badge-offline"}.get(s['status'], "badge-offline")
        status_text = {"online": "Online", "idle": "Ausente", "offline": "Offline"}.get(s['status'], "Offline")
        is_fav = uid in favorites
        
        users_html += f"""
        <div class="user-card {s['status']}" onclick="window.location.href='/chat/{uid}'">
            <div class="user-header">
                <div>
                    <div class="user-id">{uid[:20]}{'...' if len(uid) > 20 else ''}</div>
                    <div class="user-badges">
                        <span class="badge {status_badge}">{status_text}</span>
                        {'<span class="badge badge-vip">👑 VIP</span>' if s['is_vip'] else ''}
                        {'<span class="badge badge-locked">🔒</span>' if s['is_locked'] else ''}
                        {'<span class="badge badge-favorite">⭐</span>' if is_fav else ''}
                    </div>
                </div>
            </div>
            {f'<div class="user-preview">💬 {html.escape(s["last_message_preview"])}</div>' if s['last_message_preview'] else ''}
            <div class="user-meta">
                <span>📊 {s['total_messages']} msgs</span>
                <span>🕐 {format_time_ago(s['last_activity'])}</span>
            </div>
        </div>
        """
    
    if not users_html:
        users_html = '<div class="empty-state"><div class="icon">😔</div><p>Nenhum usuário encontrado</p></div>'
    
    content = f"""
    <div class="container">
        <div class="stats-grid" style="margin-bottom: 20px;">
            <div class="stat-card">
                <div class="stat-number">{stats['total']}</div>
                <div class="stat-label">👥 Total</div>
            </div>
            <div class="stat-card">
                <div class="stat-number" style="color: var(--success);">{stats['online']}</div>
                <div class="stat-label">🟢 Online</div>
            </div>
            <div class="stat-card">
                <div class="stat-number" style="color: var(--warning);">{stats['vips']}</div>
                <div class="stat-label">👑 VIPs</div>
            </div>
            <div class="stat-card">
                <div class="stat-number" style="color: var(--danger);">{stats['locked']}</div>
                <div class="stat-label">🔒 Travados</div>
            </div>
        </div>
        
        <div class="search-container">
            <i class="fas fa-search search-icon"></i>
            <input type="text" class="search-input" placeholder="Buscar por ID..." 
                   value="{html.escape(search)}" onkeyup="handleSearch(event)">
        </div>
        
        <div class="chips">
            <div class="chip {'active' if filter_type == 'all' else ''}" onclick="setFilter('all')">Todos</div>
            <div class="chip {'active' if filter_type == 'online' else ''}" onclick="setFilter('online')">🟢 Online</div>
            <div class="chip {'active' if filter_type == 'vip' else ''}" onclick="setFilter('vip')">👑 VIPs</div>
            <div class="chip {'active' if filter_type == 'locked' else ''}" onclick="setFilter('locked')">🔒 Travados</div>
            <div class="chip {'active' if filter_type == 'favorites' else ''}" onclick="setFilter('favorites')">⭐ Favoritos</div>
        </div>
        
        <div class="user-grid" style="margin-top: 15px;">
            {users_html}
        </div>
    </div>
    
    <script>
        let searchTimeout;
        function handleSearch(e) {{
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => {{
                window.location.href = '/dashboard?q=' + encodeURIComponent(e.target.value) + '&filter={filter_type}';
            }}, 500);
        }}
        
        function setFilter(filter) {{
            const search = document.querySelector('.search-input').value;
            window.location.href = '/dashboard?filter=' + filter + (search ? '&q=' + encodeURIComponent(search) : '');
        }}
    </script>
    """
    
    return render_page("Dashboard", content, "dashboard")

# ================= ANALYTICS =================
@app.route("/analytics")
def analytics():
    if not session.get("authenticated"):
        return redirect("/login")
    
    # Dados dos últimos 7 dias
    stats_data = get_stats_range(7)
    
    # Estatísticas gerais
    all_users = get_all_users()
    total_users = len(all_users)
    
    vip_count = 0
    total_msgs = 0
    for uid in all_users:
        s = get_user_stats(uid)
        if s["is_vip"]: vip_count += 1
        total_msgs += s["total_messages"]
    
    conversion_rate = (vip_count / total_users * 100) if total_users > 0 else 0
    
    # Dados para gráficos
    labels = [s["date"][-5:] for s in stats_data]  # MM-DD
    vips_data = [s.get("vips_activated", 0) for s in stats_data]
    msgs_data = [s.get("messages", 0) for s in stats_data]
    
    content = f"""
    <div class="container">
        <div class="stats-grid" style="margin-bottom: 20px;">
            <div class="stat-card">
                <div class="stat-number">{total_users}</div>
                <div class="stat-label">Total Usuários</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{vip_count}</div>
                <div class="stat-label">VIPs Ativos</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{conversion_rate:.1f}%</div>
                <div class="stat-label">Taxa Conversão</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{total_msgs}</div>
                <div class="stat-label">Total Mensagens</div>
            </div>
        </div>
        
        <div class="card">
            <div class="card-title">📈 VIPs Ativados (7 dias)</div>
            <div class="chart-container">
                <canvas id="vipsChart"></canvas>
            </div>
        </div>
        
        <div class="card">
            <div class="card-title">💬 Mensagens por Dia</div>
            <div class="chart-container">
                <canvas id="msgsChart"></canvas>
            </div>
        </div>
    </div>
    
    <script>
        const labels = {json.dumps(labels)};
        
        new Chart(document.getElementById('vipsChart'), {{
            type: 'bar',
            data: {{
                labels: labels,
                datasets: [{{
                    label: 'VIPs Ativados',
                    data: {json.dumps(vips_data)},
                    backgroundColor: 'rgba(102, 126, 234, 0.8)',
                    borderRadius: 8
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{ legend: {{ display: false }} }}
            }}
        }});
        
        new Chart(document.getElementById('msgsChart'), {{
            type: 'line',
            data: {{
                labels: labels,
                datasets: [{{
                    label: 'Mensagens',
                    data: {json.dumps(msgs_data)},
                    borderColor: '#10b981',
                    backgroundColor: 'rgba(16, 185, 129, 0.1)',
                    fill: true,
                    tension: 0.4
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{ legend: {{ display: false }} }}
            }}
        }});
    </script>
    """
    
    return render_page("Analytics", content, "analytics")

# ================= BROADCAST =================
@app.route("/broadcast", methods=["GET", "POST"])
def broadcast():
    if not session.get("authenticated"):
        return redirect("/login")
    
    result_html = ""
    
    if request.method == "POST":
        message = request.form.get("message", "").strip()
        filter_vip = request.form.get("filter_vip") == "on"
        filter_free = request.form.get("filter_free") == "on"
        filter_active = request.form.get("filter_active") == "on"
        
        if message:
            all_users = get_all_users()
            sent = 0
            failed = 0
            
            for uid in all_users:
                stats = get_user_stats(uid)
                
                # Aplicar filtros
                if filter_vip and not stats["is_vip"]:
                    continue
                if filter_free and stats["is_vip"]:
                    continue
                if filter_active:
                    if not stats["last_activity"]:
                        continue
                    hours = (datetime.now() - stats["last_activity"]).total_seconds() / 3600
                    if hours > 72:  # 3 dias
                        continue
                
                success, _ = send_telegram_message(uid, message)
                if success:
                    sent += 1
                else:
                    failed += 1
            
            # Salvar histórico
            filters = []
            if filter_vip: filters.append("VIP")
            if filter_free: filters.append("FREE")
            if filter_active: filters.append("Ativos 72h")
            
            save_broadcast_history(message, ", ".join(filters) or "Todos", sent, failed)
            log_admin_action("BROADCAST", f"Enviado para {sent} usuários")
            
            result_html = f"""
            <div class="card" style="background: linear-gradient(135deg, var(--success), #059669); color: white;">
                <h3>✅ Broadcast Enviado!</h3>
                <p style="margin-top: 10px;">📤 Enviados: {sent} | ❌ Falhas: {failed}</p>
            </div>
            """
    
    # Histórico
    history = get_broadcast_history()
    history_html = ""
    for h in history[:10]:
        dt = datetime.fromisoformat(h["created_at"]).strftime("%d/%m %H:%M")
        history_html += f"""
        <tr>
            <td>{dt}</td>
            <td>{html.escape(h['message'][:50])}...</td>
            <td>{h.get('filters', 'Todos')}</td>
            <td>{h['sent']}</td>
        </tr>
        """
    
    content = f"""
    <div class="container">
        {result_html}
        
        <div class="card">
            <div class="card-title">📢 Enviar Broadcast</div>
            <form method="post">
                <div class="form-group">
                    <label class="form-label">Mensagem</label>
                    <textarea name="message" class="form-input form-textarea" placeholder="Digite a mensagem..." required></textarea>
                </div>
                
                <div class="form-group">
                    <label class="form-label">Filtros</label>
                    <label class="filter-option">
                        <input type="checkbox" name="filter_vip"> Apenas VIPs
                    </label>
                    <label class="filter-option">
                        <input type="checkbox" name="filter_free"> Apenas FREE
                    </label>
                    <label class="filter-option">
                        <input type="checkbox" name="filter_active" checked> Ativos (últimas 72h)
                    </label>
                </div>
                
                <button type="submit" class="btn btn-primary">
                    <i class="fas fa-paper-plane"></i> Enviar Broadcast
                </button>
            </form>
        </div>
        
        <div class="card">
            <div class="card-title">📜 Histórico</div>
            <div class="table-container">
                <table>
                    <thead>
                        <tr>
                            <th>Data</th>
                            <th>Mensagem</th>
                            <th>Filtros</th>
                            <th>Enviados</th>
                        </tr>
                    </thead>
                    <tbody>
                        {history_html if history_html else '<tr><td colspan="4" style="text-align:center;">Nenhum broadcast ainda</td></tr>'}
                    </tbody>
                </table>
            </div>
        </div>
    </div>
    """
    
    return render_page("Broadcast", content, "broadcast")

# ================= FINANCEIRO =================
@app.route("/financeiro")
def financeiro():
    if not session.get("authenticated"):
        return redirect("/login")
    
    pending = get_pix_pending()
    
    # Contar VIPs ativos
    all_users = get_all_users()
    vip_count = sum(1 for uid in all_users if get_user_stats(uid)["is_vip"])
    
    config = get_config()
    preco = float(config.get("preco_pix", "14.99"))
    receita_estimada = vip_count * preco
    
    pending_html = ""
    for p in pending:
        dt = datetime.fromisoformat(p["created_at"]).strftime("%d/%m %H:%M")
        pending_html += f"""
        <div class="card" style="border-left: 4px solid var(--warning);">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <strong>{p.get('username') or p['uid']}</strong>
                    <p style="font-size: 12px; color: #888;">ID: {p['uid']}</p>
                    <p style="font-size: 12px; color: #888;">💰 R$ {p.get('amount', preco)} • {dt}</p>
                </div>
                <div style="display: flex; gap: 10px;">
                    <button class="btn btn-success btn-sm" onclick="aprovarPix('{p['uid']}')">✅ Aprovar</button>
                    <button class="btn btn-danger btn-sm" onclick="rejeitarPix('{p['uid']}')">❌ Rejeitar</button>
                </div>
            </div>
        </div>
        """
    
    content = f"""
    <div class="container">
        <div class="stats-grid" style="margin-bottom: 20px;">
            <div class="stat-card">
                <div class="stat-number">{len(pending)}</div>
                <div class="stat-label">⏳ PIX Pendentes</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{vip_count}</div>
                <div class="stat-label">👑 VIPs Ativos</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">R$ {receita_estimada:.0f}</div>
                <div class="stat-label">💰 Receita Est.</div>
            </div>
        </div>
        
        <div class="card">
            <div class="card-title">💳 Comprovantes Pendentes</div>
            {pending_html if pending_html else '<div class="empty-state"><div class="icon">✅</div><p>Nenhum comprovante pendente</p></div>'}
        </div>
    </div>
    
    <script>
        async function aprovarPix(uid) {{
            if (!confirm('Aprovar VIP para ' + uid + '?')) return;
            
            const resp = await fetch('/api/pix/aprovar/' + uid, {{ method: 'POST' }});
            const data = await resp.json();
            
            if (data.success) {{
                showToast('✅ VIP ativado!', 'success');
                setTimeout(() => location.reload(), 1000);
            }} else {{
                showToast('❌ ' + data.error, 'error');
            }}
        }}
        
        async function rejeitarPix(uid) {{
            if (!confirm('Rejeitar PIX de ' + uid + '?')) return;
            
            const resp = await fetch('/api/pix/rejeitar/' + uid, {{ method: 'POST' }});
            const data = await resp.json();
            
            if (data.success) {{
                showToast('PIX rejeitado', 'success');
                setTimeout(() => location.reload(), 1000);
            }}
        }}
    </script>
    """
    
    return render_page("Financeiro", content, "financeiro")

# ================= GALERIA =================
@app.route("/galeria", methods=["GET", "POST"])
def galeria():
    if not session.get("authenticated"):
        return redirect("/login")
    
    if request.method == "POST" and "photo" in request.files:
        photo = request.files["photo"]
        if photo.filename:
            name = request.form.get("name", photo.filename)
            data = base64.b64encode(photo.read()).decode('utf-8')
            add_to_gallery(name, data)
            return redirect("/galeria")
    
    photos = get_gallery()
    
    gallery_html = ""
    for p in photos:
        gallery_html += f"""
        <div class="gallery-item" onclick="selectPhoto('{p['id']}', '{p['name']}')">
            <img src="data:image/jpeg;base64,{p['data'][:1000]}..." alt="{p['name']}" 
                 onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%22100%22 height=%22100%22><rect fill=%22%23ddd%22 width=%22100%22 height=%22100%22/></svg>'">
            <button class="delete-btn" onclick="event.stopPropagation(); deletePhoto('{p['id']}')">&times;</button>
        </div>
        """
    
    content = f"""
    <div class="container">
        <div class="card">
            <div class="card-title">📤 Upload de Foto</div>
            <form method="post" enctype="multipart/form-data" style="display: flex; gap: 10px; flex-wrap: wrap;">
                <input type="text" name="name" class="form-input" placeholder="Nome da foto" style="flex: 1; min-width: 200px;">
                <input type="file" name="photo" accept="image/*" required style="flex: 1;">
                <button type="submit" class="btn btn-primary">Enviar</button>
            </form>
        </div>
        
        <div class="card">
            <div class="card-title">🖼️ Galeria ({len(photos)} fotos)</div>
            <div class="gallery-grid">
                {gallery_html if gallery_html else '<p style="text-align:center; color:#888;">Nenhuma foto na galeria</p>'}
            </div>
        </div>
    </div>
    
    <script>
        function selectPhoto(id, name) {{
            // Copiar ID para clipboard ou abrir modal de envio
            showToast('📷 Foto: ' + name, 'success');
        }}
        
        async function deletePhoto(id) {{
            if (!confirm('Excluir esta foto?')) return;
            
            const resp = await fetch('/api/galeria/delete/' + id, {{ method: 'POST' }});
            if (resp.ok) {{
                showToast('Foto excluída', 'success');
                setTimeout(() => location.reload(), 500);
            }}
        }}
    </script>
    """
    
    return render_page("Galeria", content, "galeria")

# ================= FAVORITOS =================
@app.route("/favoritos")
def favoritos():
    if not session.get("authenticated"):
        return redirect("/login")
    
    fav_ids = get_favorites()
    
    users_html = ""
    for uid in fav_ids:
        s = get_user_stats(uid)
        status_badge = {"online": "badge-online", "idle": "badge-idle", "offline": "badge-offline"}.get(s['status'], "badge-offline")
        
        users_html += f"""
        <div class="user-card {s['status']}" onclick="window.location.href='/chat/{uid}'">
            <div class="user-header">
                <div>
                    <div class="user-id">⭐ {uid[:20]}</div>
                    <div class="user-badges">
                        <span class="badge {status_badge}">{s['status'].title()}</span>
                        {'<span class="badge badge-vip">👑 VIP</span>' if s['is_vip'] else ''}
                    </div>
                </div>
            </div>
            <div class="user-meta">
                <span>📊 {s['total_messages']} msgs</span>
                <span>🕐 {format_time_ago(s['last_activity'])}</span>
            </div>
        </div>
        """
    
    content = f"""
    <div class="container">
        <div class="card">
            <div class="card-title">⭐ Usuários Favoritos ({len(fav_ids)})</div>
            <p style="color: #888; font-size: 14px; margin-bottom: 20px;">
                Marque usuários como favoritos na tela de chat para acesso rápido
            </p>
        </div>
        
        <div class="user-grid">
            {users_html if users_html else '<div class="empty-state"><div class="icon">⭐</div><p>Nenhum favorito ainda</p></div>'}
        </div>
    </div>
    """
    
    return render_page("Favoritos", content, "favoritos")

# ================= ALERTAS =================
@app.route("/alertas")
def alertas():
    if not session.get("authenticated"):
        return redirect("/login")
    
    alerts = get_alerts()
    
    alerts_html = ""
    for a in alerts:
        dt = datetime.fromisoformat(a["created_at"]).strftime("%d/%m %H:%M")
        icon = {"pix": "💳", "new_user": "👤", "vip_expiring": "⏰", "error": "❌"}.get(a["type"], "🔔")
        
        alerts_html += f"""
        <div class="alert-item {'unread' if not a['read'] else ''}" onclick="markRead('{a['id']}')">
            <div class="alert-icon">{icon}</div>
            <div class="alert-content">
                <div class="alert-message">{html.escape(a['message'])}</div>
                <div class="alert-time">{dt}</div>
            </div>
        </div>
        """
    
    content = f"""
    <div class="container">
        <div class="card">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
                <div class="card-title" style="margin: 0;">🔔 Alertas</div>
                <button class="btn btn-sm btn-secondary" onclick="markAllRead()">Marcar todos como lidos</button>
            </div>
            
            {alerts_html if alerts_html else '<div class="empty-state"><div class="icon">🔔</div><p>Nenhum alerta</p></div>'}
        </div>
    </div>
    
    <script>
        async function markRead(id) {{
            await fetch('/api/alert/read/' + id, {{ method: 'POST' }});
        }}
        
        async function markAllRead() {{
            await fetch('/api/alert/read-all', {{ method: 'POST' }});
            showToast('Todos marcados como lidos', 'success');
            setTimeout(() => location.reload(), 500);
        }}
    </script>
    """
    
    return render_page("Alertas", content, "alertas")

# ================= LOGS =================
@app.route("/logs")
def logs():
    if not session.get("authenticated"):
        return redirect("/login")
    
    admin_logs = get_admin_logs(100)
    
    logs_html = ""
    for log in admin_logs:
        dt = datetime.fromisoformat(log["timestamp"]).strftime("%d/%m %H:%M:%S")
        logs_html += f"""
        <tr>
            <td>{dt}</td>
            <td><strong>{log['action']}</strong></td>
            <td>{html.escape(log.get('details', '') or '-')}</td>
            <td>{log.get('uid', '-')}</td>
        </tr>
        """
    
    content = f"""
    <div class="container">
        <div class="card">
            <div class="card-title">📝 Logs de Ações</div>
            <div class="table-container">
                <table>
                    <thead>
                        <tr>
                            <th>Data</th>
                            <th>Ação</th>
                            <th>Detalhes</th>
                            <th>Usuário</th>
                        </tr>
                    </thead>
                    <tbody>
                        {logs_html if logs_html else '<tr><td colspan="4" style="text-align:center;">Nenhum log</td></tr>'}
                    </tbody>
                </table>
            </div>
        </div>
    </div>
    """
    
    return render_page("Logs", content, "logs")

# ================= CONFIG =================
@app.route("/config", methods=["GET", "POST"])
def config_page():
    if not session.get("authenticated"):
        return redirect("/login")
    
    config = get_config()
    saved = False
    
    if request.method == "POST":
        config["limite_diario"] = int(request.form.get("limite_diario", 15))
        config["dias_vip"] = int(request.form.get("dias_vip", 15))
        config["preco_pix"] = request.form.get("preco_pix", "14.99")
        config["preco_pix_desconto"] = request.form.get("preco_pix_desconto", "9.99")
        config["pix_key"] = request.form.get("pix_key", "")
        config["msg_limite"] = request.form.get("msg_limite", "")
        config["msg_vip_ativado"] = request.form.get("msg_vip_ativado", "")
        config["msg_bom_dia"] = request.form.get("msg_bom_dia", "")
        config["msg_boa_noite"] = request.form.get("msg_boa_noite", "")
        
        save_config(config)
        saved = True
    
    content = f"""
    <div class="container">
        {f'<div class="card" style="background: var(--success); color: white;">✅ Configurações salvas!</div>' if saved else ''}
        
        <form method="post">
            <div class="card">
                <div class="card-title">💰 Preços e Limites</div>
                
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px;">
                    <div class="form-group">
                        <label class="form-label">Limite Diário</label>
                        <input type="number" name="limite_diario" class="form-input" value="{config['limite_diario']}">
                    </div>
                    <div class="form-group">
                        <label class="form-label">Dias VIP</label>
                        <input type="number" name="dias_vip" class="form-input" value="{config['dias_vip']}">
                    </div>
                    <div class="form-group">
                        <label class="form-label">Preço PIX (R$)</label>
                        <input type="text" name="preco_pix" class="form-input" value="{config['preco_pix']}">
                    </div>
                    <div class="form-group">
                        <label class="form-label">Preço Desconto (R$)</label>
                        <input type="text" name="preco_pix_desconto" class="form-input" value="{config['preco_pix_desconto']}">
                    </div>
                </div>
                
                <div class="form-group">
                    <label class="form-label">Chave PIX</label>
                    <input type="text" name="pix_key" class="form-input" value="{html.escape(config.get('pix_key', ''))}">
                </div>
            </div>
            
            <div class="card">
                <div class="card-title">💬 Mensagens</div>
                
                <div class="form-group">
                    <label class="form-label">Mensagem de Limite</label>
                    <textarea name="msg_limite" class="form-input form-textarea">{html.escape(config.get('msg_limite', ''))}</textarea>
                </div>
                
                <div class="form-group">
                    <label class="form-label">Mensagem VIP Ativado</label>
                    <textarea name="msg_vip_ativado" class="form-input form-textarea">{html.escape(config.get('msg_vip_ativado', ''))}</textarea>
                </div>
                
                <div class="form-group">
                    <label class="form-label">Mensagem Bom Dia</label>
                    <textarea name="msg_bom_dia" class="form-input form-textarea">{html.escape(config.get('msg_bom_dia', ''))}</textarea>
                </div>
                
                <div class="form-group">
                    <label class="form-label">Mensagem Boa Noite</label>
                    <textarea name="msg_boa_noite" class="form-input form-textarea">{html.escape(config.get('msg_boa_noite', ''))}</textarea>
                </div>
            </div>
            
            <button type="submit" class="btn btn-primary" style="width: 100%;">
                💾 Salvar Configurações
            </button>
        </form>
    </div>
    """
    
    return render_page("Configurações", content, "config")

# ================= CHAT =================
@app.route("/chat/<uid>")
def chat_view(uid):
    if not session.get("authenticated"):
        return redirect("/login")
    
    messages = get_user_messages(uid)
    stats = get_user_stats(uid)
    is_fav = is_favorite(uid)
    notes = get_user_notes(uid)
    tags = get_user_tags(uid)
    is_takeover = is_takeover_active(uid)
    
    messages_html = ""
    for msg in messages:
        role = msg["role"]
        text = html.escape(msg["text"])
        time_str = msg["time"]
        
        if role == "user":
            messages_html += f'<div class="message message-user"><div class="message-label">Usuário</div>{text}<div class="message-time">{time_str}</div></div>'
        elif role == "assistant":
            messages_html += f'<div class="message message-sophia"><div class="message-label">🤖 Sophia</div>{text}<div class="message-time">{time_str}</div></div>'
        elif role == "admin":
            messages_html += f'<div class="message message-admin"><div class="message-label">👑 Admin</div>{text}<div class="message-time">{time_str}</div></div>'
        else:
            messages_html += f'<div class="message message-system">⚡ {text}</div>'
    
    if not messages_html:
        messages_html = '<div class="empty-state"><div class="icon">📭</div><p>Nenhuma mensagem</p></div>'
    
    status_text = {"online": "🟢 Online", "idle": "🟡 Ausente", "offline": "🔴 Offline"}.get(stats['status'], "")
    
    tags_html = "".join([f'<span class="badge" style="background:#667eea;color:white;">{t}</span>' for t in tags])
    
    return f"""
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
        <title>Chat - {uid[:12]}</title>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
        {STYLES}
    </head>
    <body>
        <div class="chat-container">
            <div class="chat-header-bar">
                <div class="chat-back" onclick="window.location.href='/dashboard'">
                    <i class="fas fa-arrow-left"></i>
                </div>
                <div class="chat-user-info" onclick="openModal('userModal')">
                    <div class="chat-user-name">
                        {'⭐ ' if is_fav else ''}{uid[:25]}
                    </div>
                    <div class="chat-user-status">
                        {status_text} 
                        {'• 👑 VIP até ' + stats['vip_until'] if stats['vip_until'] else ''}
                        {'• 🔒 Travado' if stats['is_locked'] else ''}
                    </div>
                </div>
                <div style="display: flex; gap: 10px;">
                    <div style="cursor:pointer; font-size: 20px; {'background:#ff6b6b;padding:5px;border-radius:8px;' if is_takeover else ''}" 
                         onclick="toggleTakeover()" title="{'Liberar Conversa' if is_takeover else 'Assumir Conversa'}">
                        {'🎮' if is_takeover else '🕹️'}
                    </div>
                    <div style="cursor:pointer; font-size: 20px;" onclick="toggleFavorite()">
                        {'⭐' if is_fav else '☆'}
                    </div>
                    <div style="cursor:pointer; font-size: 20px;" onclick="location.reload()">
                        🔄
                    </div>
                </div>
            </div>

          {'<div style="background:linear-gradient(135deg,#ff6b6b,#ee5a5a);color:white;padding:12px 20px;text-align:center;font-weight:600;">🎮 VOCÊ ESTÁ NO CONTROLE - IA pausada</div>' if is_takeover else ''}  
            <div class="chat-messages" id="chatMessages">
                {messages_html}
            </div>
            
            <div class="quick-replies">
                <div class="quick-reply" onclick="setMessage('Oi amor! 💕')">Oi amor</div>
                <div class="quick-reply" onclick="setMessage('Tudo bem? 🥰')">Tudo bem?</div>
                <div class="quick-reply" onclick="setMessage('Senti sua falta... 🥺')">Senti falta</div>
                <div class="quick-reply" onclick="setMessage('Te adoro! 💖')">Te adoro</div>
                <div class="quick-reply" onclick="setMessage('💖 Seu VIP foi ativado!')">VIP ativado</div>
            </div>
            
            <div class="photo-preview-container" id="photoPreview">
                <img id="previewImg" class="photo-preview-img">
                <span id="photoName"></span>
                <button class="photo-preview-remove" onclick="removePhoto()">✕</button>
            </div>
            
            <div class="chat-input-area">
                <div class="chat-input-row">
                    <button class="photo-upload-btn" onclick="document.getElementById('photoInput').click()">
                        📷
                    </button>
                    <input type="file" id="photoInput" accept="image/*" style="display:none" onchange="previewPhoto(event)">
                    <input type="text" class="chat-input" id="messageInput" placeholder="Digite...">
                    <button class="send-btn" onclick="sendMessage()">
                        <i class="fas fa-paper-plane"></i>
                    </button>
                </div>
            </div>
        </div>
        
        <!-- FAB -->
        <button class="fab" onclick="toggleBottomSheet()">⚡</button>
        
        <!-- Bottom Sheet -->
        <div class="bottom-sheet-overlay" id="bsOverlay" onclick="toggleBottomSheet()"></div>
        <div class="bottom-sheet" id="bottomSheet">
            <div class="bottom-sheet-handle"></div>
            <div class="bottom-sheet-title">⚡ Ações</div>
            <div class="action-grid">
                <button class="action-btn warning" onclick="executeAction('setvip')">
                    <span class="icon">👑</span><span>VIP</span>
                </button>
                <button class="action-btn success" onclick="executeAction('bonus5')">
                    <span class="icon">🎁</span><span>+5 Msgs</span>
                </button>
                <button class="action-btn success" onclick="executeAction('bonus10')">
                    <span class="icon">🎁</span><span>+10 Msgs</span>
                </button>
                <button class="action-btn" onclick="executeAction('reset')">
                    <span class="icon">🔄</span><span>Resetar</span>
                </button>
                <button class="action-btn" onclick="executeAction('clearmemory')">
                    <span class="icon">🧠</span><span>Limpar</span>
                </button>
                <button class="action-btn" onclick="executeAction('unpause')">
                    <span class="icon">▶️</span><span>Despausar</span>
                </button>
                <button class="action-btn danger" onclick="executeAction('blacklist')">
                    <span class="icon">🚫</span><span>Bloquear</span>
                </button>
                <button class="action-btn" onclick="openModal('notesModal'); toggleBottomSheet();">
                    <span class="icon">📝</span><span>Notas</span>
                </button>
                <button class="action-btn" onclick="openModal('tagsModal'); toggleBottomSheet();">
                    <span class="icon">🏷️</span><span>Tags</span>
                </button>
            </div>
        </div>
        
        <!-- User Modal -->
        <div class="modal-overlay" id="userModal" onclick="if(event.target===this)closeModal('userModal')">
            <div class="modal-content">
                <div class="modal-header">
                    <h3>👤 Detalhes</h3>
                    <span class="modal-close" onclick="closeModal('userModal')">&times;</span>
                </div>
                <div class="modal-body">
                    <p><strong>ID:</strong> {uid}</p>
                    <p><strong>Status:</strong> {status_text}</p>
                    <p><strong>Mensagens:</strong> {stats['total_messages']}</p>
                    <p><strong>Hoje:</strong> {stats['today_count']}/15</p>
                    <p><strong>VIP:</strong> {'Até ' + stats['vip_until'] if stats['vip_until'] else 'Não'}</p>
                    <p><strong>Tags:</strong> {tags_html or 'Nenhuma'}</p>
                </div>
            </div>
        </div>
        
        <!-- Notes Modal -->
        <div class="modal-overlay" id="notesModal" onclick="if(event.target===this)closeModal('notesModal')">
            <div class="modal-content">
                <div class="modal-header">
                    <h3>📝 Notas</h3>
                    <span class="modal-close" onclick="closeModal('notesModal')">&times;</span>
                </div>
                <div class="modal-body">
                    <textarea id="notesText" class="form-input form-textarea" placeholder="Adicione notas sobre este usuário...">{html.escape(notes)}</textarea>
                </div>
                <div class="modal-footer">
                    <button class="btn btn-primary" onclick="saveNotes()">Salvar</button>
                </div>
            </div>
        </div>
        
        <!-- Tags Modal -->
        <div class="modal-overlay" id="tagsModal" onclick="if(event.target===this)closeModal('tagsModal')">
            <div class="modal-content">
                <div class="modal-header">
                    <h3>🏷️ Tags</h3>
                    <span class="modal-close" onclick="closeModal('tagsModal')">&times;</span>
                </div>
                <div class="modal-body">
                    <div id="currentTags" style="margin-bottom: 15px;">
                        {tags_html or '<span style="color:#888;">Nenhuma tag</span>'}
                    </div>
                    <div style="display: flex; gap: 10px;">
                        <input type="text" id="newTag" class="form-input" placeholder="Nova tag...">
                        <button class="btn btn-primary" onclick="addTag()">Adicionar</button>
                    </div>
                </div>
            </div>
        </div>
        
        <div class="toast" id="toast"></div>
        
        <script>
            if (localStorage.getItem('theme') === 'dark') document.body.classList.add('dark');
            
            const chatMessages = document.getElementById('chatMessages');
            chatMessages.scrollTop = chatMessages.scrollHeight;
            
            function toggleBottomSheet() {{
                document.getElementById('bsOverlay').classList.toggle('active');
                document.getElementById('bottomSheet').classList.toggle('active');
            }}
            
            function setMessage(text) {{
                document.getElementById('messageInput').value = text;
                document.getElementById('messageInput').focus();
            }}
            
            let selectedPhoto = null;
            
            function previewPhoto(event) {{
                const file = event.target.files[0];
                if (file) {{
                    selectedPhoto = file;
                    const reader = new FileReader();
                    reader.onload = (e) => {{
                        document.getElementById('previewImg').src = e.target.result;
                        document.getElementById('photoName').textContent = file.name;
                        document.getElementById('photoPreview').classList.add('active');
                    }};
                    reader.readAsDataURL(file);
                }}
            }}
            
            function removePhoto() {{
                selectedPhoto = null;
                document.getElementById('photoPreview').classList.remove('active');
                document.getElementById('photoInput').value = '';
            }}
            
            async function sendMessage() {{
                const input = document.getElementById('messageInput');
                const message = input.value.trim();
                
                if (selectedPhoto) {{
                    const formData = new FormData();
                    formData.append('photo', selectedPhoto);
                    formData.append('caption', message);
                    
                    showToast('Enviando...', 'success');
                    
                    try {{
                        const resp = await fetch('/send-photo/{uid}', {{ method: 'POST', body: formData }});
                        const data = await resp.json();
                        if (data.success) {{
                            showToast('✅ Foto enviada!', 'success');
                            removePhoto();
                            input.value = '';
                            setTimeout(() => location.reload(), 1000);
                        }} else {{
                            showToast('❌ ' + data.error, 'error');
                        }}
                    }} catch(e) {{
                        showToast('❌ Erro', 'error');
                    }}
                }} else if (message) {{
                    try {{
                        const resp = await fetch('/send/{uid}', {{
                            method: 'POST',
                            headers: {{'Content-Type': 'application/x-www-form-urlencoded'}},
                            body: 'message=' + encodeURIComponent(message)
                        }});
                        const data = await resp.json();
                        if (data.success) {{
                            showToast('✅ Enviado!', 'success');
                            input.value = '';
                            setTimeout(() => location.reload(), 1000);
                        }} else {{
                            showToast('❌ ' + data.error, 'error');
                        }}
                    }} catch(e) {{
                        showToast('❌ Erro', 'error');
                    }}
                }}
            }}
            
            async function executeAction(action) {{
                if (action === 'blacklist' && !confirm('Bloquear?')) return;
                
                toggleBottomSheet();
                showToast('Executando...', 'success');
                
                try {{
                    const resp = await fetch('/action/{uid}/' + action, {{ method: 'POST' }});
                    const data = await resp.json();
                    if (data.success) {{
                        showToast('✅ ' + data.message, 'success');
                        setTimeout(() => location.reload(), 1500);
                    }} else {{
                        showToast('❌ ' + data.error, 'error');
                    }}
                }} catch(e) {{
                    showToast('❌ Erro', 'error');
                }}
            }}

            async function toggleTakeover() {{
                const resp = await fetch('/api/takeover/{uid}', {{ method: 'POST' }});
                const data = await resp.json();
                if (data.success) {{
                    showToast(data.active ? '🎮 Controle assumido! IA pausada.' : '✅ Controle liberado! IA reativada.', 'success');
                    setTimeout(() => location.reload(), 800);
                }} else {{
                    showToast('❌ Erro', 'error');
                }}
            }}
            
            async function toggleFavorite() {{
                const resp = await fetch('/api/favorite/{uid}', {{ method: 'POST' }});
                const data = await resp.json();
                showToast(data.is_favorite ? '⭐ Adicionado aos favoritos' : '☆ Removido dos favoritos', 'success');
                setTimeout(() => location.reload(), 500);
            }}
            
            async function saveNotes() {{
                const notes = document.getElementById('notesText').value;
                const resp = await fetch('/api/notes/{uid}', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{ notes }})
                }});
                if (resp.ok) {{
                    showToast('✅ Notas salvas', 'success');
                    closeModal('notesModal');
                }}
            }}
            
            async function addTag() {{
                const tag = document.getElementById('newTag').value.trim();
                if (!tag) return;
                
                const resp = await fetch('/api/tags/{uid}', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{ tag }})
                }});
                if (resp.ok) {{
                    showToast('✅ Tag adicionada', 'success');
                    setTimeout(() => location.reload(), 500);
                }}
            }}
            
            function showToast(message, type) {{
                const toast = document.getElementById('toast');
                toast.textContent = message;
                toast.className = 'toast ' + type + ' show';
                setTimeout(() => toast.classList.remove('show'), 3000);
            }}
            
            function openModal(id) {{ document.getElementById(id).classList.add('active'); }}
            function closeModal(id) {{ document.getElementById(id).classList.remove('active'); }}
            
            document.getElementById('messageInput').addEventListener('keypress', (e) => {{
                if (e.key === 'Enter') sendMessage();
            }});
            
            setTimeout(() => location.reload(), 30000);
        </script>
    </body>
    </html>
    """

# ================= APIs =================
@app.route("/send/<uid>", methods=["POST"])
def send_message_route(uid):
    if not session.get("authenticated"):
        return jsonify({"success": False, "error": "Não autorizado"}), 401
    
    message = request.form.get("message", "").strip()
    if not message:
        return jsonify({"success": False, "error": "Mensagem vazia"}), 400
    
    success, error = send_telegram_message(uid, message)
    if success:
        save_admin_message(uid, message)
        log_admin_action("MESSAGE_SENT", message[:50], uid)
        return jsonify({"success": True})
    return jsonify({"success": False, "error": error}), 500

@app.route("/send-photo/<uid>", methods=["POST"])
def send_photo_route(uid):
    if not session.get("authenticated"):
        return jsonify({"success": False, "error": "Não autorizado"}), 401
    
    if 'photo' not in request.files:
        return jsonify({"success": False, "error": "Nenhuma foto"}), 400
    
    photo = request.files['photo']
    caption = request.form.get("caption", "").strip()
    
    success, error = send_telegram_photo(uid, photo.read(), caption)
    if success:
        save_admin_message(uid, f"[📷 FOTO]{' - ' + caption if caption else ''}")
        log_admin_action("PHOTO_SENT", caption[:30] if caption else "Sem legenda", uid)
        return jsonify({"success": True})
    return jsonify({"success": False, "error": error}), 500

@app.route("/action/<uid>/<action>", methods=["POST"])
def action_route(uid, action):
    if not session.get("authenticated"):
        return jsonify({"success": False, "error": "Não autorizado"}), 401
    
    actions = {
        "setvip": lambda: activate_vip(uid),
        "bonus5": lambda: give_bonus_messages(uid, 5),
        "bonus10": lambda: give_bonus_messages(uid, 10),
        "reset": lambda: reset_daily_limit(uid),
        "clearmemory": lambda: clear_user_memory(uid),
        "unpause": lambda: unpause_user(uid),
        "blacklist": lambda: blacklist_user(uid),
        "unblacklist": lambda: unblacklist_user(uid),
    }
    
    if action not in actions:
        return jsonify({"success": False, "error": "Ação inválida"}), 400
    
    success, message = actions[action]()
    if success:
        save_admin_message(uid, f"[⚡ {action.upper()}]")
        
        if action == "setvip":
            send_telegram_message(uid, "💖 Seu VIP foi ativado! Agora a gente pode conversar sem limite 😘")
        elif action in ["bonus5", "bonus10"]:
            amt = 5 if action == "bonus5" else 10
            send_telegram_message(uid, f"🎁 Você ganhou +{amt} mensagens extras! Aproveita 💕")
        
        return jsonify({"success": True, "message": message})
    return jsonify({"success": False, "error": message}), 500

@app.route("/api/favorite/<uid>", methods=["POST"])
def favorite_route(uid):
    if not session.get("authenticated"):
        return jsonify({"success": False}), 401
    
    is_fav = toggle_favorite(uid)
    return jsonify({"success": True, "is_favorite": is_fav})

@app.route("/api/notes/<uid>", methods=["POST"])
def notes_route(uid):
    if not session.get("authenticated"):
        return jsonify({"success": False}), 401
    
    data = request.get_json()
    save_user_notes(uid, data.get("notes", ""))
    return jsonify({"success": True})

@app.route("/api/tags/<uid>", methods=["POST"])
def tags_route(uid):
    if not session.get("authenticated"):
        return jsonify({"success": False}), 401
    
    data = request.get_json()
    add_user_tag(uid, data.get("tag", ""))
    return jsonify({"success": True})

@app.route("/api/pix/aprovar/<uid>", methods=["POST"])
def aprovar_pix(uid):
    if not session.get("authenticated"):
        return jsonify({"success": False}), 401
    
    success, msg = activate_vip(uid)
    if success:
        remove_pix_pending(uid)
        send_telegram_message(uid, "💖 Pagamento confirmado! VIP ativo por 15 dias 😘")
    return jsonify({"success": success, "message": msg})

@app.route("/api/pix/rejeitar/<uid>", methods=["POST"])
def rejeitar_pix(uid):
    if not session.get("authenticated"):
        return jsonify({"success": False}), 401
    
    remove_pix_pending(uid)
    log_admin_action("PIX_REJECTED", "", uid)
    return jsonify({"success": True})

@app.route("/api/galeria/delete/<photo_id>", methods=["POST"])
def delete_gallery_photo(photo_id):
    if not session.get("authenticated"):
        return jsonify({"success": False}), 401
    
    remove_from_gallery(photo_id)
    return jsonify({"success": True})

@app.route("/api/alert/read/<alert_id>", methods=["POST"])
def read_alert(alert_id):
    if not session.get("authenticated"):
        return jsonify({"success": False}), 401
    
    mark_alert_read(alert_id)
    return jsonify({"success": True})

@app.route("/api/alert/read-all", methods=["POST"])
def read_all_alerts():
    if not session.get("authenticated"):
        return jsonify({"success": False}), 401
    
    mark_all_alerts_read()
    return jsonify({"success": True})

@app.route("/api/takeover/<uid>", methods=["POST"])
def takeover_route(uid):
    if not session.get("authenticated"):
        return jsonify({"success": False}), 401
    
    if is_takeover_active(uid):
        end_takeover(uid)
        return jsonify({"success": True, "active": False})
    else:
        start_takeover(uid)
        return jsonify({"success": True, "active": True})

@app.route("/health")
def health():
    return jsonify({"status": "ok", "redis": check_redis(), "version": "5.0"})

# ================= EXPORTAR CONVERSAS =================
@app.route("/exportar-conversas")
def exportar_conversas():
    if not session.get("authenticated"):
        return redirect("/login")
    
    all_users = get_all_users()
    export_data = []
    
    for uid in all_users:
        stats = get_user_stats(uid)
        messages = get_user_messages(uid)
        
        user_msgs = [m for m in messages if m['role'] == 'user']
        sophia_msgs = [m for m in messages if m['role'] == 'assistant']
        
        user_data = {
            "uid": uid,
            "is_vip": stats['is_vip'],
            "total_msgs": len(messages),
            "user_msgs": len(user_msgs),
            "sophia_msgs": len(sophia_msgs),
            "status": stats['status'],
            "is_locked": stats['is_locked'],
            "conversa": []
        }
        
        for msg in messages:
            user_data["conversa"].append({
                "role": msg['role'],
                "text": msg['text'],
                "time": msg['time']
            })
        
        export_data.append(user_data)
    
    export_data.sort(key=lambda x: x['total_msgs'], reverse=True)
    
    response = app.response_class(
        response=json.dumps(export_data, ensure_ascii=False, indent=2),
        status=200,
        mimetype='application/json'
    )
    response.headers["Content-Disposition"] = "attachment; filename=conversas_sophia.json"
    return response


@app.route("/exportar-txt")
def exportar_txt():
    if not session.get("authenticated"):
        return redirect("/login")
    
    all_users = get_all_users()
    output = []
    
    output.append("=" * 60)
    output.append("RELATORIO DE CONVERSAS - SOPHIA BOT")
    output.append(f"Data: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    output.append(f"Total de usuarios: {len(all_users)}")
    output.append("=" * 60)
    output.append("")
    
    for uid in all_users:
        stats = get_user_stats(uid)
        messages = get_user_messages(uid)
        
        if not messages:
            continue
        
        user_msgs = len([m for m in messages if m['role'] == 'user'])
        
        output.append("-" * 60)
        output.append(f"USUARIO: {uid}")
        output.append(f"VIP: {'Sim' if stats['is_vip'] else 'Nao'}")
        output.append(f"Msgs do usuario: {user_msgs}")
        output.append(f"Total msgs: {len(messages)}")
        output.append(f"Travado: {'Sim' if stats['is_locked'] else 'Nao'}")
        output.append("-" * 60)
        output.append("")
        
        for msg in messages:
            role_label = {
                'user': 'USER',
                'assistant': 'SOPHIA', 
                'admin': 'ADMIN',
                'system': 'SISTEMA',
                'action': 'ACAO',
                'info': 'INFO'
            }.get(msg['role'], msg['role'].upper())
            
            output.append(f"[{msg['time']}] {role_label}:")
            output.append(f"   {msg['text']}")
            output.append("")
        
        output.append("")
    
    vips = sum(1 for uid in all_users if get_user_stats(uid)['is_vip'])
    output.append("=" * 60)
    output.append("RESUMO")
    output.append(f"Total usuarios: {len(all_users)}")
    output.append(f"VIPs: {vips}")
    output.append(f"Conversao: {(vips/len(all_users)*100) if all_users else 0:.1f}%")
    output.append("=" * 60)
    
    response = app.response_class(
        response="\n".join(output),
        status=200,
        mimetype='text/plain; charset=utf-8'
    )
    response.headers["Content-Disposition"] = "attachment; filename=conversas_sophia.txt"
    return response


if __name__ == "__main__":
    logger.info(f"🚀 Sophia Admin v5.0 FULL - Porta {PORT}")
    app.run(host="0.0.0.0", port=PORT, debug=False)
