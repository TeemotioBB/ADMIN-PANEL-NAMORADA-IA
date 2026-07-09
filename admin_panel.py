#!/usr/bin/env python3
"""
Sophia Admin Panel v6 - Refactor UI/UX
"""

import os
import json
import redis
import urllib.request
import urllib.parse
import urllib.error
import base64
from datetime import datetime, timedelta, date
from flask import Flask, request, redirect, session, jsonify, send_file, Response, make_response
from io import BytesIO
import logging
import time
import html
import hashlib
from functools import wraps

# ========================= CONFIG =========================

REDIS_URL = os.environ.get("REDIS_URL", "redis://default:DcddfJOHLXZdFPjEhRjHeodNgdtrsevl@shuttle.proxy.rlwy.net:12241")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8528168785:AAFfgtaB0vEagd1cdfZ3hWDyL9PKFZrmRjk")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")
SECRET_KEY = os.environ.get("SECRET_KEY", "sophia-secret-" + str(int(time.time())))
PORT = int(os.environ.get("PORT", 8081))

ONLINE_THRESHOLD = 20
IDLE_THRESHOLD = 40
OFFLINE_THRESHOLD = 60

CACHE_TTL = 30
_cache = {}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

redis_client = None
try:
    redis_client = redis.from_url(REDIS_URL, decode_responses=True, socket_connect_timeout=3, socket_timeout=3)
    redis_client.ping()
    logger.info("Redis conectado")
except Exception as e:
    logger.error(f"Redis erro: {e}")

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=8)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# ========================= CACHE =========================

def cache_key(func_name, *args):
    return f"{func_name}:{':'.join(map(str, args))}"

def get_cache(key):
    if key in _cache:
        value, ts = _cache[key]
        if time.time() - ts < CACHE_TTL:
            return value
        del _cache[key]
    return None

def set_cache(key, value):
    _cache[key] = (value, time.time())
    if len(_cache) > 1000:
        _cache.clear()

def cached(ttl=CACHE_TTL):
    def deco(f):
        @wraps(f)
        def wrap(*a, **k):
            key = cache_key(f.__name__, *a)
            r = get_cache(key)
            if r is not None:
                return r
            r = f(*a, **k)
            set_cache(key, r)
            return r
        return wrap
    return deco

def clear_cache():
    _cache.clear()

# ========================= REDIS KEYS =========================

def admin_log_key():       return "admin:logs"
def admin_config_key():    return "admin:config"
def admin_gallery_key():   return "admin:gallery"
def admin_favorites_key(): return "admin:favorites"
def admin_notes_key(u):    return f"admin:notes:{u}"
def admin_tags_key(u):     return f"admin:tags:{u}"
def admin_alerts_key():    return "admin:alerts"
def daily_stats_key(d):    return f"stats:daily:{d}"
def pix_pending_list_key():return "admin:pix_pending"
def broadcast_history_key():return "admin:broadcast_history"
def admin_takeover_key(u): return f"admin:takeover:{u}"
def broadcast_locked_sent_key(u): return f"broadcast:locked_sent:{u}"

# ========================= TELEGRAM =========================

def send_telegram_message(chat_id, text, parse_mode="Markdown"):
    if not TELEGRAM_TOKEN: return False, "Token não configurado"
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        data = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": parse_mode}).encode('utf-8')
        req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'}, method='POST')
        with urllib.request.urlopen(req, timeout=5) as r:
            res = json.loads(r.read().decode('utf-8'))
        return (True, "Enviado") if res.get("ok") else (False, res.get("description", "Erro"))
    except Exception as e:
        return False, str(e)

def send_telegram_photo(chat_id, photo_data, caption=""):
    if not TELEGRAM_TOKEN: return False, "Token não configurado"
    import uuid
    boundary = str(uuid.uuid4())
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    try:
        body = b''
        body += f'--{boundary}\r\n'.encode() + b'Content-Disposition: form-data; name="chat_id"\r\n\r\n' + f'{chat_id}\r\n'.encode()
        if caption:
            body += f'--{boundary}\r\n'.encode() + b'Content-Disposition: form-data; name="caption"\r\n\r\n' + f'{caption}\r\n'.encode()
        body += f'--{boundary}\r\n'.encode() + b'Content-Disposition: form-data; name="photo"; filename="photo.jpg"\r\nContent-Type: image/jpeg\r\n\r\n' + photo_data + b'\r\n'
        body += f'--{boundary}--\r\n'.encode()
        req = urllib.request.Request(url, data=body, headers={'Content-Type': f'multipart/form-data; boundary={boundary}'}, method='POST')
        with urllib.request.urlopen(req, timeout=15) as r:
            res = json.loads(r.read().decode('utf-8'))
        return (True, "Foto enviada") if res.get("ok") else (False, res.get("description", "Erro"))
    except Exception as e:
        return False, str(e)

def send_telegram_photo_by_file_id(chat_id, file_id, caption=""):
    if not TELEGRAM_TOKEN: return False, "Token não configurado"
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    try:
        payload = {"chat_id": chat_id, "photo": file_id}
        if caption: payload["caption"] = caption
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'}, method='POST')
        with urllib.request.urlopen(req, timeout=5) as r:
            res = json.loads(r.read().decode('utf-8'))
        return (True, "Foto enviada") if res.get("ok") else (False, res.get("description", "Erro"))
    except Exception as e:
        return False, str(e)

def _pix_keyboard():
    config = get_config()
    payment_url = config.get("pix_payment_url", "")
    if payment_url:
        return {"inline_keyboard": [[{"text": "💳 PAGAR COM PIX (R$ 9,99)", "url": payment_url}]]}
    return {"inline_keyboard": [[{"text": "💳 PAGAR COM PIX (R$ 9,99)", "callback_data": "pay_pix"}]]}

def send_telegram_message_with_button(chat_id, text):
    if not TELEGRAM_TOKEN: return False, "Token não configurado"
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        data = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "Markdown", "reply_markup": _pix_keyboard()}).encode('utf-8')
        req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'}, method='POST')
        with urllib.request.urlopen(req, timeout=5) as r:
            res = json.loads(r.read().decode('utf-8'))
        return (True, "Enviado") if res.get("ok") else (False, res.get("description", "Erro"))
    except Exception as e:
        return False, str(e)

def send_telegram_photo_with_button(chat_id, photo_data, caption=""):
    if not TELEGRAM_TOKEN: return False, "Token não configurado"
    import uuid
    boundary = str(uuid.uuid4())
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    try:
        keyboard = _pix_keyboard()
        body = b''
        body += f'--{boundary}\r\n'.encode() + b'Content-Disposition: form-data; name="chat_id"\r\n\r\n' + f'{chat_id}\r\n'.encode()
        if caption:
            body += f'--{boundary}\r\n'.encode() + b'Content-Disposition: form-data; name="caption"\r\n\r\n' + f'{caption}\r\n'.encode()
        body += f'--{boundary}\r\n'.encode() + b'Content-Disposition: form-data; name="parse_mode"\r\n\r\nMarkdown\r\n'
        body += f'--{boundary}\r\n'.encode() + b'Content-Disposition: form-data; name="reply_markup"\r\n\r\n' + json.dumps(keyboard).encode('utf-8') + b'\r\n'
        body += f'--{boundary}\r\n'.encode() + b'Content-Disposition: form-data; name="photo"; filename="photo.jpg"\r\nContent-Type: image/jpeg\r\n\r\n' + photo_data + b'\r\n'
        body += f'--{boundary}--\r\n'.encode()
        req = urllib.request.Request(url, data=body, headers={'Content-Type': f'multipart/form-data; boundary={boundary}'}, method='POST')
        with urllib.request.urlopen(req, timeout=15) as r:
            res = json.loads(r.read().decode('utf-8'))
        return (True, "Foto enviada") if res.get("ok") else (False, res.get("description", "Erro"))
    except Exception as e:
        return False, str(e)

# ========================= ADMIN LOG =========================

def log_admin_action(action, details="", uid=None):
    try:
        entry = {"timestamp": datetime.now().isoformat(), "action": action, "details": details, "uid": uid}
        redis_client.lpush(admin_log_key(), json.dumps(entry))
        redis_client.ltrim(admin_log_key(), 0, 499)
    except: pass

@cached(60)
def get_admin_logs(limit=50):
    try:
        logs = redis_client.lrange(admin_log_key(), 0, limit - 1)
        return [json.loads(l) for l in logs]
    except: return []

# ========================= CONFIG =========================

DEFAULT_CONFIG = {
    "limite_diario": 15, "dias_vip": 15, "preco_vip_stars": 250,
    "preco_pix": "14.99", "preco_pix_desconto": "9.99",
    "pix_key": "mayaoficialbr@outlook.com",
    "pix_payment_url": "https://app.pushinpay.com.br/service/pay/A0D7D476-E44F-42EB-AECA-1EF20EE5C01E",
    "msg_limite": "💔 Seu limite diário acabou.\nVolte amanhã ou vire VIP 💖",
    "msg_vip_ativado": "💖 Pagamento aprovado!\nVIP ativo por {dias} dias 😘",
}

@cached(60)
def get_config():
    try:
        c = redis_client.get(admin_config_key())
        if c: return {**DEFAULT_CONFIG, **json.loads(c)}
        return DEFAULT_CONFIG.copy()
    except: return DEFAULT_CONFIG.copy()

def save_config(config):
    try:
        redis_client.set(admin_config_key(), json.dumps(config))
        clear_cache()
        log_admin_action("CONFIG_UPDATED", "Configurações atualizadas")
        return True
    except: return False

# ========================= GALLERY =========================

@cached(30)
def get_gallery():
    try:
        photos = redis_client.lrange(admin_gallery_key(), 0, -1)
        return [json.loads(p) for p in photos]
    except: return []

def add_to_gallery(name, data_b64, thumbnail_b64=None):
    try:
        photo = {
            "id": hashlib.md5(f"{name}{time.time()}".encode()).hexdigest()[:12],
            "name": name, "data": data_b64,
            "thumbnail": thumbnail_b64 or data_b64,
            "created_at": datetime.now().isoformat()
        }
        redis_client.lpush(admin_gallery_key(), json.dumps(photo))
        clear_cache()
        log_admin_action("GALLERY_ADD", f"Foto: {name}")
        return True, photo["id"]
    except Exception as e:
        return False, str(e)

def remove_from_gallery(photo_id):
    try:
        photos = get_gallery()
        for p in photos:
            if p["id"] == photo_id:
                redis_client.lrem(admin_gallery_key(), 1, json.dumps(p))
                clear_cache()
                log_admin_action("GALLERY_REMOVE", f"Foto: {p['name']}")
                return True
        return False
    except: return False

# ========================= FAVORITES =========================

@cached(30)
def get_favorites():
    try: return list(redis_client.smembers(admin_favorites_key()))
    except: return []

def toggle_favorite(uid):
    try:
        if redis_client.sismember(admin_favorites_key(), uid):
            redis_client.srem(admin_favorites_key(), uid)
            clear_cache()
            log_admin_action("FAVORITE_REMOVE", uid, uid)
            return False
        redis_client.sadd(admin_favorites_key(), uid)
        clear_cache()
        log_admin_action("FAVORITE_ADD", uid, uid)
        return True
    except: return False

def is_favorite(uid):
    return uid in get_favorites()

# ========================= NOTES & TAGS =========================

@cached(30)
def get_user_notes(uid):
    try: return redis_client.get(admin_notes_key(uid)) or ""
    except: return ""

def save_user_notes(uid, notes):
    try:
        if notes.strip(): redis_client.set(admin_notes_key(uid), notes)
        else: redis_client.delete(admin_notes_key(uid))
        clear_cache()
        log_admin_action("NOTES_UPDATE", "Notas atualizadas", uid)
        return True
    except: return False

@cached(30)
def get_user_tags(uid):
    try: return list(redis_client.smembers(admin_tags_key(uid)))
    except: return []

def add_user_tag(uid, tag):
    try:
        redis_client.sadd(admin_tags_key(uid), tag)
        clear_cache()
        log_admin_action("TAG_ADD", f"Tag: {tag}", uid)
        return True
    except: return False

def remove_user_tag(uid, tag):
    try:
        redis_client.srem(admin_tags_key(uid), tag)
        clear_cache()
        log_admin_action("TAG_REMOVE", f"Tag: {tag}", uid)
        return True
    except: return False

# ========================= ALERTS =========================

def add_alert(alert_type, message, uid=None, priority="normal"):
    try:
        alert = {
            "id": hashlib.md5(f"{message}{time.time()}".encode()).hexdigest()[:10],
            "type": alert_type, "message": message, "uid": uid,
            "priority": priority, "created_at": datetime.now().isoformat(), "read": False
        }
        redis_client.lpush(admin_alerts_key(), json.dumps(alert))
        redis_client.ltrim(admin_alerts_key(), 0, 49)
        clear_cache()
        return True
    except: return False

@cached(15)
def get_alerts(unread_only=False):
    try:
        alerts = redis_client.lrange(admin_alerts_key(), 0, -1)
        result = [json.loads(a) for a in alerts]
        if unread_only: result = [a for a in result if not a.get("read")]
        return result
    except: return []

def mark_alert_read(alert_id):
    try:
        alerts = redis_client.lrange(admin_alerts_key(), 0, -1)
        for i, aj in enumerate(alerts):
            a = json.loads(aj)
            if a["id"] == alert_id:
                a["read"] = True
                redis_client.lset(admin_alerts_key(), i, json.dumps(a))
                clear_cache()
                return True
        return False
    except: return False

def mark_all_alerts_read():
    try:
        alerts = redis_client.lrange(admin_alerts_key(), 0, -1)
        redis_client.delete(admin_alerts_key())
        for aj in alerts:
            a = json.loads(aj)
            a["read"] = True
            redis_client.rpush(admin_alerts_key(), json.dumps(a))
        clear_cache()
        return True
    except: return False

def get_unread_count():
    return len(get_alerts(unread_only=True))

# ========================= PIX =========================

def add_pix_pending(uid, username, amount, has_discount=False):
    try:
        entry = {"uid": uid, "username": username, "amount": amount,
                 "has_discount": has_discount, "created_at": datetime.now().isoformat()}
        redis_client.hset(pix_pending_list_key(), uid, json.dumps(entry))
        add_alert("pix", f"💳 Novo comprovante PIX de {username or uid}", uid, "high")
        clear_cache()
        return True
    except: return False

@cached(15)
def get_pix_pending():
    try:
        pending = redis_client.hgetall(pix_pending_list_key())
        return [json.loads(v) for v in pending.values()]
    except: return []

def remove_pix_pending(uid):
    try:
        redis_client.hdel(pix_pending_list_key(), uid)
        clear_cache()
        return True
    except: return False

# ========================= STATS =========================

def record_daily_stat(stat_type, increment=1):
    try:
        today = date.today().isoformat()
        key = daily_stats_key(today)
        redis_client.hincrby(key, stat_type, increment)
        redis_client.expire(key, 86400 * 90)
    except: pass

@cached(30)
def get_daily_stats(d):
    try:
        stats = redis_client.hgetall(daily_stats_key(d))
        return {k: int(v) for k, v in stats.items()}
    except: return {}

@cached(60)
def get_stats_range(days=7):
    result = []
    for i in range(days):
        d = (date.today() - timedelta(days=i)).isoformat()
        stats = get_daily_stats(d)
        stats["date"] = d
        result.append(stats)
    return list(reversed(result))

# ========================= BROADCAST =========================

def save_broadcast_history(message, filters, sent_count, failed_count):
    try:
        entry = {"message": message[:200], "filters": filters,
                 "sent": sent_count, "failed": failed_count,
                 "created_at": datetime.now().isoformat()}
        redis_client.lpush(broadcast_history_key(), json.dumps(entry))
        redis_client.ltrim(broadcast_history_key(), 0, 29)
        clear_cache()
        return True
    except: return False

@cached(30)
def get_broadcast_history():
    try:
        history = redis_client.lrange(broadcast_history_key(), 0, -1)
        return [json.loads(h) for h in history]
    except: return []

def get_message_hash(message):
    return hashlib.md5(message.encode()).hexdigest()[:12]

def mark_broadcast_sent_to_locked(uid, message_hash):
    try:
        redis_client.set(broadcast_locked_sent_key(uid), message_hash, ex=86400*30)
        return True
    except: return False

def has_received_broadcast_while_locked(uid, message_hash):
    try:
        return redis_client.get(broadcast_locked_sent_key(uid)) == message_hash
    except: return False

def clear_broadcast_lock_memory(uid):
    try:
        redis_client.delete(broadcast_locked_sent_key(uid))
        return True
    except: return False

# ========================= TAKEOVER =========================

def start_takeover(uid):
    try:
        cp = redis_client.get(f"paused:{uid}")
        ci = redis_client.get(f"ignored:{uid}")
        redis_client.hset(admin_takeover_key(uid), mapping={
            "active": "1", "started_at": datetime.now().isoformat(),
            "prev_paused": cp or "", "prev_ignored": ci or ""
        })
        redis_client.set(f"paused:{uid}", "admin_takeover")
        log_admin_action("TAKEOVER_START", "Admin assumiu controle", uid)
        return True
    except: return False

def end_takeover(uid):
    try:
        d = redis_client.hgetall(admin_takeover_key(uid))
        pp = d.get("prev_paused", "")
        pi = d.get("prev_ignored", "")
        if pp: redis_client.set(f"paused:{uid}", pp)
        else: redis_client.delete(f"paused:{uid}")
        if pi: redis_client.set(f"ignored:{uid}", pi)
        else: redis_client.delete(f"ignored:{uid}")
        redis_client.delete(admin_takeover_key(uid))
        log_admin_action("TAKEOVER_END", "Admin liberou controle", uid)
        return True
    except: return False

def is_takeover_active(uid):
    try: return redis_client.hget(admin_takeover_key(uid), "active") == "1"
    except: return False

# ========================= ADMIN ACTIONS =========================

def save_admin_message(uid, text):
    try:
        ts = datetime.now().strftime("%H:%M:%S")
        redis_client.rpush(f"chatlog:{uid}", f"[{ts}] ADMIN: {text[:100]}")
        redis_client.ltrim(f"chatlog:{uid}", -200, -1)
        return True
    except: return False

def activate_vip(uid, days=15):
    try:
        vip_until = datetime.now() + timedelta(days=days)
        redis_client.set(f"vip:{uid}", vip_until.isoformat())
        for k in ["pix_pending", "pix_clicked", "pix_interest", "flash_discount"]:
            redis_client.delete(f"{k}:{uid}")
        remove_pix_pending(uid)
        clear_broadcast_lock_memory(uid)
        redis_client.delete(f"cart_abandoned:{uid}")
        redis_client.delete(f"cart_followup:{uid}")
        clear_cache()
        record_daily_stat("vips_activated")
        log_admin_action("VIP_ACTIVATED", f"{days} dias", uid)
        vip_message = (
            "💖 **PAGAMENTO CONFIRMADO!** 💖\n\nAmor, agora você é meu VIP! 👑\n\n"
            "Olha o que você desbloqueou:\n✅ Conversas ilimitadas comigo\n"
            "✅ Fotos exclusivas (olha aí embaixo 👇)\n✅ Respostas mais ousadas e sem censura\n"
            "✅ Prioridade nas minhas respostas\n\n⚠️ **Importante:** Eu sou sua companhia virtual, tá amor? "
            "A gente conversa, troca fotos, mas não rola encontro pessoal nem videochamada. "
            "Mas pode ter certeza que vou te dar MUITA atenção aqui 😘\n\n"
            "Agora me conta… o que você quer fazer comigo? 🔥"
        )
        send_telegram_message(uid, vip_message)
        FOTOS = [
            "AgACAgEAAxkBAAEDCGRpYDdvZ7-wu_S21Byz1fzVYgPx4QACGQxrGxhjAAFH3vklPrzMxqIBAAMCAAN5AAM4BA",
            "AgACAgEAAxkBAAEDCGZpYDd73debHgEmczIBknJpT0icWwACGgxrGxhjAAFHtUw2zQfnPvMBAAMCAAN5AAM4BA",
            "AgACAgEAAxkBAAEDCGhpYDeLOftxX9egLqPZTkFZnx_vwAACGwxrGxhjAAFH_O602Y3tZCsBAAMCAAN5AAM4BA",
        ]
        time.sleep(1)
        for i, fid in enumerate(FOTOS):
            try:
                cap = "Essa é só pra você, amor… 😘" if i == 0 else None
                send_telegram_photo_by_file_id(uid, fid, cap)
                time.sleep(0.8)
            except Exception as e:
                logger.error(f"Erro foto VIP {i}: {e}")
        return True, f"VIP até {vip_until.strftime('%d/%m/%Y')}"
    except Exception as e:
        return False, str(e)

def reset_daily_limit(uid):
    try:
        redis_client.delete(f"count:{uid}:{date.today()}")
        clear_broadcast_lock_memory(uid)
        clear_cache()
        log_admin_action("LIMIT_RESET", "", uid)
        return True, "Limite resetado"
    except Exception as e: return False, str(e)

def give_bonus_messages(uid, amount=5):
    try:
        cur = int(redis_client.get(f"bonus:{uid}") or 0)
        redis_client.set(f"bonus:{uid}", cur + amount)
        redis_client.expire(f"bonus:{uid}", 86400 * 7)
        clear_cache()
        log_admin_action("BONUS_GIVEN", f"+{amount}", uid)
        return True, f"+{amount} msgs (total: {cur + amount})"
    except Exception as e: return False, str(e)

def clear_user_memory(uid):
    try:
        redis_client.delete(f"memory:{uid}")
        clear_cache()
        log_admin_action("MEMORY_CLEARED", "", uid)
        return True, "Memória limpa"
    except Exception as e: return False, str(e)

def unpause_user(uid):
    try:
        redis_client.delete(f"paused:{uid}")
        redis_client.delete(f"ignored:{uid}")
        clear_cache()
        log_admin_action("USER_UNPAUSED", "", uid)
        return True, "Gatilhos reativados"
    except Exception as e: return False, str(e)

def blacklist_user(uid):
    try:
        redis_client.sadd("blacklist", str(uid))
        clear_cache()
        log_admin_action("USER_BLACKLISTED", "", uid)
        return True, "Usuário bloqueado"
    except Exception as e: return False, str(e)

def unblacklist_user(uid):
    try:
        redis_client.srem("blacklist", str(uid))
        clear_cache()
        log_admin_action("USER_UNBLACKLISTED", "", uid)
        return True, "Usuário desbloqueado"
    except Exception as e: return False, str(e)

# ========================= UTILITIES =========================

def check_redis():
    if not redis_client: return False
    try: redis_client.ping(); return True
    except: return False

@cached(30)
def get_all_users():
    if not check_redis(): return []
    try: return list(redis_client.smembers("all_users"))
    except: return []

@cached(10)
def get_user_messages(uid):
    if not check_redis(): return []
    messages = []
    seen = set()
    try:
        logs = redis_client.lrange(f"chatlog:{uid}", -100, -1)
        for log in logs:
            msg = parse_chat_message(log)
            if msg:
                k = f"{msg['role']}:{msg['time']}:{msg['text'][:20]}"
                if k not in seen:
                    seen.add(k)
                    messages.append(msg)
    except: pass
    return messages

def parse_chat_message(log_line):
    try:
        if log_line.startswith('['):
            end = log_line.find(']')
            if end > 0:
                ts = log_line[1:end]
                rem = log_line[end+2:]
                cp = rem.find(':')
                if cp > 0:
                    role = rem[:cp].strip().lower()
                    text = rem[cp+1:].strip()
                    rm = {"user":"user","sophia":"assistant","admin":"admin","system":"system",
                          "action":"action","info":"info","error":"error","blocked":"blocked"}
                    return {"role": rm.get(role, "system"), "text": text, "time": ts}
    except: pass
    return None

@cached(15)
def get_user_stats(uid):
    s = {"total_messages": 0, "user_messages": 0, "sophia_messages": 0,
         "last_activity": None, "last_message_preview": None,
         "status": "offline", "is_vip": False, "is_locked": False,
         "vip_until": None, "today_count": 0}
    try:
        vu = redis_client.get(f"vip:{uid}")
        if vu:
            dt = datetime.fromisoformat(vu)
            s["is_vip"] = dt > datetime.now()
            s["vip_until"] = dt.strftime("%d/%m/%Y") if s["is_vip"] else None
    except: pass
    try:
        c = int(redis_client.get(f"count:{uid}:{date.today()}") or 0)
        s["today_count"] = c
        s["is_locked"] = c >= 15 and not s["is_vip"]
    except: pass
    msgs = get_user_messages(uid)
    s["total_messages"] = len(msgs)
    last_um = None
    for m in msgs:
        if m["role"] == "user":
            s["user_messages"] += 1
            last_um = m["text"]
        elif m["role"] == "assistant":
            s["sophia_messages"] += 1
    if last_um:
        s["last_message_preview"] = last_um[:60] + "…" if len(last_um) > 60 else last_um
    try:
        la = redis_client.get(f"last_activity:{uid}")
        if la: s["last_activity"] = datetime.fromisoformat(la)
    except: pass
    if s["last_activity"]:
        d = (datetime.now() - s["last_activity"]).total_seconds() / 60
        if d < ONLINE_THRESHOLD: s["status"] = "online"
        elif d < IDLE_THRESHOLD: s["status"] = "idle"
        else: s["status"] = "offline"
    return s

@cached(20)
def get_global_stats():
    users = get_all_users()
    total = len(users)
    vips = online = idle = locked = 0
    if not users:
        return {"total": 0, "vips": 0, "online": 0, "idle": 0, "locked": 0}
    pipe = redis_client.pipeline()
    for u in users:
        pipe.get(f"vip:{u}")
        pipe.get(f"count:{u}:{date.today()}")
        pipe.get(f"last_activity:{u}")
    try:
        results = pipe.execute()
        for i in range(0, len(results), 3):
            vd, cd, ad = results[i], results[i+1], results[i+2]
            is_vip_now = False
            if vd:
                try:
                    dt = datetime.fromisoformat(vd)
                    if dt > datetime.now():
                        vips += 1
                        is_vip_now = True
                except: pass
            try:
                c = int(cd or 0)
                if c >= 15 and not is_vip_now: locked += 1
            except: pass
            if ad:
                try:
                    la = datetime.fromisoformat(ad)
                    d = (datetime.now() - la).total_seconds() / 60
                    if d < ONLINE_THRESHOLD: online += 1
                    elif d < IDLE_THRESHOLD: idle += 1
                except: pass
    except: pass
    return {"total": total, "vips": vips, "online": online, "idle": idle, "locked": locked}

def format_time_ago(dt):
    if not dt: return "—"
    d = (datetime.now() - dt).total_seconds()
    if d < 60: return "agora"
    if d < 3600: return f"{int(d/60)}min"
    if d < 86400: return f"{int(d/3600)}h"
    return f"{int(d/86400)}d"

def auth_required():
    return session.get("authenticated")

# ========================= ICONS (SVG inline) =========================

ICONS = {
    "home":      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>',
    "chart":     '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3v18h18"/><path d="M7 14l4-4 4 4 5-7"/></svg>',
    "megaphone": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 11l18-8v18l-18-8z"/><path d="M11 11v6"/></svg>',
    "money":     '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="6" width="20" height="12" rx="2"/><circle cx="12" cy="12" r="2.5"/></svg>',
    "image":     '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="9" cy="9" r="2"/><path d="M21 15l-5-5L5 21"/></svg>',
    "star":      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>',
    "bell":      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/></svg>',
    "log":       '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="9" y1="13" x2="15" y2="13"/><line x1="9" y1="17" x2="15" y2="17"/></svg>',
    "download":  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>',
    "settings":  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>',
    "search":    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>',
    "menu":      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>',
    "x":         '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>',
    "check":     '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>',
    "refresh":   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 0 1 15.5-6.3L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-15.5 6.3L3 16"/><path d="M3 21v-5h5"/></svg>',
    "send":      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>',
    "camera":    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/></svg>',
    "arrow_left":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/></svg>',
    "moon":      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>',
    "sun":       '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>',
    "logout":    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>',
    "trash":     '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>',
    "bolt":      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>',
    "play":      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg>',
    "pause":     '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>',
    "filter":    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/></svg>',
    "edit":      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.12 2.12 0 0 1 3 3L12 15l-4 1 1-4z"/></svg>',
}

def icon(name, size=16, cls=""):
    svg = ICONS.get(name, "")
    return f'<span class="icon {cls}" style="width:{size}px;height:{size}px" aria-hidden="true">{svg}</span>'

# ========================= CSS (servido com cache HTTP) =========================

ADMIN_CSS = r"""
/* Design tokens */
:root{
  --bg:#0a0a0a; --bg-elev:#111; --surface:#161616; --surface-2:#1c1c1c;
  --border:#262626; --border-strong:#2e2e2e;
  --text:#fafafa; --text-2:#a3a3a3; --text-3:#666; --text-4:#404040;
  --accent:#ff5a1f; --accent-soft:rgba(255,90,31,.12);
  --success:#16a34a; --warn:#f59e0b; --danger:#ef4444; --info:#3b82f6;
  --radius:10px; --radius-sm:6px; --radius-lg:14px;
  --gap:14px; --pad:18px;
  --mono:ui-monospace,"SF Mono","JetBrains Mono",Menlo,Consolas,monospace;
  --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif;
  --shadow:0 4px 16px rgba(0,0,0,.35);
  --tap:44px;
  --sidebar-w:240px;
}
body.light{
  --bg:#fafafa; --bg-elev:#fff; --surface:#fff; --surface-2:#f5f5f5;
  --border:#e5e5e5; --border-strong:#d4d4d4;
  --text:#0a0a0a; --text-2:#525252; --text-3:#a3a3a3; --text-4:#d4d4d4;
  --shadow:0 4px 16px rgba(0,0,0,.06);
}
*,*::before,*::after{box-sizing:border-box}
*{margin:0;padding:0}
html,body{height:100%}
body{font-family:var(--sans);background:var(--bg);color:var(--text);font-size:14px;line-height:1.45;-webkit-font-smoothing:antialiased;-webkit-tap-highlight-color:transparent;overflow-x:hidden}
a{color:inherit;text-decoration:none}
button{font:inherit;color:inherit;cursor:pointer;background:none;border:0}
select,input,textarea{font:inherit;color:inherit}
table{border-collapse:collapse;width:100%}
.mono{font-family:var(--mono);font-variant-numeric:tabular-nums}
.icon{display:inline-flex;align-items:center;justify-content:center;flex-shrink:0;vertical-align:middle}
.icon svg{width:100%;height:100%;display:block}

/* Layout */
.layout{display:flex;min-height:100vh}
.main{flex:1;min-width:0;display:flex;flex-direction:column;padding-bottom:80px}

/* Sidebar */
.sidebar{
  width:var(--sidebar-w); background:var(--bg-elev); border-right:1px solid var(--border);
  display:flex; flex-direction:column; flex-shrink:0;
  position:fixed; inset:0 auto 0 0; z-index:100;
  transform:translateX(-100%); transition:transform .25s ease;
}
.sidebar.open{transform:translateX(0)}
.sidebar-head{padding:18px 18px 14px;display:flex;align-items:center;gap:10px;border-bottom:1px solid var(--border)}
.sidebar-brand{font-size:15px;font-weight:600;letter-spacing:-0.01em}
.sidebar-brand span{color:var(--text-3);font-weight:400;font-size:12px;margin-left:6px}
.sidebar-dot{width:8px;height:8px;border-radius:50%;background:var(--accent);box-shadow:0 0 12px var(--accent);animation:pulse 2.4s ease-in-out infinite}
@keyframes pulse{50%{opacity:.4}}
.sidebar-nav{flex:1;overflow-y:auto;padding:8px 8px;display:flex;flex-direction:column;gap:1px}
.nav-item{
  display:flex;align-items:center;gap:11px;padding:9px 11px;
  border-radius:var(--radius-sm);color:var(--text-2);font-size:13px;
  transition:background .12s, color .12s;min-height:38px
}
.nav-item:hover{background:var(--surface);color:var(--text)}
.nav-item.active{background:var(--surface-2);color:var(--text)}
.nav-item .icon{width:16px;height:16px;color:var(--text-3)}
.nav-item.active .icon{color:var(--accent)}
.nav-item-badge{
  margin-left:auto;background:var(--accent);color:#fff;
  font-size:10px;font-weight:600;padding:1px 6px;border-radius:999px;min-width:18px;text-align:center
}
.sidebar-foot{padding:12px 8px;border-top:1px solid var(--border)}

.sidebar-overlay{
  position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:99;
  opacity:0;visibility:hidden;transition:opacity .2s
}
.sidebar-overlay.open{opacity:1;visibility:visible}

@media(min-width:1024px){
  .sidebar{position:sticky;transform:translateX(0);height:100vh;top:0}
  .sidebar-overlay{display:none}
  .menu-btn{display:none!important}
  .main{margin-left:0}
}

/* Topbar */
.topbar{
  position:sticky;top:0;z-index:50;
  background:color-mix(in srgb, var(--bg) 80%, transparent);
  backdrop-filter:blur(10px); -webkit-backdrop-filter:blur(10px);
  border-bottom:1px solid var(--border);
  padding:10px 14px; display:flex; align-items:center; gap:10px; min-height:54px
}
.menu-btn{
  width:36px;height:36px;border-radius:var(--radius-sm);
  background:var(--surface);border:1px solid var(--border-strong);
  display:inline-flex;align-items:center;justify-content:center
}
.menu-btn .icon{width:18px;height:18px}
.topbar-title{font-size:15px;font-weight:600;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.topbar-actions{display:flex;align-items:center;gap:6px}

/* Buttons */
.btn{
  height:36px;min-width:36px;padding:0 14px;
  border-radius:var(--radius-sm);background:var(--surface);
  border:1px solid var(--border-strong);font-size:13px;font-weight:500;
  display:inline-flex;align-items:center;justify-content:center;gap:7px;
  transition:background .12s, border-color .12s, transform .08s;white-space:nowrap
}
.btn:hover{background:var(--surface-2);border-color:#3a3a3a}
.btn:active{transform:scale(.97)}
.btn .icon{width:14px;height:14px}
.btn-primary{background:var(--accent);border-color:var(--accent);color:#fff}
.btn-primary:hover{background:#ff6b30;border-color:#ff6b30}
.btn-success{background:var(--success);border-color:var(--success);color:#fff}
.btn-success:hover{background:#15803d;border-color:#15803d}
.btn-danger{background:var(--danger);border-color:var(--danger);color:#fff}
.btn-warn{background:var(--warn);border-color:var(--warn);color:#fff}
.btn-ghost{background:transparent}
.btn-icon{padding:0;width:36px}
.btn-sm{height:30px;padding:0 11px;font-size:12px}
.btn-full{width:100%}
.btn-lg{height:46px;padding:0 22px;font-size:14px;font-weight:600}

/* Container */
.container{max-width:1400px;margin:0 auto;padding:16px;width:100%}
@media(min-width:768px){.container{padding:24px}}

/* Cards */
.card{
  background:var(--surface);border:1px solid var(--border);
  border-radius:var(--radius);padding:var(--pad);
  margin-bottom:14px;contain:layout
}
.card-head{
  display:flex;align-items:center;justify-content:space-between;
  margin-bottom:14px;gap:10px;flex-wrap:wrap
}
.card-title{font-size:13px;font-weight:600;display:flex;align-items:center;gap:8px}
.card-title .icon{color:var(--text-3);width:15px;height:15px}

/* Section heading */
.section-head{display:flex;align-items:center;justify-content:space-between;margin:22px 0 10px;gap:10px}
.section-head h2{font-size:11px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:var(--text-3)}
.section-head .actions{display:flex;gap:6px}

/* KPI grid */
.kpi-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:var(--gap);margin-bottom:14px}
@media(min-width:768px){.kpi-grid{grid-template-columns:repeat(4,1fr)}}
.kpi{
  position:relative;background:var(--surface);border:1px solid var(--border);
  border-radius:var(--radius);padding:14px;overflow:hidden
}
.kpi::before{content:'';position:absolute;inset:0 auto 0 0;width:2px;background:var(--text-4)}
.kpi.accent::before{background:var(--accent)}
.kpi.success::before{background:var(--success)}
.kpi.warn::before{background:var(--warn)}
.kpi.info::before{background:var(--info)}
.kpi.danger::before{background:var(--danger)}
.kpi-label{font-size:10.5px;letter-spacing:.06em;text-transform:uppercase;color:var(--text-3);font-weight:500}
.kpi-value{font-family:var(--mono);font-variant-numeric:tabular-nums;font-size:clamp(22px,6vw,28px);font-weight:600;letter-spacing:-.02em;margin:6px 0 2px}
.kpi-change{font-size:11.5px;color:var(--text-2)}

/* Skeleton */
.skel{
  display:inline-block;
  background:linear-gradient(90deg,var(--surface-2) 0%,var(--border-strong) 50%,var(--surface-2) 100%);
  background-size:200% 100%;animation:shimmer 1.4s linear infinite;
  border-radius:4px;height:1em;min-width:40px;color:transparent
}
@keyframes shimmer{0%{background-position:200% 0}100%{background-position:-200% 0}}

/* Search */
.search-wrap{position:relative;margin-bottom:12px}
.search-input{
  width:100%;height:42px;padding:0 16px 0 40px;
  background:var(--surface);border:1px solid var(--border-strong);
  border-radius:var(--radius-sm);font-size:14px;color:var(--text)
}
.search-input:focus{outline:0;border-color:var(--accent)}
.search-icon{position:absolute;left:12px;top:50%;transform:translateY(-50%);color:var(--text-3);width:16px;height:16px;pointer-events:none}

/* Chips */
.chips{display:flex;gap:6px;overflow-x:auto;padding:4px 0 10px;-webkit-overflow-scrolling:touch;scrollbar-width:none}
.chips::-webkit-scrollbar{display:none}
.chip{
  flex:0 0 auto;height:32px;padding:0 13px;
  background:var(--surface);border:1px solid var(--border-strong);
  border-radius:999px;font-size:12.5px;color:var(--text-2);
  display:inline-flex;align-items:center;gap:5px;white-space:nowrap;
  transition:background .12s, color .12s, border-color .12s
}
.chip:hover{background:var(--surface-2);color:var(--text)}
.chip.active{background:var(--accent);border-color:var(--accent);color:#fff}

/* User grid */
.user-grid{display:grid;grid-template-columns:1fr;gap:10px}
@media(min-width:560px){.user-grid{grid-template-columns:repeat(2,1fr)}}
@media(min-width:900px){.user-grid{grid-template-columns:repeat(3,1fr)}}
@media(min-width:1280px){.user-grid{grid-template-columns:repeat(4,1fr)}}
.user-card{
  background:var(--surface);border:1px solid var(--border);
  border-left:3px solid var(--text-4);border-radius:var(--radius-sm);
  padding:13px 14px;cursor:pointer;
  transition:background .12s, border-color .12s, transform .08s
}
.user-card:hover{background:var(--surface-2)}
.user-card:active{transform:scale(.99)}
.user-card.online{border-left-color:var(--success)}
.user-card.idle{border-left-color:var(--warn)}
.user-card.offline{border-left-color:var(--text-4)}
.user-card .uid{font-family:var(--mono);font-size:13px;font-weight:600;color:var(--text)}
.user-card .preview{font-size:12.5px;color:var(--text-2);margin:7px 0 8px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;line-height:1.4;min-height:35px}
.user-card .meta{display:flex;justify-content:space-between;font-size:11.5px;color:var(--text-3);padding-top:8px;border-top:1px solid var(--border)}
.user-card .meta b{font-family:var(--mono);color:var(--text-2);font-weight:600}
.user-card-head{display:flex;justify-content:space-between;align-items:flex-start;gap:8px}

/* Badges */
.badge{
  display:inline-flex;align-items:center;gap:4px;
  padding:2px 7px;border-radius:999px;font-size:10.5px;font-weight:600;
  border:1px solid;white-space:nowrap;letter-spacing:.02em
}
.badge-online{color:#4ade80;border-color:rgba(74,222,128,.3);background:rgba(74,222,128,.08)}
.badge-idle{color:#fbbf24;border-color:rgba(251,191,36,.3);background:rgba(251,191,36,.08)}
.badge-offline{color:var(--text-3);border-color:var(--border-strong);background:transparent}
.badge-vip{color:#fbbf24;border-color:rgba(251,191,36,.4);background:rgba(251,191,36,.12)}
.badge-locked{color:#f87171;border-color:rgba(248,113,113,.3);background:rgba(248,113,113,.08)}
.badge-fav{color:#fb923c;border-color:rgba(251,146,60,.3);background:rgba(251,146,60,.08)}
.badge-tag{color:#a3a3a3;border-color:var(--border-strong);background:var(--surface-2)}
.badge-dot{width:5px;height:5px;border-radius:50%;background:currentColor;display:inline-block}
.user-badges{display:flex;gap:4px;flex-wrap:wrap;margin-top:5px}

/* Empty state */
.empty{text-align:center;padding:40px 20px;color:var(--text-3);font-size:13px}
.empty .icon{width:32px;height:32px;margin:0 auto 12px;color:var(--text-4)}

/* Forms */
.form-group{margin-bottom:14px}
.form-label{display:block;margin-bottom:6px;font-size:12px;font-weight:500;color:var(--text-2)}
.form-input,.form-textarea,.form-select{
  width:100%;padding:11px 13px;
  background:var(--bg-elev);border:1px solid var(--border-strong);
  border-radius:var(--radius-sm);font-size:14px;color:var(--text);
  transition:border-color .12s
}
.form-input:focus,.form-textarea:focus,.form-select:focus{outline:0;border-color:var(--accent)}
.form-textarea{min-height:96px;resize:vertical;font-family:var(--sans)}
.form-select{appearance:none;padding-right:34px;background-image:url("data:image/svg+xml,%3Csvg width='10' height='6' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M1 1l4 4 4-4' stroke='%23a3a3a3' stroke-width='1.5' fill='none' stroke-linecap='round'/%3E%3C/svg%3E");background-repeat:no-repeat;background-position:right 12px center}
.form-hint{font-size:11.5px;color:var(--text-3);margin-top:5px}
.form-row{display:grid;grid-template-columns:1fr;gap:14px}
@media(min-width:640px){.form-row.cols-2{grid-template-columns:1fr 1fr}.form-row.cols-3{grid-template-columns:repeat(3,1fr)}}

.checkbox{
  display:flex;gap:10px;align-items:flex-start;padding:11px 13px;
  background:var(--bg-elev);border:1px solid var(--border);
  border-radius:var(--radius-sm);cursor:pointer;margin-bottom:8px
}
.checkbox input{width:18px;height:18px;flex-shrink:0;margin-top:2px;accent-color:var(--accent)}
.checkbox-content{flex:1;min-width:0}
.checkbox-content strong{font-size:13px;color:var(--text);font-weight:600;display:block}
.checkbox-content small{font-size:11.5px;color:var(--text-3);display:block;margin-top:3px}

/* Tables */
.table-wrap{overflow-x:auto;margin:0 -6px}
.table-wrap table{min-width:560px}
thead th{
  text-align:left;font-size:10.5px;letter-spacing:.06em;text-transform:uppercase;
  color:var(--text-3);font-weight:500;padding:9px 11px;
  border-bottom:1px solid var(--border)
}
tbody td{padding:10px 11px;border-bottom:1px solid var(--border);font-size:13px;color:var(--text-2)}
tbody td.mono,tbody td b{font-family:var(--mono);color:var(--text);font-weight:600;font-variant-numeric:tabular-nums}
tbody tr:last-child td{border-bottom:0}
tbody tr:hover{background:rgba(255,255,255,.02)}
body.light tbody tr:hover{background:rgba(0,0,0,.02)}

/* Alert banners */
.alert-banner{
  display:flex;gap:11px;align-items:flex-start;
  padding:11px 14px;border-radius:var(--radius-sm);
  margin-bottom:12px;font-size:13px;border:1px solid;line-height:1.5
}
.alert-banner.danger{color:#fca5a5;border-color:rgba(239,68,68,.3);background:rgba(239,68,68,.08)}
.alert-banner.warn{color:#fcd34d;border-color:rgba(245,158,11,.3);background:rgba(245,158,11,.08)}
.alert-banner.success{color:#86efac;border-color:rgba(22,163,74,.3);background:rgba(22,163,74,.08)}
.alert-banner.info{color:#93c5fd;border-color:rgba(59,130,246,.3);background:rgba(59,130,246,.08)}
.alert-banner strong{color:var(--text)}

/* Alert list */
.alert-row{
  display:flex;gap:12px;padding:12px 14px;border-bottom:1px solid var(--border);
  cursor:pointer;transition:background .12s
}
.alert-row:hover{background:var(--surface-2)}
.alert-row.unread{background:var(--accent-soft);border-left:2px solid var(--accent);padding-left:12px}
.alert-row .icon{width:18px;height:18px;color:var(--text-3);flex-shrink:0}
.alert-row .body{flex:1;min-width:0}
.alert-row .msg{font-size:13.5px;color:var(--text);line-height:1.4}
.alert-row .time{font-size:11.5px;color:var(--text-3);margin-top:3px}

/* Chart container */
.chart-wrap{position:relative;height:240px;width:100%}
@media(min-width:768px){.chart-wrap{height:280px}}

/* Charts grid */
.charts-grid{display:grid;grid-template-columns:1fr;gap:14px;margin-bottom:14px}
@media(min-width:900px){.charts-grid{grid-template-columns:1fr 1fr}}

/* Gallery */
.gallery-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(110px,1fr));gap:8px}
.gallery-item{
  position:relative;aspect-ratio:1;border-radius:var(--radius-sm);
  overflow:hidden;cursor:pointer;background:var(--surface-2);border:1px solid var(--border)
}
.gallery-item img{width:100%;height:100%;object-fit:cover;display:block}
.gallery-del{
  position:absolute;top:5px;right:5px;width:26px;height:26px;
  background:rgba(239,68,68,.9);border-radius:50%;color:#fff;
  display:flex;align-items:center;justify-content:center;opacity:0;transition:opacity .12s
}
.gallery-item:hover .gallery-del{opacity:1}
.gallery-del .icon{width:14px;height:14px}

/* Chat layout */
.chat-shell{display:flex;flex-direction:column;height:100vh;overflow:hidden}
.chat-topbar{
  background:var(--bg-elev);border-bottom:1px solid var(--border);
  padding:10px 14px;display:flex;align-items:center;gap:12px;min-height:60px
}
.chat-back{
  width:36px;height:36px;border-radius:var(--radius-sm);
  background:var(--surface);border:1px solid var(--border-strong);
  display:flex;align-items:center;justify-content:center;flex-shrink:0
}
.chat-back .icon{width:18px;height:18px}
.chat-user{flex:1;min-width:0;cursor:pointer}
.chat-user-name{font-weight:600;font-size:14px;font-family:var(--mono);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.chat-user-status{font-size:11.5px;color:var(--text-3);margin-top:2px}
.chat-tools{display:flex;gap:6px;flex-shrink:0}
.chat-tool{
  width:36px;height:36px;border-radius:var(--radius-sm);
  background:var(--surface);border:1px solid var(--border-strong);
  display:flex;align-items:center;justify-content:center;color:var(--text-2)
}
.chat-tool.on{background:var(--accent);border-color:var(--accent);color:#fff}
.chat-tool .icon{width:18px;height:18px}

.takeover-banner{
  background:linear-gradient(135deg,#ef4444,#dc2626);color:#fff;
  padding:10px 18px;text-align:center;font-weight:600;font-size:13px
}

.chat-messages{flex:1;overflow-y:auto;padding:14px;display:flex;flex-direction:column;gap:8px;background:var(--bg)}
.msg{max-width:86%;padding:10px 13px;border-radius:14px;font-size:13.5px;line-height:1.45;animation:fadeUp .25s ease}
@keyframes fadeUp{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:translateY(0)}}
.msg-user{align-self:flex-end;background:var(--accent);color:#fff;border-bottom-right-radius:4px}
.msg-sophia{align-self:flex-start;background:var(--surface);border:1px solid var(--border);border-bottom-left-radius:4px}
.msg-admin{align-self:flex-start;background:var(--warn);color:#1c1c1c;border-bottom-left-radius:4px}
.msg-system{align-self:center;background:var(--surface-2);color:var(--text-3);font-size:11.5px;padding:5px 12px;border-radius:999px}
.msg-time{font-size:10px;opacity:.7;margin-top:4px;font-family:var(--mono)}
.msg-label{font-size:10px;font-weight:600;margin-bottom:3px;opacity:.7;text-transform:uppercase;letter-spacing:.04em}

.quick-replies{display:flex;gap:6px;overflow-x:auto;padding:8px 14px;background:var(--bg-elev);border-top:1px solid var(--border);scrollbar-width:none}
.quick-replies::-webkit-scrollbar{display:none}
.quick-reply{
  flex:0 0 auto;height:30px;padding:0 13px;background:var(--surface);
  border:1px solid var(--border-strong);border-radius:999px;font-size:12px;
  display:flex;align-items:center;white-space:nowrap
}
.quick-reply:active{background:var(--accent);border-color:var(--accent);color:#fff}

.photo-preview{display:none;align-items:center;gap:10px;padding:8px 14px;background:var(--surface);border-top:1px solid var(--border)}
.photo-preview.active{display:flex}
.photo-preview img{width:50px;height:50px;object-fit:cover;border-radius:var(--radius-sm)}
.photo-preview-name{flex:1;font-size:12px;color:var(--text-2);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.photo-preview-remove{width:30px;height:30px;background:var(--danger);color:#fff;border-radius:50%;display:flex;align-items:center;justify-content:center;flex-shrink:0}
.photo-preview-remove .icon{width:14px;height:14px}

.chat-input-bar{background:var(--bg-elev);border-top:1px solid var(--border);padding:10px 12px;display:flex;align-items:center;gap:8px}
.chat-attach{width:42px;height:42px;border-radius:50%;background:var(--surface);border:1px solid var(--border-strong);display:flex;align-items:center;justify-content:center;flex-shrink:0}
.chat-attach .icon{width:18px;height:18px;color:var(--text-2)}
.chat-input{flex:1;height:42px;padding:0 16px;background:var(--surface);border:1px solid var(--border-strong);border-radius:21px;font-size:14px;color:var(--text)}
.chat-input:focus{outline:0;border-color:var(--accent)}
.chat-send{width:42px;height:42px;border-radius:50%;background:var(--accent);color:#fff;display:flex;align-items:center;justify-content:center;flex-shrink:0}
.chat-send .icon{width:18px;height:18px}

/* FAB */
.fab{
  position:fixed;bottom:18px;right:18px;width:54px;height:54px;border-radius:50%;
  background:var(--accent);color:#fff;display:flex;align-items:center;justify-content:center;
  box-shadow:0 8px 22px rgba(255,90,31,.4);z-index:40;
  transition:transform .15s
}
.fab:active{transform:scale(.92)}
.fab .icon{width:22px;height:22px}

/* Bottom sheet */
.sheet-overlay{position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:200;opacity:0;visibility:hidden;transition:opacity .2s}
.sheet-overlay.open{opacity:1;visibility:visible}
.sheet{
  position:fixed;left:0;right:0;bottom:0;
  background:var(--bg-elev);border-radius:18px 18px 0 0;
  padding:18px;z-index:201;transform:translateY(100%);
  transition:transform .25s ease;max-height:80vh;overflow-y:auto;
  padding-bottom:max(18px,env(safe-area-inset-bottom))
}
.sheet.open{transform:translateY(0)}
.sheet-handle{width:36px;height:4px;background:var(--border-strong);border-radius:2px;margin:0 auto 14px}
.sheet-title{font-size:15px;font-weight:600;text-align:center;margin-bottom:14px}
.action-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}
.action-btn{
  display:flex;flex-direction:column;align-items:center;gap:6px;
  padding:14px 8px;background:var(--surface);border:1px solid var(--border);
  border-radius:var(--radius-sm);font-size:11.5px;color:var(--text-2);min-height:78px
}
.action-btn:active{transform:scale(.95)}
.action-btn .icon{width:22px;height:22px;color:var(--text)}
.action-btn.danger{color:var(--danger)}
.action-btn.danger .icon{color:var(--danger)}
.action-btn.success{color:var(--success)}
.action-btn.success .icon{color:var(--success)}
.action-btn.warn{color:var(--warn)}
.action-btn.warn .icon{color:var(--warn)}

/* Modal */
.modal-overlay{position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:300;display:none;align-items:center;justify-content:center;padding:16px}
.modal-overlay.open{display:flex}
.modal{background:var(--bg-elev);border:1px solid var(--border);border-radius:var(--radius);width:100%;max-width:520px;max-height:90vh;overflow:hidden;display:flex;flex-direction:column}
.modal-head{padding:14px 18px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center}
.modal-head h3{font-size:14px;font-weight:600}
.modal-close{width:30px;height:30px;display:flex;align-items:center;justify-content:center;border-radius:var(--radius-sm)}
.modal-close:hover{background:var(--surface)}
.modal-close .icon{width:16px;height:16px}
.modal-body{padding:16px 18px;overflow-y:auto;flex:1}
.modal-foot{padding:12px 18px;border-top:1px solid var(--border);display:flex;gap:8px;justify-content:flex-end}

/* Toast */
.toast{
  position:fixed;bottom:24px;left:50%;
  transform:translateX(-50%) translateY(100px);
  padding:12px 22px;border-radius:999px;font-size:13px;font-weight:500;
  z-index:1000;opacity:0;transition:transform .25s ease, opacity .25s ease;
  background:var(--surface);border:1px solid var(--border-strong);color:var(--text);
  box-shadow:var(--shadow)
}
.toast.show{transform:translateX(-50%) translateY(0);opacity:1}
.toast.success{background:var(--success);border-color:var(--success);color:#fff}
.toast.error{background:var(--danger);border-color:var(--danger);color:#fff}

/* Login */
.login-page{min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px;background:var(--bg)}
.login-card{background:var(--surface);border:1px solid var(--border);padding:28px;border-radius:var(--radius-lg);width:100%;max-width:380px}
.login-brand{text-align:center;margin-bottom:24px}
.login-brand h1{font-size:22px;font-weight:600;letter-spacing:-.02em}
.login-brand p{font-size:12px;color:var(--text-3);margin-top:4px}

/* Spinner */
.spin{animation:spin .8s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}

/* Helpers */
.hide-mobile{display:none}
@media(min-width:768px){.hide-mobile{display:inline-flex}.hide-desktop{display:none}}
.text-2{color:var(--text-2)}
.text-3{color:var(--text-3)}
.text-mono{font-family:var(--mono);font-variant-numeric:tabular-nums}
.mt-sm{margin-top:8px}.mt-md{margin-top:14px}.mt-lg{margin-top:22px}

/* Filter option (broadcast) */
.filter-opt{display:flex;gap:10px;align-items:flex-start;padding:11px 13px;background:var(--surface-2);border:1px solid var(--border);border-radius:var(--radius-sm);margin-bottom:6px;cursor:pointer}
.filter-opt.danger{border-color:rgba(239,68,68,.3);background:rgba(239,68,68,.06)}
.filter-opt.success{border-color:rgba(22,163,74,.3);background:rgba(22,163,74,.06)}
.filter-opt input{width:18px;height:18px;margin-top:2px;flex-shrink:0;accent-color:var(--accent)}
.filter-opt strong{font-size:13px;font-weight:600;display:block;color:var(--text)}
.filter-opt small{font-size:11.5px;color:var(--text-3);display:block;margin-top:3px}



/* ========================= V6.3 VISUAL REFRESH =========================
   Upgrade visual: dashboard mais vivo, moderno e com microinterações.
   Mantém a mesma estrutura HTML e rotas, só melhora a apresentação.
*/
:root{
  --bg:#070712;
  --bg-elev:rgba(14,15,28,.86);
  --surface:rgba(22,24,43,.78);
  --surface-2:rgba(33,36,61,.86);
  --surface-3:rgba(255,255,255,.08);
  --border:rgba(255,255,255,.10);
  --border-strong:rgba(255,255,255,.16);
  --text:#f9fafb;
  --text-2:#c7c9d9;
  --text-3:#8f94ad;
  --text-4:#565b76;
  --accent:#ff5a7d;
  --accent-2:#7c3aed;
  --accent-3:#22d3ee;
  --accent-soft:rgba(255,90,125,.16);
  --success:#22c55e;
  --warn:#f59e0b;
  --danger:#f43f5e;
  --info:#38bdf8;
  --shadow:0 18px 50px rgba(0,0,0,.38);
  --shadow-soft:0 12px 34px rgba(0,0,0,.22);
  --glow:0 0 0 1px rgba(255,255,255,.08),0 18px 60px rgba(124,58,237,.22);
}

body.light{
  --bg:#f4f7fb;
  --bg-elev:rgba(255,255,255,.86);
  --surface:rgba(255,255,255,.82);
  --surface-2:#f1f5f9;
  --surface-3:rgba(15,23,42,.06);
  --border:rgba(15,23,42,.09);
  --border-strong:rgba(15,23,42,.14);
  --text:#0f172a;
  --text-2:#475569;
  --text-3:#64748b;
  --text-4:#cbd5e1;
  --shadow:0 18px 45px rgba(15,23,42,.10);
  --shadow-soft:0 10px 28px rgba(15,23,42,.08);
}

body{
  background:
    radial-gradient(circle at 8% -10%, rgba(255,90,125,.26), transparent 34%),
    radial-gradient(circle at 82% 4%, rgba(34,211,238,.18), transparent 28%),
    radial-gradient(circle at 58% 108%, rgba(124,58,237,.28), transparent 34%),
    var(--bg);
  min-height:100vh;
}

body::before{
  content:"";
  position:fixed;
  inset:0;
  pointer-events:none;
  z-index:-1;
  background-image:
    linear-gradient(rgba(255,255,255,.035) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,255,255,.035) 1px, transparent 1px);
  background-size:42px 42px;
  mask-image:linear-gradient(to bottom, rgba(0,0,0,.72), transparent 76%);
}

body.light::before{
  background-image:
    linear-gradient(rgba(15,23,42,.035) 1px, transparent 1px),
    linear-gradient(90deg, rgba(15,23,42,.035) 1px, transparent 1px);
}

.layout{isolation:isolate}
.main{position:relative}
.container{max-width:1480px}

/* Premium shell */
.sidebar{
  background:
    linear-gradient(180deg, rgba(255,255,255,.08), rgba(255,255,255,.035)),
    rgba(8,9,19,.82);
  backdrop-filter:blur(18px);
  -webkit-backdrop-filter:blur(18px);
  border-right:1px solid rgba(255,255,255,.11);
  box-shadow:14px 0 60px rgba(0,0,0,.24);
}

body.light .sidebar{
  background:rgba(255,255,255,.84);
  box-shadow:14px 0 50px rgba(15,23,42,.08);
}

.sidebar-head{
  min-height:72px;
  background:
    radial-gradient(circle at 16% 16%, rgba(255,90,125,.28), transparent 45%),
    linear-gradient(135deg, rgba(124,58,237,.18), transparent 58%);
}

.sidebar-dot{
  width:12px;
  height:12px;
  background:linear-gradient(135deg,var(--accent),var(--accent-3));
  box-shadow:0 0 0 6px rgba(255,90,125,.12),0 0 28px rgba(34,211,238,.35);
}

.sidebar-brand{
  font-size:17px;
  font-weight:800;
  letter-spacing:-.03em;
}

.sidebar-brand span{
  display:inline-flex;
  align-items:center;
  padding:2px 8px;
  border-radius:999px;
  background:rgba(255,255,255,.08);
  color:var(--text-2);
  font-size:10.5px;
  margin-left:8px;
  border:1px solid rgba(255,255,255,.08);
}

.nav-item{
  position:relative;
  margin:2px 4px;
  min-height:42px;
  border-radius:13px;
  color:var(--text-2);
  transition:transform .18s ease, background .18s ease, color .18s ease, box-shadow .18s ease;
}

.nav-item:hover{
  transform:translateX(3px);
  background:rgba(255,255,255,.075);
  color:var(--text);
}

.nav-item.active{
  color:#fff;
  background:
    linear-gradient(135deg, rgba(255,90,125,.95), rgba(124,58,237,.95));
  box-shadow:0 12px 28px rgba(124,58,237,.26), inset 0 1px 0 rgba(255,255,255,.24);
}

.nav-item.active .icon{color:#fff}
.nav-item-badge{
  background:linear-gradient(135deg,var(--accent),var(--accent-2));
  box-shadow:0 8px 22px rgba(255,90,125,.26);
}

/* Topbar glass */
.topbar{
  min-height:64px;
  background:rgba(8,9,19,.58);
  backdrop-filter:blur(22px) saturate(140%);
  -webkit-backdrop-filter:blur(22px) saturate(140%);
  border-bottom:1px solid rgba(255,255,255,.10);
  box-shadow:0 10px 36px rgba(0,0,0,.18);
}

body.light .topbar{
  background:rgba(255,255,255,.74);
  border-bottom:1px solid rgba(15,23,42,.08);
}

.topbar-title{
  font-size:16px;
  font-weight:800;
  letter-spacing:-.025em;
}

.btn{
  border-radius:12px;
  border-color:var(--border-strong);
  background:rgba(255,255,255,.07);
  box-shadow:inset 0 1px 0 rgba(255,255,255,.08);
  transition:transform .16s ease, background .16s ease, border-color .16s ease, box-shadow .16s ease;
}

body.light .btn{background:rgba(255,255,255,.84)}
.btn:hover{
  transform:translateY(-1px);
  background:rgba(255,255,255,.11);
  border-color:rgba(255,255,255,.24);
  box-shadow:0 10px 24px rgba(0,0,0,.14), inset 0 1px 0 rgba(255,255,255,.12);
}

.btn-primary{
  border:0;
  background:linear-gradient(135deg,var(--accent),var(--accent-2));
  box-shadow:0 12px 26px rgba(255,90,125,.25);
}

.btn-primary:hover{
  background:linear-gradient(135deg,#ff7290,#8b5cf6);
}

/* Dashboard hero */
.dashboard-hero{
  position:relative;
  overflow:hidden;
  border:1px solid rgba(255,255,255,.12);
  border-radius:26px;
  padding:24px;
  margin-bottom:18px;
  background:
    radial-gradient(circle at 10% 10%, rgba(255,90,125,.40), transparent 28%),
    radial-gradient(circle at 90% 16%, rgba(34,211,238,.30), transparent 26%),
    linear-gradient(135deg, rgba(255,255,255,.12), rgba(255,255,255,.045));
  box-shadow:var(--glow);
}

body.light .dashboard-hero{
  background:
    radial-gradient(circle at 10% 10%, rgba(255,90,125,.24), transparent 30%),
    radial-gradient(circle at 90% 16%, rgba(14,165,233,.22), transparent 28%),
    linear-gradient(135deg, rgba(255,255,255,.96), rgba(248,250,252,.78));
}

.dashboard-hero::after{
  content:"";
  position:absolute;
  width:260px;
  height:260px;
  right:-80px;
  top:-90px;
  border-radius:999px;
  background:conic-gradient(from 180deg, rgba(255,90,125,.45), rgba(124,58,237,.18), rgba(34,211,238,.42), rgba(255,90,125,.45));
  filter:blur(8px);
  opacity:.55;
  animation:floatOrb 8s ease-in-out infinite;
}

@keyframes floatOrb{
  0%,100%{transform:translate3d(0,0,0) rotate(0)}
  50%{transform:translate3d(-18px,14px,0) rotate(16deg)}
}

.hero-content{
  position:relative;
  z-index:1;
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:18px;
  flex-wrap:wrap;
}

.hero-kicker{
  display:inline-flex;
  align-items:center;
  gap:8px;
  padding:6px 10px;
  border-radius:999px;
  font-size:11px;
  font-weight:800;
  text-transform:uppercase;
  letter-spacing:.09em;
  color:#fff;
  background:rgba(255,255,255,.12);
  border:1px solid rgba(255,255,255,.13);
}

body.light .hero-kicker{color:#6d28d9;background:rgba(124,58,237,.08)}
.hero-title{
  margin-top:12px;
  font-size:clamp(26px,4vw,42px);
  line-height:1;
  font-weight:900;
  letter-spacing:-.055em;
}

.hero-title span{
  background:linear-gradient(135deg,#fff,var(--accent-3));
  -webkit-background-clip:text;
  background-clip:text;
  color:transparent;
}

body.light .hero-title span{
  background:linear-gradient(135deg,#7c3aed,#db2777);
  -webkit-background-clip:text;
  background-clip:text;
  color:transparent;
}

.hero-subtitle{
  margin-top:10px;
  max-width:680px;
  color:var(--text-2);
  font-size:14px;
}

.hero-actions{
  display:flex;
  align-items:center;
  gap:10px;
  flex-wrap:wrap;
}

.live-pill{
  display:inline-flex;
  align-items:center;
  gap:8px;
  padding:10px 12px;
  border-radius:999px;
  color:#d1fae5;
  background:rgba(34,197,94,.10);
  border:1px solid rgba(34,197,94,.24);
  font-size:12px;
  font-weight:700;
}

.live-pill::before{
  content:"";
  width:8px;
  height:8px;
  border-radius:999px;
  background:#22c55e;
  box-shadow:0 0 0 6px rgba(34,197,94,.12),0 0 22px rgba(34,197,94,.55);
}

/* KPI Cards */
.kpi-grid{gap:16px;margin-bottom:18px}
.kpi{
  border:1px solid rgba(255,255,255,.12);
  border-radius:22px;
  padding:18px;
  background:
    linear-gradient(145deg, rgba(255,255,255,.12), rgba(255,255,255,.055));
  box-shadow:var(--shadow-soft);
  overflow:hidden;
  transform:translateZ(0);
  transition:transform .18s ease, box-shadow .18s ease, border-color .18s ease;
}

body.light .kpi{
  background:rgba(255,255,255,.86);
  border-color:rgba(15,23,42,.08);
}

.kpi:hover{
  transform:translateY(-3px);
  box-shadow:0 20px 48px rgba(0,0,0,.28);
  border-color:rgba(255,255,255,.22);
}

.kpi::before{
  width:100%;
  height:3px;
  inset:0 0 auto 0;
  background:linear-gradient(90deg,var(--accent),var(--accent-2),var(--accent-3));
}

.kpi::after{
  content:"";
  position:absolute;
  right:-42px;
  bottom:-48px;
  width:140px;
  height:140px;
  border-radius:999px;
  opacity:.12;
  background:currentColor;
  filter:blur(2px);
}

.kpi.info{color:var(--info)}
.kpi.success{color:var(--success)}
.kpi.warn{color:var(--warn)}
.kpi.danger{color:var(--danger)}
.kpi-label{color:var(--text-3);font-size:11px;font-weight:800}
.kpi-value{
  color:var(--text);
  font-size:clamp(28px,5vw,38px);
  margin-top:8px;
  letter-spacing:-.06em;
}
.kpi-change{color:var(--text-2);font-weight:600}

/* Cards, forms and chips */
.card{
  border-radius:22px;
  border:1px solid rgba(255,255,255,.11);
  background:linear-gradient(145deg, rgba(255,255,255,.10), rgba(255,255,255,.045));
  box-shadow:var(--shadow-soft);
}

body.light .card{
  background:rgba(255,255,255,.86);
  border-color:rgba(15,23,42,.08);
}

.card-title{
  font-size:14px;
  font-weight:800;
}

.search-wrap{
  padding:4px;
  border-radius:18px;
  background:rgba(255,255,255,.055);
  border:1px solid rgba(255,255,255,.09);
  box-shadow:inset 0 1px 0 rgba(255,255,255,.06);
}

body.light .search-wrap{background:rgba(255,255,255,.72)}
.search-input{
  height:48px;
  border-radius:14px;
  background:rgba(255,255,255,.075);
  border:0;
  font-weight:600;
}

body.light .search-input{background:#fff}
.search-input:focus{
  box-shadow:0 0 0 3px rgba(255,90,125,.16);
}

.chips{
  gap:8px;
  padding:8px 0 16px;
}

.chip{
  height:38px;
  padding:0 16px;
  border-radius:999px;
  background:rgba(255,255,255,.07);
  border:1px solid rgba(255,255,255,.11);
  font-weight:800;
  color:var(--text-2);
  box-shadow:inset 0 1px 0 rgba(255,255,255,.07);
}

body.light .chip{background:rgba(255,255,255,.82)}
.chip:hover{
  transform:translateY(-1px);
  border-color:rgba(255,255,255,.22);
  background:rgba(255,255,255,.11);
}

.chip.active{
  color:#fff;
  border:0;
  background:linear-gradient(135deg,var(--accent),var(--accent-2));
  box-shadow:0 12px 28px rgba(124,58,237,.24);
}

/* User cards */
.user-grid{gap:14px}
.user-card{
  position:relative;
  border:1px solid rgba(255,255,255,.11);
  border-left:0;
  border-radius:20px;
  padding:16px;
  background:
    linear-gradient(145deg, rgba(255,255,255,.10), rgba(255,255,255,.045));
  box-shadow:0 10px 28px rgba(0,0,0,.16);
  overflow:hidden;
  transition:transform .18s ease, border-color .18s ease, box-shadow .18s ease, background .18s ease;
}

body.light .user-card{
  background:rgba(255,255,255,.86);
  border-color:rgba(15,23,42,.08);
}

.user-card::before{
  content:"";
  position:absolute;
  inset:0 auto 0 0;
  width:4px;
  background:var(--text-4);
}

.user-card::after{
  content:"";
  position:absolute;
  width:86px;
  height:86px;
  right:-34px;
  top:-34px;
  border-radius:999px;
  background:rgba(255,255,255,.12);
  pointer-events:none;
}

.user-card.online::before{background:linear-gradient(180deg,#22c55e,#14b8a6)}
.user-card.idle::before{background:linear-gradient(180deg,#f59e0b,#f97316)}
.user-card.offline::before{background:linear-gradient(180deg,#64748b,#334155)}

.user-card:hover{
  transform:translateY(-4px);
  border-color:rgba(255,255,255,.20);
  box-shadow:0 18px 42px rgba(0,0,0,.26);
  background:
    radial-gradient(circle at 100% 0%, rgba(255,90,125,.16), transparent 34%),
    linear-gradient(145deg, rgba(255,255,255,.12), rgba(255,255,255,.055));
}

.user-card .uid{
  font-size:13.5px;
  font-weight:800;
  letter-spacing:-.02em;
}

.user-card .preview{
  color:var(--text-2);
  min-height:44px;
  margin:10px 0 10px;
}

.user-card .meta{
  border-top:1px solid rgba(255,255,255,.10);
  color:var(--text-3);
}

body.light .user-card .meta{border-top-color:rgba(15,23,42,.08)}
.user-card .meta b{color:var(--text);font-weight:900}

/* Badges */
.user-badges{display:flex;gap:6px;flex-wrap:wrap;margin-top:10px}
.badge{
  border-radius:999px;
  padding:4px 8px;
  font-weight:900;
  letter-spacing:.02em;
  border:0;
}

.badge-dot{
  width:6px;
  height:6px;
  border-radius:999px;
  display:inline-block;
  background:currentColor;
  box-shadow:0 0 14px currentColor;
}

.badge-online{color:#bbf7d0;background:rgba(34,197,94,.15)}
.badge-idle{color:#fde68a;background:rgba(245,158,11,.16)}
.badge-offline{color:#cbd5e1;background:rgba(148,163,184,.14)}
.badge-vip{color:#fce7f3;background:linear-gradient(135deg,rgba(236,72,153,.28),rgba(124,58,237,.24))}
.badge-locked{color:#fecdd3;background:rgba(244,63,94,.18)}
.badge-fav{color:#fef3c7;background:rgba(245,158,11,.18)}

/* Tables, modals, gallery and chat */
.table-wrap, .chat-messages, .modal, .sheet{
  border-radius:22px;
  border-color:rgba(255,255,255,.11);
  background:linear-gradient(145deg, rgba(255,255,255,.10), rgba(255,255,255,.045));
  box-shadow:var(--shadow-soft);
}

table tr{transition:background .14s ease}
tbody tr:hover{background:rgba(255,255,255,.055)}

.form-input, .form-select, .form-textarea{
  border-radius:14px;
  background:rgba(255,255,255,.07);
  border:1px solid rgba(255,255,255,.12);
}

.form-input:focus, .form-select:focus, .form-textarea:focus{
  border-color:rgba(255,90,125,.55);
  box-shadow:0 0 0 3px rgba(255,90,125,.14);
}

.gallery-item{
  border-radius:20px;
  overflow:hidden;
  box-shadow:var(--shadow-soft);
  transition:transform .18s ease, box-shadow .18s ease;
}

.gallery-item:hover{
  transform:translateY(-4px) scale(1.01);
  box-shadow:0 20px 46px rgba(0,0,0,.28);
}

.toast{
  border-radius:16px;
  background:linear-gradient(135deg, rgba(20,21,35,.96), rgba(43,31,62,.96));
  border:1px solid rgba(255,255,255,.14);
  box-shadow:0 18px 44px rgba(0,0,0,.34);
}

/* Loading and subtle motion */
.skel{
  background:linear-gradient(90deg, rgba(255,255,255,.06), rgba(255,255,255,.17), rgba(255,255,255,.06));
  background-size:220% 100%;
}

@media (prefers-reduced-motion: reduce){
  *,*::before,*::after{
    animation-duration:.001ms!important;
    animation-iteration-count:1!important;
    scroll-behavior:auto!important;
    transition-duration:.001ms!important;
  }
}

@media(max-width:720px){
  .dashboard-hero{padding:20px;border-radius:22px}
  .hero-actions{width:100%}
  .hero-actions .btn, .live-pill{flex:1;justify-content:center}
  .kpi-grid{gap:12px}
}
"""

# ========================= JS COMMON =========================

ADMIN_JS_COMMON = r"""
(function(){
'use strict';
// Theme
const savedTheme = localStorage.getItem('sa-theme') || 'dark';
if (savedTheme === 'light') document.body.classList.add('light');
window.toggleTheme = function(){
  document.body.classList.toggle('light');
  const isLight = document.body.classList.contains('light');
  localStorage.setItem('sa-theme', isLight ? 'light' : 'dark');
  document.querySelectorAll('[data-theme-icon]').forEach(el => {
    el.innerHTML = isLight ? ICON_MOON : ICON_SUN;
  });
};
const ICON_MOON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="100%" height="100%"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';
const ICON_SUN = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="100%" height="100%"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>';

// Sidebar drawer
window.toggleSidebar = function(){
  const sb = document.getElementById('sidebar');
  const ov = document.getElementById('sidebarOverlay');
  if (!sb) return;
  sb.classList.toggle('open');
  if (ov) ov.classList.toggle('open');
};

// Toast
window.toast = function(msg, type){
  let t = document.getElementById('toast');
  if (!t) {
    t = document.createElement('div');
    t.id = 'toast';
    t.className = 'toast';
    document.body.appendChild(t);
  }
  t.textContent = msg;
  t.className = 'toast ' + (type||'') + ' show';
  clearTimeout(window._toastTimer);
  window._toastTimer = setTimeout(() => t.classList.remove('show'), 2800);
};

// Modal
window.openModal = function(id){ const m = document.getElementById(id); if (m) m.classList.add('open'); };
window.closeModal = function(id){ const m = document.getElementById(id); if (m) m.classList.remove('open'); };

// Bottom sheet
window.toggleSheet = function(id){
  const s = document.getElementById(id);
  const ov = document.getElementById(id + 'Overlay');
  if (s) s.classList.toggle('open');
  if (ov) ov.classList.toggle('open');
};

// Fetch wrapper
window.api = async function(url, opts){
  opts = opts || {};
  try {
    const r = await fetch(url, opts);
    if (r.status === 401) { window.location.href = '/login'; return null; }
    const ct = r.headers.get('content-type') || '';
    if (ct.includes('application/json')) return await r.json();
    return await r.text();
  } catch(e) {
    console.error('api error:', e);
    return null;
  }
};

// Confirm helper
window.confirmAction = function(msg){ return confirm(msg); };

// Close modal on outside click
document.addEventListener('click', function(e){
  if (e.target.classList.contains('modal-overlay')) {
    e.target.classList.remove('open');
  }
  if (e.target.classList.contains('sheet-overlay')) {
    e.target.classList.remove('open');
    const sheetId = e.target.id.replace('Overlay','');
    const s = document.getElementById(sheetId);
    if (s) s.classList.remove('open');
  }
});

// ESC closes modals/sheets
document.addEventListener('keydown', function(e){
  if (e.key === 'Escape') {
    document.querySelectorAll('.modal-overlay.open, .sheet.open, .sheet-overlay.open').forEach(el => el.classList.remove('open'));
  }
});
})();
"""

ADMIN_JS_DASHBOARD = r"""
(function(){
'use strict';
const state = {
  filter: new URLSearchParams(location.search).get('filter') || 'all',
  search: '',
  timer: null,
};

const grid = document.getElementById('userGrid');
const searchInput = document.getElementById('searchInput');
if (searchInput) {
  searchInput.addEventListener('input', function(e){
    state.search = e.target.value.trim();
    clearTimeout(state.timer);
    state.timer = setTimeout(load, 300);
  });
}

document.querySelectorAll('[data-filter]').forEach(chip => {
  chip.addEventListener('click', function(){
    document.querySelectorAll('[data-filter]').forEach(c => c.classList.remove('active'));
    chip.classList.add('active');
    state.filter = chip.dataset.filter;
    load();
  });
});

function statusBadge(s){
  const map = {online:'Online', idle:'Ausente', offline:'Offline'};
  return '<span class="badge badge-'+s+'"><span class="badge-dot"></span>'+(map[s]||'Offline')+'</span>';
}

function escapeHtml(s){
  return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

async function load(){
  if (!grid) return;
  const params = new URLSearchParams({filter: state.filter, q: state.search});
  const data = await api('/api/users?' + params.toString());
  if (!data || !data.users) return;

  if (data.stats) {
    const update = (id, val) => { const el = document.getElementById(id); if (el && el.textContent !== String(val)) el.textContent = val; };
    update('kpi-total', data.stats.total);
    update('kpi-online', data.stats.online);
    update('kpi-vips', data.stats.vips);
    update('kpi-locked', data.stats.locked);
  }

  if (data.users.length === 0) {
    grid.innerHTML = '<div class="empty" style="grid-column:1/-1"><p>Nenhum usuário encontrado</p></div>';
    return;
  }

  grid.innerHTML = data.users.map(u => `
    <div class="user-card ${u.status}" onclick="location.href='/chat/${encodeURIComponent(u.id)}'">
      <div class="user-card-head">
        <span class="uid">${escapeHtml(u.id_short)}</span>
      </div>
      <div class="user-badges">
        ${statusBadge(u.status)}
        ${u.is_vip ? '<span class="badge badge-vip"><span class="badge-dot"></span>VIP</span>' : ''}
        ${u.is_locked ? '<span class="badge badge-locked">LOCK</span>' : ''}
        ${u.is_fav ? '<span class="badge badge-fav">★</span>' : ''}
      </div>
      <div class="preview">${u.preview ? escapeHtml(u.preview) : '<span class="text-3">sem mensagens</span>'}</div>
      <div class="meta">
        <span><b>${u.total_messages}</b> msg</span>
        <span>${escapeHtml(u.last_ago)}</span>
      </div>
    </div>
  `).join('');
}

// Initial load
load();

// Auto-refresh every 30s when tab visible
let refreshTimer;
function startRefresh(){
  refreshTimer = setInterval(load, 60000);
}
document.addEventListener('visibilitychange', function(){
  if (document.hidden) clearInterval(refreshTimer);
  else { load(); startRefresh(); }
});
startRefresh();

// Manual refresh
const refreshBtn = document.getElementById('refreshBtn');
if (refreshBtn) refreshBtn.addEventListener('click', load);
})();
"""

# ========================= STATIC ASSET ROUTES =========================

def _cached_response(body, mime):
    resp = make_response(body)
    resp.headers['Content-Type'] = mime
    resp.headers['Cache-Control'] = 'public, max-age=86400'
    return resp

@app.route("/admin/static/admin.css")
def serve_css():
    return _cached_response(ADMIN_CSS, 'text/css; charset=utf-8')

@app.route("/admin/static/admin.js")
def serve_js():
    return _cached_response(ADMIN_JS_COMMON, 'application/javascript; charset=utf-8')

@app.route("/admin/static/dashboard.js")
def serve_dashboard_js():
    return _cached_response(ADMIN_JS_DASHBOARD, 'application/javascript; charset=utf-8')

# ========================= TEMPLATES =========================

def render_sidebar(active):
    unread = get_unread_count()
    pix_count = len(get_pix_pending())
    def nav(href, key, ico, label, badge=None):
        cls = "nav-item active" if active == key else "nav-item"
        b = f'<span class="nav-item-badge">{badge}</span>' if badge else ''
        return f'<a href="{href}" class="{cls}">{icon(ico)}<span>{label}</span>{b}</a>'
    return f"""
<div class="sidebar-overlay" id="sidebarOverlay" onclick="toggleSidebar()"></div>
<aside class="sidebar" id="sidebar">
  <div class="sidebar-head">
    <span class="sidebar-dot"></span>
    <div class="sidebar-brand">Sophia<span>admin v6</span></div>
  </div>
  <nav class="sidebar-nav">
    {nav('/dashboard','dashboard','home','Dashboard')}
    {nav('/analytics','analytics','chart','Analytics')}
    {nav('/broadcast','broadcast','megaphone','Broadcast')}
    {nav('/financeiro','financeiro','money','Financeiro', pix_count if pix_count else None)}
    {nav('/galeria','galeria','image','Galeria')}
    {nav('/favoritos','favoritos','star','Favoritos')}
    {nav('/alertas','alertas','bell','Alertas', unread if unread else None)}
    {nav('/logs','logs','log','Logs')}
    {nav('/exportar','exportar','download','Exportar')}
    {nav('/config','config','settings','Configurações')}
  </nav>
  <div class="sidebar-foot">
    <a href="/logout" class="nav-item">{icon('logout')}<span>Sair</span></a>
  </div>
</aside>
"""

def render_topbar(title):
    unread = get_unread_count()
    badge = f'<span class="nav-item-badge" style="position:absolute;top:2px;right:2px;min-width:14px;padding:0 3px">{unread}</span>' if unread else ''
    return f"""
<header class="topbar">
  <button class="menu-btn" onclick="toggleSidebar()" aria-label="Menu">{icon('menu', 18)}</button>
  <h1 class="topbar-title">{title}</h1>
  <div class="topbar-actions">
    <a href="/alertas" class="btn btn-icon btn-ghost" style="position:relative" aria-label="Alertas">{icon('bell', 16)}{badge}</a>
    <button class="btn btn-icon btn-ghost" onclick="toggleTheme()" aria-label="Tema" data-theme-icon>{icon('moon', 16)}</button>
  </div>
</header>
"""

def render_page(title, content, active_page="dashboard", extra_head="", extra_js=""):
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
  <meta name="theme-color" content="#0a0a0a">
  <title>{html.escape(title)} · Sophia</title>
  <link rel="stylesheet" href="/admin/static/admin.css">
  {extra_head}
</head>
<body>
  <div class="layout">
    {render_sidebar(active_page)}
    <div class="main">
      {render_topbar(title)}
      {content}
    </div>
  </div>
  <div class="toast" id="toast"></div>
  <script src="/admin/static/admin.js"></script>
  {extra_js}
  <script>
    (function(){{
      const isLight = document.body.classList.contains('light');
      document.querySelectorAll('[data-theme-icon]').forEach(el => {{
        if (isLight) el.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="100%" height="100%"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>';
      }});
    }})();
  </script>
</body>
</html>"""

# ========================= ROUTES: AUTH =========================

@app.route("/")
def home():
    return redirect("/dashboard" if auth_required() else "/login")

@app.route("/login", methods=["GET","POST"])
def login():
    error = None
    if request.method == "POST":
        if request.form.get("password","").strip() == ADMIN_PASSWORD:
            session["authenticated"] = True
            session.permanent = True
            log_admin_action("LOGIN", "Admin logou")
            return redirect("/dashboard")
        error = "Senha incorreta"
    err_html = f'<div class="alert-banner danger">{error}</div>' if error else ''
    return f"""<!DOCTYPE html>
<html lang="pt-BR"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Login · Sophia</title>
<link rel="stylesheet" href="/admin/static/admin.css">
</head><body>
<div class="login-page">
  <div class="login-card">
    <div class="login-brand">
      <h1>Sophia Admin</h1>
      <p>v6 · sign in to continue</p>
    </div>
    {err_html}
    <form method="post">
      <div class="form-group">
        <label class="form-label">Senha</label>
        <input type="password" name="password" class="form-input" placeholder="••••••••" required autofocus>
      </div>
      <button type="submit" class="btn btn-primary btn-lg btn-full">Entrar</button>
    </form>
  </div>
</div>
</body></html>"""

@app.route("/logout")
def logout():
    log_admin_action("LOGOUT", "Admin deslogou")
    session.clear()
    return redirect("/login")

# ========================= API: DASHBOARD DATA =========================

def get_dashboard_users_fast(filter_type="all", q=""):
    """Carrega o dashboard sem varrer mensagens de todos os usuários.

    O fluxo antigo chamava get_user_stats(uid) para cada usuário e lia até 100
    mensagens de cada chatlog antes de mostrar somente 50 cards. Aqui usamos
    pipeline para buscar dados leves de todos os usuários e só depois lemos o
    chatlog dos 50 usuários que realmente aparecem na tela.
    """
    if not check_redis():
        return {
            "users": [],
            "stats": {"total": 0, "vips": 0, "online": 0, "idle": 0, "locked": 0}
        }

    all_uids = get_all_users()
    favorites = set(get_favorites())
    today = date.today()
    now = datetime.now()

    stats = {
        "total": len(all_uids),
        "vips": 0,
        "online": 0,
        "idle": 0,
        "locked": 0,
    }

    if not all_uids:
        return {"users": [], "stats": stats}

    pipe = redis_client.pipeline()
    for uid in all_uids:
        pipe.get(f"vip:{uid}")
        pipe.get(f"count:{uid}:{today}")
        pipe.get(f"last_activity:{uid}")

    try:
        results = pipe.execute()
    except Exception as e:
        logger.error(f"Erro ao carregar dashboard: {e}")
        return {"users": [], "stats": stats}

    rows = []

    for i, uid in enumerate(all_uids):
        vip_raw, count_raw, activity_raw = results[i * 3:i * 3 + 3]

        is_vip = False
        if vip_raw:
            try:
                is_vip = datetime.fromisoformat(vip_raw) > now
            except Exception:
                pass

        try:
            today_count = int(count_raw or 0)
        except Exception:
            today_count = 0

        is_locked = today_count >= 15 and not is_vip

        last_activity = None
        status = "offline"
        if activity_raw:
            try:
                last_activity = datetime.fromisoformat(activity_raw)
                diff_min = (now - last_activity).total_seconds() / 60
                if diff_min < ONLINE_THRESHOLD:
                    status = "online"
                elif diff_min < IDLE_THRESHOLD:
                    status = "idle"
            except Exception:
                pass

        if is_vip:
            stats["vips"] += 1
        if is_locked:
            stats["locked"] += 1
        if status == "online":
            stats["online"] += 1
        elif status == "idle":
            stats["idle"] += 1

        if q and q not in uid.lower():
            continue
        if filter_type == "vip" and not is_vip:
            continue
        if filter_type == "online" and status != "online":
            continue
        if filter_type == "idle" and status != "idle":
            continue
        if filter_type == "locked" and not is_locked:
            continue
        if filter_type == "favorites" and uid not in favorites:
            continue

        rows.append({
            "id": uid,
            "id_short": uid[:20] + ("…" if len(uid) > 20 else ""),
            "status": status,
            "is_vip": is_vip,
            "is_locked": is_locked,
            "is_fav": uid in favorites,
            "last_activity": last_activity,
            "total_messages": 0,
            "preview": None,
            "last_ago": format_time_ago(last_activity),
        })

    rows.sort(key=lambda x: x["last_activity"] or datetime.min, reverse=True)
    rows = rows[:50]

    # Só busca mensagens dos cards que serão exibidos.
    if rows:
        pipe = redis_client.pipeline()
        for user in rows:
            pipe.lrange(f"chatlog:{user['id']}", -100, -1)
        try:
            chatlogs = pipe.execute()
        except Exception as e:
            logger.error(f"Erro ao carregar previews do dashboard: {e}")
            chatlogs = [[] for _ in rows]
    else:
        chatlogs = []

    for user, logs in zip(rows, chatlogs):
        messages = []
        last_user_message = None
        seen = set()

        for log in logs:
            msg = parse_chat_message(log)
            if not msg:
                continue
            k = f"{msg['role']}:{msg['time']}:{msg['text'][:20]}"
            if k in seen:
                continue
            seen.add(k)
            messages.append(msg)
            if msg["role"] == "user":
                last_user_message = msg["text"]

        user["total_messages"] = len(messages)
        if last_user_message:
            user["preview"] = last_user_message[:60] + "…" if len(last_user_message) > 60 else last_user_message
        user.pop("last_activity", None)

    return {"users": rows, "stats": stats}


@app.route("/api/users")
def api_users():
    if not auth_required():
        return jsonify({"error": "unauthorized"}), 401

    filter_type = request.args.get("filter", "all")
    q = request.args.get("q", "").strip().lower()

    return jsonify(get_dashboard_users_fast(filter_type, q))


# ========================= DASHBOARD =========================

@app.route("/dashboard")
def dashboard():
    if not auth_required(): return redirect("/login")
    initial_filter = request.args.get('filter','all')
    initial_q = request.args.get('q','').strip()

    def chip(key, label):
        cls = "chip active" if key == initial_filter else "chip"
        return f'<button class="{cls}" data-filter="{key}">{label}</button>'

    skel = ''.join([
        '<div class="user-card offline">'
        '<div class="user-card-head"><span class="skel" style="width:120px"></span></div>'
        '<div class="user-badges"><span class="skel" style="width:60px"></span></div>'
        '<div class="preview"><span class="skel" style="width:90%"></span></div>'
        '<div class="meta"><span class="skel" style="width:50px"></span><span class="skel" style="width:40px"></span></div>'
        '</div>'
    ] * 6)

    content = f"""
<main class="container">
  <section class="dashboard-hero">
    <div class="hero-content">
      <div>
        <div class="hero-kicker">{icon('bolt', 13)} Painel em tempo real</div>
        <h2 class="hero-title">Operação Sophia <span>ao vivo</span></h2>
        <p class="hero-subtitle">Acompanhe usuários, conversas, VIPs e travas com uma interface mais clara, visual e pronta para decisão rápida.</p>
      </div>
      <div class="hero-actions">
        <span class="live-pill">Atualização automática</span>
        <button class="btn btn-primary" id="refreshBtn" type="button">{icon('refresh', 14)} Atualizar agora</button>
      </div>
    </div>
  </section>

  <div class="kpi-grid">
    <article class="kpi info"><div class="kpi-label">Total</div><div class="kpi-value mono" id="kpi-total"><span class="skel">000</span></div><div class="kpi-change">usuários no bot</div></article>
    <article class="kpi success"><div class="kpi-label">Online</div><div class="kpi-value mono" id="kpi-online"><span class="skel">00</span></div><div class="kpi-change">ativos agora</div></article>
    <article class="kpi warn"><div class="kpi-label">VIPs</div><div class="kpi-value mono" id="kpi-vips"><span class="skel">00</span></div><div class="kpi-change">assinantes ativos</div></article>
    <article class="kpi danger"><div class="kpi-label">Travados</div><div class="kpi-value mono" id="kpi-locked"><span class="skel">00</span></div><div class="kpi-change">no limite diário</div></article>
  </div>

  <div class="search-wrap">
    {icon('search', 16, 'search-icon')}
    <input id="searchInput" type="text" class="search-input" placeholder="Buscar por ID de usuário…" value="{html.escape(initial_q)}">
  </div>

  <div class="chips">
    {chip('all','Todos')}
    {chip('online','Online')}
    {chip('vip','VIPs')}
    {chip('locked','Travados')}
    {chip('favorites','Favoritos')}
  </div>

  <div class="user-grid" id="userGrid">
    {skel}
  </div>
</main>
"""
    extra_js = '<script src="/admin/static/dashboard.js"></script>'
    return render_page("Dashboard", content, "dashboard", extra_js=extra_js)

# ========================= ANALYTICS =========================

@app.route("/analytics")
def analytics():
    if not auth_required(): return redirect("/login")
    stats_data = get_stats_range(7)
    all_users = get_all_users()
    total_users = len(all_users)
    vip_count = 0
    total_msgs = 0

    # Versão otimizada: conta VIPs e tamanho dos chatlogs em pipeline.
    # Evita chamar get_user_stats(uid) para todos os usuários.
    if all_users and check_redis():
        pipe = redis_client.pipeline()
        for uid in all_users:
            pipe.get(f"vip:{uid}")
            pipe.llen(f"chatlog:{uid}")
        try:
            results = pipe.execute()
            now = datetime.now()
            for i in range(0, len(results), 2):
                vip_raw, msg_count = results[i], results[i + 1]
                if vip_raw:
                    try:
                        if datetime.fromisoformat(vip_raw) > now:
                            vip_count += 1
                    except Exception:
                        pass
                try:
                    total_msgs += int(msg_count or 0)
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"Erro analytics pipeline: {e}")

    conversion = (vip_count / total_users * 100) if total_users > 0 else 0
    labels = [s["date"][-5:] for s in stats_data]
    vips_data = [s.get("vips_activated", 0) for s in stats_data]
    msgs_data = [s.get("messages", 0) for s in stats_data]

    content = f"""
<main class="container">
  <div class="kpi-grid">
    <article class="kpi info"><div class="kpi-label">Total Users</div><div class="kpi-value mono">{total_users}</div><div class="kpi-change">cadastrados</div></article>
    <article class="kpi warn"><div class="kpi-label">VIPs</div><div class="kpi-value mono">{vip_count}</div><div class="kpi-change">ativos</div></article>
    <article class="kpi accent"><div class="kpi-label">Conversão</div><div class="kpi-value mono">{conversion:.1f}%</div><div class="kpi-change">users → VIP</div></article>
    <article class="kpi success"><div class="kpi-label">Mensagens</div><div class="kpi-value mono">{total_msgs}</div><div class="kpi-change">total trocadas</div></article>
  </div>

  <div class="charts-grid">
    <div class="card">
      <div class="card-head"><h3 class="card-title">VIPs ativados · 7 dias</h3></div>
      <div class="chart-wrap"><canvas id="vipsChart"></canvas></div>
    </div>
    <div class="card">
      <div class="card-head"><h3 class="card-title">Mensagens por dia</h3></div>
      <div class="chart-wrap"><canvas id="msgsChart"></canvas></div>
    </div>
  </div>
</main>
"""
    extra_head = '<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js" defer></script>'
    extra_js = f"""<script>
window.addEventListener('load', function(){{
  if (typeof Chart === 'undefined') return setTimeout(arguments.callee, 100);
  Chart.defaults.color = getComputedStyle(document.body).getPropertyValue('--text-2').trim();
  Chart.defaults.borderColor = getComputedStyle(document.body).getPropertyValue('--border').trim();
  Chart.defaults.font.family = '-apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif';
  Chart.defaults.font.size = 11;
  Chart.defaults.plugins.legend.display = false;
  Chart.defaults.plugins.tooltip.backgroundColor = '#1c1c1c';
  Chart.defaults.plugins.tooltip.borderColor = '#2e2e2e';
  Chart.defaults.plugins.tooltip.borderWidth = 1;
  Chart.defaults.plugins.tooltip.padding = 10;
  Chart.defaults.plugins.tooltip.cornerRadius = 6;
  Chart.defaults.plugins.tooltip.displayColors = false;

  const labels = {json.dumps(labels)};
  const baseScales = {{y:{{beginAtZero:true,grid:{{color:'#1c1c1c'}},ticks:{{padding:6}}}},x:{{grid:{{display:false}},ticks:{{padding:6}}}}}};

  new Chart(document.getElementById('vipsChart'), {{
    type:'bar',
    data:{{labels:labels, datasets:[{{data:{json.dumps(vips_data)}, backgroundColor:'rgba(255,90,31,.8)', borderRadius:4, borderSkipped:false}}]}},
    options:{{responsive:true, maintainAspectRatio:false, scales:baseScales}}
  }});
  new Chart(document.getElementById('msgsChart'), {{
    type:'line',
    data:{{labels:labels, datasets:[{{data:{json.dumps(msgs_data)}, borderColor:'#16a34a', backgroundColor:'rgba(22,163,74,.12)', tension:.35, fill:true, borderWidth:2, pointRadius:3, pointBackgroundColor:'#16a34a'}}]}},
    options:{{responsive:true, maintainAspectRatio:false, scales:baseScales}}
  }});
}});
</script>"""
    return render_page("Analytics", content, "analytics", extra_head=extra_head, extra_js=extra_js)


# ========================= BROADCAST =========================

@app.route("/broadcast", methods=["GET","POST"])
def broadcast():
    if not auth_required(): return redirect("/login")
    result_html = ""
    if request.method == "POST":
        message = request.form.get("message","").strip()
        filter_vip    = request.form.get("filter_vip")    == "on"
        filter_free   = request.form.get("filter_free")   == "on"
        filter_active = request.form.get("filter_active") == "on"
        filter_locked = request.form.get("filter_locked") == "on"
        add_pix = request.form.get("add_pix_button") == "on"
        photo_file = request.files.get("photo")
        photo_data = photo_file.read() if (photo_file and photo_file.filename) else None
        if message or photo_data:
            all_uids = get_all_users()
            sent = failed = skipped = 0
            msg_hash = get_message_hash((message or "") + str(bool(photo_data))) if filter_locked else None
            for uid in all_uids:
                s = get_user_stats(uid)
                if filter_vip and not s["is_vip"]: continue
                if filter_free and s["is_vip"]: continue
                if filter_active:
                    if not s["last_activity"]: continue
                    hours = (datetime.now() - s["last_activity"]).total_seconds() / 3600
                    if hours > 72: continue
                if filter_locked:
                    if not s["is_locked"]: continue
                    if has_received_broadcast_while_locked(uid, msg_hash):
                        skipped += 1
                        continue
                if add_pix:
                    success, _ = (send_telegram_photo_with_button(uid, photo_data, message) if photo_data else send_telegram_message_with_button(uid, message))
                else:
                    success, _ = (send_telegram_photo(uid, photo_data, message) if photo_data else send_telegram_message(uid, message))
                if success:
                    sent += 1
                    if filter_locked:
                        mark_broadcast_sent_to_locked(uid, msg_hash)
                else:
                    failed += 1
            filters = []
            if filter_vip: filters.append("VIP")
            if filter_free: filters.append("FREE")
            if filter_active: filters.append("Ativos 72h")
            if filter_locked: filters.append("Travados")
            msg_preview = "[FOTO]" if photo_data else message
            save_broadcast_history(msg_preview, ", ".join(filters) or "Todos", sent, failed)
            log_admin_action("BROADCAST", f"Enviado para {sent} usuários")
            extra = f' · {skipped} ignorados (duplicado)' if (filter_locked and skipped > 0) else ''
            result_html = f'<div class="alert-banner success"><strong>Enviado.</strong> <span>{sent} entregues · {failed} falhas{extra}</span></div>'

    history = get_broadcast_history()
    history_rows = ""
    for h in history[:10]:
        dt = datetime.fromisoformat(h["created_at"]).strftime("%d/%m %H:%M")
        history_rows += f"""<tr><td class="mono">{dt}</td><td>{html.escape(h['message'][:60])}</td><td>{html.escape(h.get('filters','Todos'))}</td><td><b>{h['sent']}</b></td></tr>"""
    if not history_rows:
        history_rows = '<tr><td colspan="4" class="empty" style="padding:20px">Nenhum broadcast ainda</td></tr>'

    all_users = get_all_users()
    locked_count = sum(1 for u in all_users if get_user_stats(u)["is_locked"])
    photos = get_gallery()
    gallery_items = ""
    for p in photos[:12]:
        gallery_items += f'<div class="gallery-item" onclick="pickGalleryPhoto(\'{p["id"]}\',{json.dumps(p["name"])})"><img src="data:image/jpeg;base64,{p["thumbnail"]}" alt=""></div>'
    if not gallery_items:
        gallery_items = '<p class="text-3" style="grid-column:1/-1;text-align:center;padding:20px">Galeria vazia</p>'

    content = f"""
<main class="container">
  {result_html}
  <div class="card">
    <div class="card-head"><h3 class="card-title">{icon('megaphone',15)}Enviar broadcast</h3></div>
    <form method="post" enctype="multipart/form-data" id="bcastForm">
      <div class="photo-preview" id="photoPreview" style="margin-bottom:12px;border-radius:var(--radius-sm);border:1px solid var(--border)">
        <img id="photoPreviewImg"><span class="photo-preview-name" id="photoPreviewName"></span>
        <button type="button" class="photo-preview-remove" onclick="removeBcastPhoto()">{icon('x',14)}</button>
      </div>
      <div class="form-group">
        <label class="form-label">Foto (opcional)</label>
        <div style="display:flex;gap:8px;flex-wrap:wrap">
          <input type="file" name="photo" id="bcastPhoto" accept="image/*" class="form-input" style="flex:1;min-width:200px" onchange="previewBcastPhoto(event)">
          <button type="button" class="btn" onclick="openModal('galleryModal')">{icon('image',14)} Galeria</button>
        </div>
      </div>
      <div class="form-group">
        <label class="form-label">Mensagem (ou legenda da foto)</label>
        <textarea name="message" class="form-textarea" placeholder="Digite a mensagem…"></textarea>
      </div>
      <div class="form-group">
        <label class="form-label">Pagamento</label>
        <label class="filter-opt success">
          <input type="checkbox" name="add_pix_button" checked>
          <div><strong>Adicionar botão PAGAR COM PIX</strong><small>Botão interativo embaixo da mensagem</small></div>
        </label>
      </div>
      <div class="form-group">
        <label class="form-label">Filtros</label>
        <label class="filter-opt"><input type="checkbox" name="filter_vip"><div><strong>Apenas VIPs</strong></div></label>
        <label class="filter-opt"><input type="checkbox" name="filter_free"><div><strong>Apenas FREE</strong></div></label>
        <label class="filter-opt"><input type="checkbox" name="filter_active" checked><div><strong>Ativos nas últimas 72h</strong></div></label>
        <label class="filter-opt danger">
          <input type="checkbox" name="filter_locked">
          <div><strong>Apenas travados ({locked_count})</strong><small>Sistema inteligente: não reenvia para quem já recebeu no mesmo travamento</small></div>
        </label>
      </div>
      <button type="submit" class="btn btn-primary btn-lg btn-full">{icon('send',14)} Enviar broadcast</button>
    </form>
  </div>

  <div class="card">
    <div class="card-head"><h3 class="card-title">{icon('log',15)}Histórico</h3></div>
    <div class="table-wrap">
      <table>
        <thead><tr><th>Data</th><th>Mensagem</th><th>Filtros</th><th>Enviados</th></tr></thead>
        <tbody>{history_rows}</tbody>
      </table>
    </div>
  </div>
</main>

<div class="modal-overlay" id="galleryModal">
  <div class="modal">
    <div class="modal-head"><h3>Selecionar da galeria</h3><button class="modal-close" onclick="closeModal('galleryModal')">{icon('x',14)}</button></div>
    <div class="modal-body"><div class="gallery-grid">{gallery_items}</div></div>
  </div>
</div>
"""
    extra_js = """<script>
function previewBcastPhoto(e){
  const f = e.target.files[0]; if(!f) return;
  const r = new FileReader();
  r.onload = (ev) => {
    document.getElementById('photoPreviewImg').src = ev.target.result;
    document.getElementById('photoPreviewName').textContent = f.name;
    document.getElementById('photoPreview').classList.add('active');
  };
  r.readAsDataURL(f);
}
function removeBcastPhoto(){
  document.getElementById('photoPreview').classList.remove('active');
  document.getElementById('bcastPhoto').value = '';
}
async function pickGalleryPhoto(id, name){
  const data = await api('/api/galeria/get/'+id);
  if (!data || !data.success) return;
  const bs = atob(data.photo);
  const arr = new Uint8Array(bs.length);
  for (let i=0; i<bs.length; i++) arr[i] = bs.charCodeAt(i);
  const blob = new Blob([arr], {type:'image/jpeg'});
  const file = new File([blob], name, {type:'image/jpeg'});
  const dt = new DataTransfer();
  dt.items.add(file);
  document.getElementById('bcastPhoto').files = dt.files;
  document.getElementById('photoPreviewImg').src = 'data:image/jpeg;base64,'+data.photo;
  document.getElementById('photoPreviewName').textContent = name;
  document.getElementById('photoPreview').classList.add('active');
  closeModal('galleryModal');
  toast('Foto selecionada', 'success');
}
</script>"""
    return render_page("Broadcast", content, "broadcast", extra_js=extra_js)

# ========================= FINANCEIRO =========================

@app.route("/financeiro")
def financeiro():
    if not auth_required(): return redirect("/login")
    pending = get_pix_pending()
    all_users = get_all_users()
    vip_count = 0
    if all_users and check_redis():
        pipe = redis_client.pipeline()
        for uid in all_users:
            pipe.get(f"vip:{uid}")
        try:
            now = datetime.now()
            for vip_raw in pipe.execute():
                if vip_raw:
                    try:
                        if datetime.fromisoformat(vip_raw) > now:
                            vip_count += 1
                    except Exception:
                        pass
        except Exception as e:
            logger.error(f"Erro financeiro VIP count: {e}")
    config = get_config()
    preco = float(config.get("preco_pix","14.99"))
    receita = vip_count * preco

    pending_html = ""
    for p in pending:
        dt = datetime.fromisoformat(p["created_at"]).strftime("%d/%m %H:%M")
        pending_html += f"""
<div class="card" style="border-left:3px solid var(--warn)">
  <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap">
    <div style="min-width:0;flex:1">
      <strong style="font-size:14px">{html.escape(p.get('username') or p['uid'])}</strong>
      <div class="text-3" style="font-size:11.5px;margin-top:2px">ID {html.escape(p['uid'])} · R$ {p.get('amount', preco)} · {dt}</div>
    </div>
    <div style="display:flex;gap:6px">
      <button class="btn btn-success btn-sm" onclick="aprovarPix('{html.escape(p['uid'])}')">{icon('check',12)} Aprovar</button>
      <button class="btn btn-danger btn-sm" onclick="rejeitarPix('{html.escape(p['uid'])}')">{icon('x',12)} Rejeitar</button>
    </div>
  </div>
</div>"""
    if not pending_html:
        pending_html = '<div class="empty"><p>Nenhum comprovante pendente</p></div>'

    content = f"""
<main class="container">
  <div class="kpi-grid">
    <article class="kpi warn"><div class="kpi-label">Pendentes</div><div class="kpi-value mono">{len(pending)}</div><div class="kpi-change">aguardando análise</div></article>
    <article class="kpi success"><div class="kpi-label">VIPs ativos</div><div class="kpi-value mono">{vip_count}</div><div class="kpi-change">assinantes</div></article>
    <article class="kpi accent"><div class="kpi-label">Receita est.</div><div class="kpi-value mono">R$ {receita:.0f}</div><div class="kpi-change">VIPs × R$ {preco:.2f}</div></article>
  </div>

  <div class="section-head"><h2>Comprovantes pendentes</h2></div>
  {pending_html}
</main>
<script>
async function aprovarPix(uid){{
  if (!confirm('Aprovar VIP para '+uid+'?')) return;
  const r = await api('/api/pix/aprovar/'+encodeURIComponent(uid),{{method:'POST'}});
  if (r && r.success) {{ toast('VIP ativado','success'); setTimeout(()=>location.reload(),900); }}
  else toast('Erro: '+((r&&r.error)||'falha'),'error');
}}
async function rejeitarPix(uid){{
  if (!confirm('Rejeitar PIX de '+uid+'?')) return;
  const r = await api('/api/pix/rejeitar/'+encodeURIComponent(uid),{{method:'POST'}});
  if (r && r.success) {{ toast('Rejeitado','success'); setTimeout(()=>location.reload(),700); }}
}}
</script>
"""
    return render_page("Financeiro", content, "financeiro")

# ========================= GALERIA =========================

@app.route("/galeria", methods=["GET","POST"])
def galeria():
    if not auth_required(): return redirect("/login")
    if request.method == "POST" and "photo" in request.files:
        photo = request.files["photo"]
        if photo.filename:
            name = request.form.get("name", photo.filename)
            data = base64.b64encode(photo.read()).decode('utf-8')
            add_to_gallery(name, data)
            return redirect("/galeria")
    photos = get_gallery()
    items = ""
    for p in photos:
        items += f"""<div class="gallery-item" onclick="toast('{html.escape(p['name'])}','success')">
<img src="data:image/jpeg;base64,{p['thumbnail']}" alt="">
<button class="gallery-del" onclick="event.stopPropagation();deletePhoto('{p['id']}')">{icon('trash',13)}</button>
</div>"""
    if not items:
        items = '<p class="text-3" style="grid-column:1/-1;text-align:center;padding:24px">Nenhuma foto na galeria ainda</p>'
    content = f"""
<main class="container">
  <div class="card">
    <div class="card-head"><h3 class="card-title">{icon('camera',15)}Upload de foto</h3></div>
    <form method="post" enctype="multipart/form-data">
      <div class="form-row cols-2">
        <div class="form-group"><label class="form-label">Nome (opcional)</label><input type="text" name="name" class="form-input" placeholder="Foto 01"></div>
        <div class="form-group"><label class="form-label">Arquivo</label><input type="file" name="photo" accept="image/*" class="form-input" required></div>
      </div>
      <button type="submit" class="btn btn-primary">{icon('camera',14)} Enviar foto</button>
    </form>
  </div>
  <div class="card">
    <div class="card-head"><h3 class="card-title">{icon('image',15)}Galeria ({len(photos)} fotos)</h3></div>
    <div class="gallery-grid">{items}</div>
  </div>
</main>
<script>
async function deletePhoto(id){{
  if (!confirm('Excluir esta foto?')) return;
  const r = await api('/api/galeria/delete/'+id, {{method:'POST'}});
  if (r && r.success) {{ toast('Foto excluída','success'); setTimeout(()=>location.reload(),500); }}
}}
</script>
"""
    return render_page("Galeria", content, "galeria")

# ========================= FAVORITOS =========================

@app.route("/favoritos")
def favoritos():
    if not auth_required(): return redirect("/login")
    fav_ids = get_favorites()
    cards = ""
    for uid in fav_ids:
        s = get_user_stats(uid)
        status_map = {"online":"badge-online","idle":"badge-idle","offline":"badge-offline"}
        status_text_map = {"online":"Online","idle":"Ausente","offline":"Offline"}
        cards += f"""<div class="user-card {s['status']}" onclick="location.href='/chat/{html.escape(uid)}'">
<div class="user-card-head"><span class="uid">★ {html.escape(uid[:20])}</span></div>
<div class="user-badges">
  <span class="badge {status_map.get(s['status'],'badge-offline')}"><span class="badge-dot"></span>{status_text_map.get(s['status'],'Offline')}</span>
  {'<span class="badge badge-vip"><span class="badge-dot"></span>VIP</span>' if s['is_vip'] else ''}
</div>
<div class="meta"><span><b>{s['total_messages']}</b> msg</span><span>{format_time_ago(s['last_activity'])}</span></div>
</div>"""
    if not cards:
        cards = '<div class="empty" style="grid-column:1/-1"><p>Nenhum favorito ainda</p><p class="text-3" style="margin-top:6px;font-size:12px">Marque usuários no chat para acesso rápido</p></div>'
    content = f"""
<main class="container">
  <div class="card">
    <div class="card-head"><h3 class="card-title">{icon('star',15)}Usuários favoritos ({len(fav_ids)})</h3></div>
    <p class="text-3" style="font-size:12.5px">Marque usuários como favoritos na tela de chat para acesso rápido.</p>
  </div>
  <div class="user-grid">{cards}</div>
</main>
"""
    return render_page("Favoritos", content, "favoritos")

# ========================= ALERTAS =========================

@app.route("/alertas")
def alertas():
    if not auth_required(): return redirect("/login")
    alerts = get_alerts()
    rows = ""
    for a in alerts:
        dt = datetime.fromisoformat(a["created_at"]).strftime("%d/%m %H:%M")
        ico_map = {"pix":"money","new_user":"home","vip_expiring":"bell","error":"x"}
        rows += f"""<div class="alert-row {'unread' if not a['read'] else ''}" onclick="markRead('{a['id']}')">
{icon(ico_map.get(a['type'],'bell'),18)}
<div class="body"><div class="msg">{html.escape(a['message'])}</div><div class="time">{dt}</div></div>
</div>"""
    if not rows:
        rows = '<div class="empty"><p>Sem alertas no momento</p></div>'
    content = f"""
<main class="container">
  <div class="card">
    <div class="card-head">
      <h3 class="card-title">{icon('bell',15)}Alertas</h3>
      <button class="btn btn-sm" onclick="markAllRead()">{icon('check',12)} Marcar todos como lidos</button>
    </div>
    <div style="margin:0 -18px">{rows}</div>
  </div>
</main>
<script>
async function markRead(id){{ await api('/api/alert/read/'+id, {{method:'POST'}}); }}
async function markAllRead(){{
  await api('/api/alert/read-all', {{method:'POST'}});
  toast('Todos marcados como lidos','success');
  setTimeout(()=>location.reload(),500);
}}
</script>
"""
    return render_page("Alertas", content, "alertas")

# ========================= LOGS =========================

@app.route("/logs")
def logs():
    if not auth_required(): return redirect("/login")
    admin_logs = get_admin_logs(50)
    rows = ""
    for log in admin_logs:
        dt = datetime.fromisoformat(log["timestamp"]).strftime("%d/%m %H:%M:%S")
        rows += f"""<tr><td class="mono">{dt}</td><td><b>{html.escape(log['action'])}</b></td><td>{html.escape(log.get('details','') or '—')}</td><td class="mono">{html.escape(str(log.get('uid','') or '—'))}</td></tr>"""
    if not rows:
        rows = '<tr><td colspan="4" class="empty" style="padding:20px">Nenhum log</td></tr>'
    content = f"""
<main class="container">
  <div class="card">
    <div class="card-head"><h3 class="card-title">{icon('log',15)}Logs de ações (últimos 50)</h3></div>
    <div class="table-wrap">
      <table>
        <thead><tr><th>Data</th><th>Ação</th><th>Detalhes</th><th>Usuário</th></tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </div>
  </div>
</main>
"""
    return render_page("Logs", content, "logs")

# ========================= CONFIG =========================

@app.route("/config", methods=["GET","POST"])
def config_page():
    if not auth_required(): return redirect("/login")
    config = get_config()
    saved = False
    if request.method == "POST":
        try: config["limite_diario"] = int(request.form.get("limite_diario", 15))
        except: pass
        try: config["dias_vip"] = int(request.form.get("dias_vip", 15))
        except: pass
        config["preco_pix"] = request.form.get("preco_pix", "14.99")
        config["preco_pix_desconto"] = request.form.get("preco_pix_desconto", "9.99")
        config["pix_key"] = request.form.get("pix_key", "")
        config["pix_payment_url"] = request.form.get("pix_payment_url", "")
        config["msg_limite"] = request.form.get("msg_limite", "")
        config["msg_vip_ativado"] = request.form.get("msg_vip_ativado", "")
        save_config(config)
        saved = True

    saved_banner = '<div class="alert-banner success"><strong>Configurações salvas.</strong></div>' if saved else ''

    content = f"""
<main class="container">
  {saved_banner}
  <form method="post">
    <div class="card">
      <div class="card-head"><h3 class="card-title">{icon('money',15)}Preços e limites</h3></div>
      <div class="form-row cols-2">
        <div class="form-group"><label class="form-label">Limite diário</label><input type="number" name="limite_diario" class="form-input" value="{config['limite_diario']}"></div>
        <div class="form-group"><label class="form-label">Dias VIP</label><input type="number" name="dias_vip" class="form-input" value="{config['dias_vip']}"></div>
        <div class="form-group"><label class="form-label">Preço PIX (R$)</label><input type="text" name="preco_pix" class="form-input" value="{html.escape(config['preco_pix'])}"></div>
        <div class="form-group"><label class="form-label">Preço com desconto (R$)</label><input type="text" name="preco_pix_desconto" class="form-input" value="{html.escape(config['preco_pix_desconto'])}"></div>
      </div>
      <div class="form-group"><label class="form-label">Chave PIX</label><input type="text" name="pix_key" class="form-input" value="{html.escape(config.get('pix_key',''))}"></div>
      <div class="form-group"><label class="form-label">Link de pagamento PIX</label><input type="text" name="pix_payment_url" class="form-input" value="{html.escape(config.get('pix_payment_url',''))}"></div>
    </div>

    <div class="card">
      <div class="card-head"><h3 class="card-title">{icon('edit',15)}Mensagens</h3></div>
      <div class="form-group"><label class="form-label">Mensagem de limite atingido</label><textarea name="msg_limite" class="form-textarea">{html.escape(config.get('msg_limite',''))}</textarea></div>
      <div class="form-group"><label class="form-label">Mensagem de VIP ativado</label><textarea name="msg_vip_ativado" class="form-textarea">{html.escape(config.get('msg_vip_ativado',''))}</textarea></div>
    </div>

    <button type="submit" class="btn btn-primary btn-lg btn-full">{icon('check',14)} Salvar configurações</button>
  </form>
</main>
"""
    return render_page("Configurações", content, "config")

# ========================= CHAT =========================

@app.route("/chat/<uid>")
def chat_view(uid):
    if not auth_required(): return redirect("/login")
    messages = get_user_messages(uid)
    stats = get_user_stats(uid)
    is_fav = is_favorite(uid)
    notes = get_user_notes(uid)
    tags = get_user_tags(uid)
    is_takeover = is_takeover_active(uid)

    msgs_html = ""
    for m in messages:
        role = m["role"]; text = html.escape(m["text"]); t = m["time"]
        if role == "user":
            msgs_html += f'<div class="msg msg-user"><div class="msg-label">User</div>{text}<div class="msg-time">{t}</div></div>'
        elif role == "assistant":
            msgs_html += f'<div class="msg msg-sophia"><div class="msg-label">Sophia</div>{text}<div class="msg-time">{t}</div></div>'
        elif role == "admin":
            msgs_html += f'<div class="msg msg-admin"><div class="msg-label">Admin</div>{text}<div class="msg-time">{t}</div></div>'
        else:
            msgs_html += f'<div class="msg msg-system">{text}</div>'
    if not msgs_html:
        msgs_html = '<div class="empty"><p>Nenhuma mensagem nesta conversa</p></div>'

    status_map = {"online":"Online","idle":"Ausente","offline":"Offline"}
    status_text = status_map.get(stats['status'], 'Offline')
    vip_text = (' · VIP até ' + stats['vip_until']) if stats['vip_until'] else ''
    locked_text = ' · Travado' if stats['is_locked'] else ''

    tags_html = "".join([f'<span class="badge badge-tag">{html.escape(t)}</span>' for t in tags]) or '<span class="text-3">Nenhuma tag</span>'
    takeover_banner = '<div class="takeover-banner">VOCÊ ESTÁ NO CONTROLE — IA pausada</div>' if is_takeover else ''
    fav_cls = 'on' if is_fav else ''
    tk_cls = 'on' if is_takeover else ''
    uid_esc = html.escape(uid)

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#0a0a0a">
<title>Chat · {html.escape(uid[:12])}</title>
<link rel="stylesheet" href="/admin/static/admin.css">
</head>
<body>
<div class="chat-shell">
  <header class="chat-topbar">
    <a class="chat-back" href="/dashboard">{icon('arrow_left',18)}</a>
    <div class="chat-user" onclick="openModal('userModal')">
      <div class="chat-user-name">{'★ ' if is_fav else ''}{html.escape(uid[:25])}</div>
      <div class="chat-user-status">{status_text}{vip_text}{locked_text}</div>
    </div>
    <div class="chat-tools">
      <button class="chat-tool {tk_cls}" onclick="toggleTakeover()" aria-label="Takeover">{icon('pause' if is_takeover else 'play',18)}</button>
      <button class="chat-tool {fav_cls}" onclick="toggleFav()" aria-label="Favorito">{icon('star',18)}</button>
      <button class="chat-tool" onclick="location.reload()" aria-label="Atualizar">{icon('refresh',18)}</button>
    </div>
  </header>

{takeover_banner}

  <div class="chat-messages" id="chatMessages">{msgs_html}</div>

  <div class="quick-replies">
    <button class="quick-reply" onclick="setMsg('Oi amor 💕')">Oi amor</button>
    <button class="quick-reply" onclick="setMsg('Tudo bem? 🥰')">Tudo bem?</button>
    <button class="quick-reply" onclick="setMsg('Senti sua falta... 🥺')">Senti falta</button>
    <button class="quick-reply" onclick="setMsg('Te adoro 💖')">Te adoro</button>
    <button class="quick-reply" onclick="setMsg('💖 Seu VIP foi ativado!')">VIP ativado</button>
  </div>

  <div class="photo-preview" id="photoPreview">
    <img id="photoPreviewImg"><span class="photo-preview-name" id="photoPreviewName"></span>
    <button class="photo-preview-remove" onclick="removePhoto()">{icon('x',14)}</button>
  </div>

  <div class="chat-input-bar">
    <button class="chat-attach" onclick="document.getElementById('photoInput').click()" aria-label="Anexar foto">{icon('camera',18)}</button>
    <input type="file" id="photoInput" accept="image/*" style="display:none" onchange="previewPhoto(event)">
    <input type="text" class="chat-input" id="messageInput" placeholder="Mensagem…">
    <button class="chat-send" onclick="sendMessage()" aria-label="Enviar">{icon('send',18)}</button>
  </div>
</div>

<button class="fab" onclick="toggleSheet('actionsSheet')">{icon('bolt',22)}</button>

<div class="sheet-overlay" id="actionsSheetOverlay" onclick="toggleSheet('actionsSheet')"></div>
<div class="sheet" id="actionsSheet">
  <div class="sheet-handle"></div>
  <div class="sheet-title">Ações</div>
  <div class="action-grid">
    <button class="action-btn warn" onclick="doAction('setvip')">{icon('star',22)}<span>Ativar VIP</span></button>
    <button class="action-btn success" onclick="doAction('bonus5')">{icon('bolt',22)}<span>+5 msgs</span></button>
    <button class="action-btn success" onclick="doAction('bonus10')">{icon('bolt',22)}<span>+10 msgs</span></button>
    <button class="action-btn" onclick="doAction('reset')">{icon('refresh',22)}<span>Resetar</span></button>
    <button class="action-btn" onclick="doAction('clearmemory')">{icon('trash',22)}<span>Limpar mem.</span></button>
    <button class="action-btn" onclick="doAction('unpause')">{icon('play',22)}<span>Despausar</span></button>
    <button class="action-btn danger" onclick="doAction('blacklist')">{icon('x',22)}<span>Bloquear</span></button>
    <button class="action-btn" onclick="openModal('notesModal');toggleSheet('actionsSheet')">{icon('edit',22)}<span>Notas</span></button>
    <button class="action-btn" onclick="openModal('tagsModal');toggleSheet('actionsSheet')">{icon('filter',22)}<span>Tags</span></button>
  </div>
</div>

<div class="modal-overlay" id="userModal">
  <div class="modal">
    <div class="modal-head"><h3>Detalhes do usuário</h3><button class="modal-close" onclick="closeModal('userModal')">{icon('x',14)}</button></div>
    <div class="modal-body">
      <p><strong>ID:</strong> <span class="mono">{html.escape(uid)}</span></p>
      <p style="margin-top:6px"><strong>Status:</strong> {status_text}</p>
      <p style="margin-top:6px"><strong>Mensagens:</strong> <span class="mono">{stats['total_messages']}</span></p>
      <p style="margin-top:6px"><strong>Hoje:</strong> <span class="mono">{stats['today_count']}/15</span></p>
      <p style="margin-top:6px"><strong>VIP:</strong> {('até ' + stats['vip_until']) if stats['vip_until'] else 'Não'}</p>
      <p style="margin-top:10px"><strong>Tags:</strong></p>
      <div style="display:flex;flex-wrap:wrap;gap:4px;margin-top:6px">{tags_html}</div>
    </div>
  </div>
</div>

<div class="modal-overlay" id="notesModal">
  <div class="modal">
    <div class="modal-head"><h3>Notas</h3><button class="modal-close" onclick="closeModal('notesModal')">{icon('x',14)}</button></div>
    <div class="modal-body"><textarea id="notesText" class="form-textarea" placeholder="Notas sobre este usuário…" style="min-height:150px">{html.escape(notes)}</textarea></div>
    <div class="modal-foot"><button class="btn" onclick="closeModal('notesModal')">Cancelar</button><button class="btn btn-primary" onclick="saveNotes()">{icon('check',12)} Salvar</button></div>
  </div>
</div>

<div class="modal-overlay" id="tagsModal">
  <div class="modal">
    <div class="modal-head"><h3>Tags</h3><button class="modal-close" onclick="closeModal('tagsModal')">{icon('x',14)}</button></div>
    <div class="modal-body">
      <div style="display:flex;flex-wrap:wrap;gap:4px;margin-bottom:12px">{tags_html}</div>
      <div style="display:flex;gap:6px"><input type="text" id="newTag" class="form-input" placeholder="Nova tag…"><button class="btn btn-primary" onclick="addTag()">+</button></div>
    </div>
  </div>
</div>

<div class="toast" id="toast"></div>
<script src="/admin/static/admin.js"></script>
<script>
const UID = {json.dumps(uid)};
const chatMessages = document.getElementById('chatMessages');
if (chatMessages) chatMessages.scrollTop = chatMessages.scrollHeight;
let selectedPhoto = null;

function setMsg(t){{ const i = document.getElementById('messageInput'); i.value = t; i.focus(); }}
function previewPhoto(e){{
  const f = e.target.files[0]; if (!f) return;
  selectedPhoto = f;
  const r = new FileReader();
  r.onload = (ev) => {{
    document.getElementById('photoPreviewImg').src = ev.target.result;
    document.getElementById('photoPreviewName').textContent = f.name;
    document.getElementById('photoPreview').classList.add('active');
  }};
  r.readAsDataURL(f);
}}
function removePhoto(){{
  selectedPhoto = null;
  document.getElementById('photoPreview').classList.remove('active');
  document.getElementById('photoInput').value = '';
}}
async function sendMessage(){{
  const inp = document.getElementById('messageInput');
  const msg = inp.value.trim();
  if (selectedPhoto) {{
    const fd = new FormData();
    fd.append('photo', selectedPhoto);
    fd.append('caption', msg);
    toast('Enviando…');
    const r = await api('/send-photo/' + encodeURIComponent(UID), {{method:'POST', body:fd}});
    if (r && r.success) {{ toast('Foto enviada','success'); removePhoto(); inp.value=''; setTimeout(()=>location.reload(),900); }}
    else toast('Erro: ' + ((r&&r.error)||'falha'),'error');
  }} else if (msg) {{
    const r = await api('/send/' + encodeURIComponent(UID), {{
      method:'POST',
      headers:{{'Content-Type':'application/x-www-form-urlencoded'}},
      body:'message=' + encodeURIComponent(msg)
    }});
    if (r && r.success) {{ toast('Enviado','success'); inp.value=''; setTimeout(()=>location.reload(),700); }}
    else toast('Erro: ' + ((r&&r.error)||'falha'),'error');
  }}
}}
async function doAction(action){{
  if (action === 'blacklist' && !confirm('Bloquear este usuário?')) return;
  toggleSheet('actionsSheet');
  toast('Executando…');
  const r = await api('/action/' + encodeURIComponent(UID) + '/' + action, {{method:'POST'}});
  if (r && r.success) {{ toast(r.message || 'Ok','success'); setTimeout(()=>location.reload(),1100); }}
  else toast('Erro: ' + ((r&&r.error)||'falha'),'error');
}}
async function toggleTakeover(){{
  const r = await api('/api/takeover/' + encodeURIComponent(UID), {{method:'POST'}});
  if (r && r.success) {{
    toast(r.active ? 'Controle assumido — IA pausada' : 'Controle liberado — IA reativada','success');
    setTimeout(()=>location.reload(),600);
  }}
}}
async function toggleFav(){{
  const r = await api('/api/favorite/' + encodeURIComponent(UID), {{method:'POST'}});
  if (r) {{
    toast(r.is_favorite ? 'Adicionado aos favoritos' : 'Removido dos favoritos','success');
    setTimeout(()=>location.reload(),500);
  }}
}}
async function saveNotes(){{
  const notes = document.getElementById('notesText').value;
  const r = await api('/api/notes/' + encodeURIComponent(UID), {{
    method:'POST', headers:{{'Content-Type':'application/json'}}, body: JSON.stringify({{notes}})
  }});
  if (r && r.success) {{ toast('Notas salvas','success'); closeModal('notesModal'); }}
}}
async function addTag(){{
  const tag = document.getElementById('newTag').value.trim();
  if (!tag) return;
  const r = await api('/api/tags/' + encodeURIComponent(UID), {{
    method:'POST', headers:{{'Content-Type':'application/json'}}, body: JSON.stringify({{tag}})
  }});
  if (r && r.success) {{ toast('Tag adicionada','success'); setTimeout(()=>location.reload(),500); }}
}}
document.getElementById('messageInput').addEventListener('keypress', e => {{ if (e.key === 'Enter') sendMessage(); }});
</script>
</body>
</html>"""

# ========================= EXPORTAR =========================

@app.route("/exportar-conversas")
def exportar_conversas():
    if not auth_required(): return redirect("/login")
    all_users = get_all_users()
    export_data = []
    for uid in all_users:
        s = get_user_stats(uid)
        messages = get_user_messages(uid)
        user_msgs = [m for m in messages if m['role'] == 'user']
        sophia_msgs = [m for m in messages if m['role'] == 'assistant']
        export_data.append({
            "uid": uid, "is_vip": s['is_vip'], "total_msgs": len(messages),
            "user_msgs": len(user_msgs), "sophia_msgs": len(sophia_msgs),
            "status": s['status'], "is_locked": s['is_locked'],
            "conversa": [{"role": m['role'], "text": m['text'], "time": m['time']} for m in messages]
        })
    export_data.sort(key=lambda x: x['total_msgs'], reverse=True)
    return Response(json.dumps(export_data, ensure_ascii=False, indent=2),
                    mimetype='application/json',
                    headers={"Content-Disposition": "attachment; filename=conversas_sophia.json"})

@app.route("/exportar-txt")
def exportar_txt():
    if not auth_required(): return redirect("/login")
    all_users = get_all_users()
    now = datetime.now()
    limite_24h = now - timedelta(hours=24)
    out = ["=" * 60, "RELATORIO DE CONVERSAS - SOPHIA BOT", "*** ULTIMAS 24 HORAS ***",
           f"Data: {now.strftime('%d/%m/%Y %H:%M')}",
           f"Periodo: {limite_24h.strftime('%d/%m/%Y %H:%M')} ate agora",
           "=" * 60, ""]
    users_24h = 0
    for uid in all_users:
        s = get_user_stats(uid); messages = get_user_messages(uid)
        if not messages: continue
        if not s['last_activity'] or s['last_activity'] < limite_24h: continue
        users_24h += 1
        user_msgs = len([m for m in messages if m['role'] == 'user'])
        out += ["-" * 60, f"USUARIO: {uid}", f"VIP: {'Sim' if s['is_vip'] else 'Nao'}",
                f"Msgs do usuario: {user_msgs}", f"Total msgs: {len(messages)}",
                f"Travado: {'Sim' if s['is_locked'] else 'Nao'}",
                f"Ultima atividade: {s['last_activity'].strftime('%d/%m/%Y %H:%M')}",
                "-" * 60, ""]
        for m in messages:
            label = {'user':'USER','assistant':'SOPHIA','admin':'ADMIN','system':'SISTEMA','action':'ACAO','info':'INFO'}.get(m['role'], m['role'].upper())
            out += [f"[{m['time']}] {label}:", f"  {m['text']}", ""]
        out.append("")
    vips = sum(1 for u in all_users if get_user_stats(u)['is_vip'])
    out += ["=" * 60, "RESUMO - ULTIMAS 24 HORAS",
            f"Usuarios ativos (24h): {users_24h}",
            f"Total usuarios geral: {len(all_users)}",
            f"VIPs: {vips}", "=" * 60]
    return Response("\n".join(out), mimetype='text/plain; charset=utf-8',
                    headers={"Content-Disposition": f"attachment; filename=conversas_24h_{now.strftime('%d%m%Y_%H%M')}.txt"})

@app.route("/exportar", methods=["GET","POST"])
def exportar_periodo():
    if not auth_required(): return redirect("/login")
    if request.method == "POST":
        di_str = request.form.get("data_inicio")
        df_str = request.form.get("data_fim")
        try:
            di = datetime.strptime(di_str, "%Y-%m-%d") if di_str else None
            df = datetime.strptime(df_str, "%Y-%m-%d") if df_str else None
            if df: df = df.replace(hour=23, minute=59, second=59)
            all_users = get_all_users()
            linhas = []
            tot_u = 0; tot_m = 0
            linhas += ["=" * 80, "EXPORTAÇÃO DE CONVERSAS - SOPHIA BOT",
                       f"Período: {di_str or 'Início'} até {df_str or 'Hoje'}",
                       f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}",
                       "=" * 80, ""]
            for uid in all_users:
                last_str = redis_client.get(f"last_activity:{uid}")
                if not last_str: continue
                try: last_act = datetime.fromisoformat(last_str)
                except: continue
                if di and last_act < di: continue
                if df and last_act > df: continue
                messages = get_user_messages(uid)
                if not messages: continue
                msgs_filt = []
                for m in messages:
                    try:
                        mt = datetime.strptime(m['time'], "%H:%M:%S").replace(year=last_act.year, month=last_act.month, day=last_act.day)
                        if di and mt < di: continue
                        if df and mt > df: continue
                        msgs_filt.append(m)
                    except:
                        msgs_filt.append(m)
                if not msgs_filt: continue
                tot_u += 1; tot_m += len(msgs_filt)
                s = get_user_stats(uid)
                linhas += ["-" * 80, f"USUÁRIO: {uid}",
                           f"Status: {s['status'].upper()}",
                           f"É VIP: {'SIM' if s['is_vip'] else 'NÃO'}",
                           f"Travado hoje: {'SIM' if s['is_locked'] else 'NÃO'}",
                           f"Total mensagens no período: {len(msgs_filt)}",
                           f"Última atividade: {format_time_ago(s['last_activity'])}",
                           "-" * 80, ""]
                for m in msgs_filt:
                    label = {'user':'USER     ','assistant':'SOPHIA   ','admin':'ADMIN    ','system':'SISTEMA  ','action':'AÇÃO     '}.get(m['role'], m['role'].upper().ljust(9))
                    linhas += [f"[{m['time']}] {label}: {m['text']}", ""]
                linhas.append("\n")
            linhas += ["=" * 80, "RESUMO",
                       f"Período: {di_str or '—'} → {df_str or 'Hoje'}",
                       f"Total usuários: {tot_u}", f"Total mensagens: {tot_m}",
                       "=" * 80]
            content_txt = "\n".join(linhas)
            fname = f"conversas_{di_str or 'all'}_ate_{df_str or 'hoje'}_{datetime.now().strftime('%Y%m%d_%H%M')}.txt"
            return send_file(BytesIO(content_txt.encode('utf-8')), mimetype='text/plain; charset=utf-8',
                             as_attachment=True, download_name=fname)
        except Exception as e:
            return f"<h2 style='color:red'>Erro: {html.escape(str(e))}</h2><br><a href='/exportar'>Voltar</a>"

    hoje = date.today().isoformat()
    sete_dias = (date.today() - timedelta(days=7)).isoformat()
    content = f"""
<main class="container">
  <div class="card">
    <div class="card-head"><h3 class="card-title">{icon('download',15)}Exportar conversas por período</h3></div>
    <form method="post">
      <div class="form-row cols-2">
        <div class="form-group"><label class="form-label">Data inicial</label><input type="date" name="data_inicio" class="form-input" value="{sete_dias}"><div class="form-hint">Em branco = desde o início</div></div>
        <div class="form-group"><label class="form-label">Data final (inclusive)</label><input type="date" name="data_fim" class="form-input" value="{hoje}" max="{hoje}"><div class="form-hint">Em branco = hoje</div></div>
      </div>
      <button type="submit" class="btn btn-primary btn-lg btn-full">{icon('download',14)} Gerar e baixar TXT</button>
      <p class="form-hint" style="text-align:center;margin-top:12px">Inclui conversas com atividade no período escolhido.</p>
    </form>
  </div>

  <div class="card">
    <div class="card-head"><h3 class="card-title">{icon('download',15)}Exportações rápidas</h3></div>
    <div style="display:flex;gap:8px;flex-wrap:wrap">
      <a href="/exportar-txt" class="btn">{icon('download',14)} Últimas 24h (TXT)</a>
      <a href="/exportar-conversas" class="btn">{icon('download',14)} Todos (JSON)</a>
    </div>
  </div>
</main>
"""
    return render_page("Exportar", content, "exportar")

# ========================= API ROUTES =========================

@app.route("/send/<uid>", methods=["POST"])
def api_send(uid):
    if not auth_required(): return jsonify({"error":"unauthorized"}), 401
    message = request.form.get("message","").strip()
    if not message: return jsonify({"success":False,"error":"Mensagem vazia"})
    success, msg = send_telegram_message(uid, message)
    if success:
        save_admin_message(uid, message)
        log_admin_action("MESSAGE_SENT", message[:50], uid)
    return jsonify({"success": success, "message": msg})

@app.route("/send-photo/<uid>", methods=["POST"])
def api_send_photo(uid):
    if not auth_required(): return jsonify({"error":"unauthorized"}), 401
    photo = request.files.get("photo")
    caption = request.form.get("caption","").strip()
    if not photo or not photo.filename:
        return jsonify({"success":False,"error":"Foto não enviada"})
    success, msg = send_telegram_photo(uid, photo.read(), caption)
    if success:
        save_admin_message(uid, f"[FOTO] {caption}" if caption else "[FOTO]")
        log_admin_action("PHOTO_SENT", caption[:40] if caption else "foto", uid)
    return jsonify({"success": success, "message": msg})

@app.route("/action/<uid>/<action>", methods=["POST"])
def api_action(uid, action):
    if not auth_required(): return jsonify({"error":"unauthorized"}), 401
    actions = {
        "setvip":      lambda: activate_vip(uid, get_config().get("dias_vip", 15)),
        "bonus5":      lambda: give_bonus_messages(uid, 5),
        "bonus10":     lambda: give_bonus_messages(uid, 10),
        "reset":       lambda: reset_daily_limit(uid),
        "clearmemory": lambda: clear_user_memory(uid),
        "unpause":     lambda: unpause_user(uid),
        "blacklist":   lambda: blacklist_user(uid),
        "unblacklist": lambda: unblacklist_user(uid),
    }
    if action not in actions:
        return jsonify({"success":False,"error":"Ação inválida"})
    success, message = actions[action]()
    if success:
        if action == "setvip":
            try:
                send_telegram_message(uid, get_config().get("msg_vip_ativado","").replace("{dias}", str(get_config().get("dias_vip",15))))
            except: pass
        elif action == "bonus5":
            try: send_telegram_message(uid, "🎁 Ganhou +5 mensagens, amor 💕")
            except: pass
        elif action == "bonus10":
            try: send_telegram_message(uid, "🎁 Ganhou +10 mensagens, amor 💕")
            except: pass
    return jsonify({"success": success, "message": message})

@app.route("/api/favorite/<uid>", methods=["POST"])
def api_favorite(uid):
    if not auth_required(): return jsonify({"error":"unauthorized"}), 401
    result = toggle_favorite(uid)
    return jsonify({"success": True, "is_favorite": result})

@app.route("/api/notes/<uid>", methods=["POST"])
def api_notes(uid):
    if not auth_required(): return jsonify({"error":"unauthorized"}), 401
    data = request.get_json() or {}
    notes = data.get("notes","")
    success = save_user_notes(uid, notes)
    return jsonify({"success": success})

@app.route("/api/tags/<uid>", methods=["POST"])
def api_tags(uid):
    if not auth_required(): return jsonify({"error":"unauthorized"}), 401
    data = request.get_json() or {}
    tag = data.get("tag","").strip()
    if not tag: return jsonify({"success":False,"error":"Tag vazia"})
    success = add_user_tag(uid, tag)
    return jsonify({"success": success})

@app.route("/api/pix/aprovar/<uid>", methods=["POST"])
def api_pix_aprovar(uid):
    if not auth_required(): return jsonify({"error":"unauthorized"}), 401
    days = get_config().get("dias_vip", 15)
    success, message = activate_vip(uid, days)
    if success:
        remove_pix_pending(uid)
        log_admin_action("PIX_APPROVED", f"VIP {days}d", uid)
    return jsonify({"success": success, "message": message})

@app.route("/api/pix/rejeitar/<uid>", methods=["POST"])
def api_pix_rejeitar(uid):
    if not auth_required(): return jsonify({"error":"unauthorized"}), 401
    remove_pix_pending(uid)
    log_admin_action("PIX_REJECTED", "", uid)
    try:
        send_telegram_message(uid, "❌ Comprovante PIX inválido. Verifique e envie novamente, amor.")
    except: pass
    return jsonify({"success": True})

@app.route("/api/galeria/delete/<photo_id>", methods=["POST"])
def api_galeria_delete(photo_id):
    if not auth_required(): return jsonify({"error":"unauthorized"}), 401
    success = remove_from_gallery(photo_id)
    return jsonify({"success": success})

@app.route("/api/galeria/get/<photo_id>")
def api_galeria_get(photo_id):
    if not auth_required(): return jsonify({"error":"unauthorized"}), 401
    photos = get_gallery()
    for p in photos:
        if p["id"] == photo_id:
            return jsonify({"success": True, "photo": p["data"], "name": p["name"]})
    return jsonify({"success": False, "error": "Não encontrada"})

@app.route("/api/alert/read/<alert_id>", methods=["POST"])
def api_alert_read(alert_id):
    if not auth_required(): return jsonify({"error":"unauthorized"}), 401
    success = mark_alert_read(alert_id)
    return jsonify({"success": success})

@app.route("/api/alert/read-all", methods=["POST"])
def api_alert_read_all():
    if not auth_required(): return jsonify({"error":"unauthorized"}), 401
    success = mark_all_alerts_read()
    return jsonify({"success": success})

@app.route("/api/takeover/<uid>", methods=["POST"])
def api_takeover(uid):
    if not auth_required(): return jsonify({"error":"unauthorized"}), 401
    if is_takeover_active(uid):
        end_takeover(uid)
        return jsonify({"success": True, "active": False})
    start_takeover(uid)
    return jsonify({"success": True, "active": True})

@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "redis": check_redis(),
        "version": "6.0",
        "timestamp": datetime.now().isoformat()
    })

# ========================= STARTUP =========================

if __name__ == "__main__":
    logger.info(f"Sophia Admin v6 starting on port {PORT}")
    app.run(host="0.0.0.0", port=PORT, debug=False)
