#!/usr/bin/env python3
"""
🎯 Sophia Admin Panel v4 - Mobile-First UX
NOVIDADES v4:
- Design mobile-first com menu hamburguer
- Dark mode toggle
- FAB (Floating Action Button)
- Bottom sheet para ações
- Busca de usuários
- Pull-to-refresh visual
- Animações suaves
- Touch-friendly (botões maiores)
- Notificações melhoradas
"""

import os
import json
import redis
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timedelta
from flask import Flask, request, redirect, session, jsonify
import logging
import time
import html

# ================= CONFIG =================
REDIS_URL = os.environ.get("REDIS_URL", "redis://default:DcddfJOHLXZdFPjEhRjHeodNgdtrsevl@shuttle.proxy.rlwy.net:12241")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8528168785:AAFfgtaB0vEagd1cdfZ3hWDyL9PKFZrmRjk")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")
SECRET_KEY = os.environ.get("SECRET_KEY", "sophia-secret-" + str(int(time.time())))
PORT = int(os.environ.get("PORT", 8081))

ONLINE_THRESHOLD = 20
IDLE_THRESHOLD = 40
OFFLINE_THRESHOLD = 60
RECENT_THRESHOLD = 24

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
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=2)

# ================= TELEGRAM API =================
def send_telegram_message(chat_id, text):
    if not TELEGRAM_TOKEN:
        return False, "Token não configurado"
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    
    try:
        data = json.dumps({
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }).encode('utf-8')
        
        req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'}, method='POST')
        
        with urllib.request.urlopen(req, timeout=10) as response:
            result = json.loads(response.read().decode('utf-8'))
            return (True, "Enviado") if result.get("ok") else (False, result.get("description", "Erro"))
                
    except urllib.error.HTTPError as e:
        try:
            error_body = json.loads(e.read().decode('utf-8'))
            return False, error_body.get("description", str(e))
        except:
            return False, str(e)
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
            'Content-Type': f'multipart/form-data; boundary={boundary}',
            'Content-Length': len(body)
        }, method='POST')
        
        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode('utf-8'))
            return (True, "Foto enviada") if result.get("ok") else (False, result.get("description", "Erro"))
                
    except Exception as e:
        return False, str(e)

def save_admin_message(uid, text):
    try:
        timestamp = datetime.now().strftime("%H:%M:%S")
        redis_client.rpush(f"chatlog:{uid}", f"[{timestamp}] ADMIN: {text[:100]}")
        redis_client.ltrim(f"chatlog:{uid}", -200, -1)
        return True
    except:
        return False

# ================= AÇÕES ADMIN =================
def activate_vip(uid, days=15):
    try:
        vip_until = datetime.now() + timedelta(days=days)
        redis_client.set(f"vip:{uid}", vip_until.isoformat())
        for key in ["pix_pending", "pix_clicked", "pix_interest", "flash_discount"]:
            redis_client.delete(f"{key}:{uid}")
        return True, f"VIP até {vip_until.strftime('%d/%m/%Y')}"
    except Exception as e:
        return False, str(e)

def reset_daily_limit(uid):
    try:
        from datetime import date
        redis_client.delete(f"count:{uid}:{date.today()}")
        return True, "Limite resetado"
    except Exception as e:
        return False, str(e)

def give_bonus_messages(uid, amount=5):
    try:
        current = int(redis_client.get(f"bonus:{uid}") or 0)
        redis_client.set(f"bonus:{uid}", current + amount)
        redis_client.expire(f"bonus:{uid}", 86400 * 7)
        return True, f"+{amount} msgs (total: {current + amount})"
    except Exception as e:
        return False, str(e)

def clear_user_memory(uid):
    try:
        redis_client.delete(f"memory:{uid}")
        return True, "Memória limpa"
    except Exception as e:
        return False, str(e)

def unpause_user(uid):
    try:
        redis_client.delete(f"paused:{uid}")
        redis_client.delete(f"ignored:{uid}")
        return True, "Gatilhos reativados"
    except Exception as e:
        return False, str(e)

def blacklist_user(uid):
    try:
        redis_client.sadd("blacklist", str(uid))
        return True, "Usuário bloqueado"
    except Exception as e:
        return False, str(e)

def unblacklist_user(uid):
    try:
        redis_client.srem("blacklist", str(uid))
        return True, "Usuário desbloqueado"
    except Exception as e:
        return False, str(e)

# ================= STYLES v4 - MOBILE FIRST =================
STYLES = """
<style>
:root {
    --primary: #667eea;
    --primary-dark: #5a67d8;
    --secondary: #764ba2;
    --success: #10b981;
    --warning: #f59e0b;
    --danger: #ef4444;
    --dark-bg: #1a1a2e;
    --dark-card: #16213e;
    --dark-text: #e4e4e7;
    --light-bg: #f0f2f5;
    --light-card: #ffffff;
    --light-text: #333333;
    --radius: 16px;
    --shadow: 0 4px 20px rgba(0,0,0,0.1);
    --shadow-lg: 0 10px 40px rgba(0,0,0,0.15);
}

* { margin: 0; padding: 0; box-sizing: border-box; }

body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: var(--light-bg);
    color: var(--light-text);
    min-height: 100vh;
    transition: all 0.3s ease;
    -webkit-tap-highlight-color: transparent;
}

body.dark {
    --light-bg: var(--dark-bg);
    --light-card: var(--dark-card);
    --light-text: var(--dark-text);
    background: var(--dark-bg);
    color: var(--dark-text);
}

/* ===== HEADER FIXO ===== */
.header {
    position: sticky;
    top: 0;
    z-index: 100;
    background: linear-gradient(135deg, var(--primary) 0%, var(--secondary) 100%);
    color: white;
    padding: 15px 20px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    box-shadow: var(--shadow-lg);
}

.header-left {
    display: flex;
    align-items: center;
    gap: 15px;
}

.header h1 {
    font-size: 18px;
    font-weight: 600;
}

.header-actions {
    display: flex;
    gap: 10px;
    align-items: center;
}

/* ===== MENU HAMBURGUER ===== */
.hamburger {
    display: none;
    flex-direction: column;
    gap: 5px;
    cursor: pointer;
    padding: 10px;
    margin: -10px;
}

.hamburger span {
    width: 24px;
    height: 3px;
    background: white;
    border-radius: 3px;
    transition: all 0.3s;
}

.hamburger.active span:nth-child(1) {
    transform: rotate(45deg) translate(5px, 5px);
}

.hamburger.active span:nth-child(2) {
    opacity: 0;
}

.hamburger.active span:nth-child(3) {
    transform: rotate(-45deg) translate(7px, -7px);
}

/* ===== DARK MODE TOGGLE ===== */
.theme-toggle {
    width: 50px;
    height: 28px;
    background: rgba(255,255,255,0.2);
    border-radius: 14px;
    position: relative;
    cursor: pointer;
    transition: all 0.3s;
}

.theme-toggle::after {
    content: '☀️';
    position: absolute;
    left: 3px;
    top: 2px;
    width: 24px;
    height: 24px;
    background: white;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 14px;
    transition: all 0.3s;
}

body.dark .theme-toggle::after {
    content: '🌙';
    left: 23px;
}

/* ===== CONTAINER ===== */
.container {
    max-width: 1400px;
    margin: 0 auto;
    padding: 15px;
}

/* ===== SEARCH BAR ===== */
.search-container {
    position: relative;
    margin-bottom: 15px;
}

.search-input {
    width: 100%;
    padding: 14px 20px 14px 50px;
    border: none;
    border-radius: var(--radius);
    background: var(--light-card);
    font-size: 16px;
    box-shadow: var(--shadow);
    transition: all 0.3s;
}

.search-input:focus {
    outline: none;
    box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.3);
}

.search-icon {
    position: absolute;
    left: 18px;
    top: 50%;
    transform: translateY(-50%);
    color: #999;
    font-size: 18px;
}

/* ===== STATS CARDS ===== */
.stats-scroll {
    display: flex;
    gap: 12px;
    overflow-x: auto;
    padding: 5px 0 15px;
    -webkit-overflow-scrolling: touch;
    scrollbar-width: none;
}

.stats-scroll::-webkit-scrollbar { display: none; }

.stat-card {
    flex: 0 0 auto;
    min-width: 130px;
    background: var(--light-card);
    padding: 15px;
    border-radius: var(--radius);
    box-shadow: var(--shadow);
    text-align: center;
}

.stat-number {
    font-size: 28px;
    font-weight: 700;
    background: linear-gradient(135deg, var(--primary), var(--secondary));
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}

.stat-label {
    font-size: 12px;
    color: #888;
    margin-top: 5px;
}

/* ===== FILTER CHIPS ===== */
.filter-chips {
    display: flex;
    gap: 8px;
    overflow-x: auto;
    padding: 10px 0;
    -webkit-overflow-scrolling: touch;
    scrollbar-width: none;
}

.filter-chips::-webkit-scrollbar { display: none; }

.chip {
    flex: 0 0 auto;
    padding: 10px 18px;
    background: var(--light-card);
    border-radius: 25px;
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
    box-shadow: var(--shadow);
    border: 2px solid transparent;
    white-space: nowrap;
}

.chip:active {
    transform: scale(0.95);
}

.chip.active {
    background: linear-gradient(135deg, var(--primary), var(--secondary));
    color: white;
}

/* ===== USER CARDS ===== */
.user-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
    gap: 15px;
    margin-top: 15px;
}

.user-card {
    background: var(--light-card);
    border-radius: var(--radius);
    padding: 18px;
    box-shadow: var(--shadow);
    cursor: pointer;
    transition: all 0.3s;
    border-left: 4px solid var(--primary);
    position: relative;
    overflow: hidden;
}

.user-card::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: linear-gradient(135deg, var(--primary), var(--secondary));
    opacity: 0;
    transition: opacity 0.3s;
}

.user-card:active {
    transform: scale(0.98);
}

.user-card:active::before {
    opacity: 0.05;
}

.user-card.online { border-left-color: var(--success); }
.user-card.idle { border-left-color: var(--warning); }
.user-card.offline { border-left-color: var(--danger); }

.user-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 10px;
}

.user-id {
    font-weight: 600;
    font-size: 15px;
    color: var(--primary);
    word-break: break-all;
}

.user-badges {
    display: flex;
    gap: 5px;
    flex-wrap: wrap;
    margin-top: 5px;
}

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

/* ===== CHAT VIEW ===== */
.chat-container {
    display: flex;
    flex-direction: column;
    height: calc(100vh - 60px);
    background: var(--light-bg);
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
    font-size: 20px;
}

.chat-user-info {
    flex: 1;
}

.chat-user-name {
    font-weight: 600;
    font-size: 16px;
}

.chat-user-status {
    font-size: 12px;
    color: #888;
}

.chat-messages {
    flex: 1;
    overflow-y: auto;
    padding: 15px;
    display: flex;
    flex-direction: column;
    gap: 10px;
    -webkit-overflow-scrolling: touch;
}

.message {
    max-width: 85%;
    padding: 12px 16px;
    border-radius: 18px;
    animation: slideUp 0.3s ease;
    position: relative;
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

.message-time {
    font-size: 10px;
    opacity: 0.7;
    margin-top: 5px;
}

.message-label {
    font-size: 10px;
    font-weight: 600;
    margin-bottom: 4px;
    opacity: 0.8;
}

/* ===== CHAT INPUT ===== */
.chat-input-area {
    background: var(--light-card);
    padding: 15px;
    box-shadow: 0 -4px 20px rgba(0,0,0,0.05);
}

.chat-input-row {
    display: flex;
    gap: 10px;
    align-items: flex-end;
}

.chat-input {
    flex: 1;
    padding: 14px 18px;
    border: 2px solid #e0e0e0;
    border-radius: 25px;
    font-size: 16px;
    resize: none;
    max-height: 120px;
    transition: all 0.3s;
}

.chat-input:focus {
    outline: none;
    border-color: var(--primary);
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
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.3s;
    flex-shrink: 0;
}

.send-btn:active {
    transform: scale(0.9);
}

/* ===== FLOATING ACTION BUTTON ===== */
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
    box-shadow: var(--shadow-lg);
    z-index: 90;
    transition: all 0.3s;
}

.fab:active {
    transform: scale(0.9);
}

.fab.open {
    transform: rotate(45deg);
}

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

.bottom-sheet-overlay.active {
    opacity: 1;
    visibility: visible;
}

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

.bottom-sheet.active {
    transform: translateY(0);
}

.bottom-sheet-handle {
    width: 40px;
    height: 4px;
    background: #ddd;
    border-radius: 2px;
    margin: 0 auto 20px;
}

.bottom-sheet-title {
    font-size: 18px;
    font-weight: 600;
    margin-bottom: 20px;
    text-align: center;
}

.action-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 15px;
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
    transition: all 0.2s;
    font-size: 13px;
    color: var(--light-text);
}

.action-btn:active {
    transform: scale(0.95);
    background: rgba(102, 126, 234, 0.1);
}

.action-btn .icon {
    font-size: 28px;
}

.action-btn.danger { color: var(--danger); }
.action-btn.success { color: var(--success); }
.action-btn.warning { color: var(--warning); }

/* ===== QUICK REPLIES ===== */
.quick-replies {
    display: flex;
    gap: 8px;
    overflow-x: auto;
    padding: 10px 0;
    -webkit-overflow-scrolling: touch;
}

.quick-reply {
    flex: 0 0 auto;
    padding: 10px 16px;
    background: var(--light-bg);
    border-radius: 20px;
    font-size: 13px;
    cursor: pointer;
    transition: all 0.2s;
    white-space: nowrap;
}

.quick-reply:active {
    background: var(--primary);
    color: white;
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
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
}

.photo-preview-container {
    display: none;
    padding: 10px;
    background: var(--light-bg);
    border-radius: var(--radius);
    margin-bottom: 10px;
}

.photo-preview-container.active {
    display: flex;
    align-items: center;
    gap: 10px;
}

.photo-preview-img {
    width: 60px;
    height: 60px;
    object-fit: cover;
    border-radius: 8px;
}

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
    transition: all 0.3s ease;
    white-space: nowrap;
}

.toast.show {
    transform: translateX(-50%) translateY(0);
    opacity: 1;
}

.toast.success { background: var(--success); }
.toast.error { background: var(--danger); }

/* ===== LOGIN ===== */
.login-page {
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    background: linear-gradient(135deg, var(--primary) 0%, var(--secondary) 100%);
    padding: 20px;
}

.login-card {
    background: white;
    padding: 40px 30px;
    border-radius: var(--radius);
    box-shadow: var(--shadow-lg);
    width: 100%;
    max-width: 380px;
}

.login-logo {
    text-align: center;
    margin-bottom: 30px;
}

.login-logo h1 {
    color: var(--primary);
    font-size: 28px;
}

.login-logo p {
    color: #888;
    font-size: 14px;
}

.form-group {
    margin-bottom: 20px;
}

.form-group label {
    display: block;
    margin-bottom: 8px;
    font-weight: 500;
    font-size: 14px;
}

.form-input {
    width: 100%;
    padding: 14px 18px;
    border: 2px solid #e0e0e0;
    border-radius: 12px;
    font-size: 16px;
    transition: all 0.3s;
}

.form-input:focus {
    outline: none;
    border-color: var(--primary);
}

.btn-primary {
    width: 100%;
    padding: 16px;
    background: linear-gradient(135deg, var(--primary), var(--secondary));
    color: white;
    border: none;
    border-radius: 12px;
    font-size: 16px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.3s;
}

.btn-primary:active {
    transform: scale(0.98);
}

.error-msg {
    background: #fee;
    color: var(--danger);
    padding: 12px;
    border-radius: 8px;
    margin-bottom: 20px;
    font-size: 14px;
}

/* ===== EMPTY STATE ===== */
.empty-state {
    text-align: center;
    padding: 60px 20px;
    color: #888;
}

.empty-state .icon {
    font-size: 60px;
    margin-bottom: 20px;
}

/* ===== PULL TO REFRESH ===== */
.ptr-indicator {
    text-align: center;
    padding: 20px;
    color: var(--primary);
    display: none;
}

.ptr-indicator.active {
    display: block;
}

/* ===== RESPONSIVE ===== */
@media (max-width: 768px) {
    .hamburger {
        display: flex;
    }
    
    .header h1 {
        font-size: 16px;
    }
    
    .user-grid {
        grid-template-columns: 1fr;
    }
    
    .stat-card {
        min-width: 110px;
        padding: 12px;
    }
    
    .stat-number {
        font-size: 24px;
    }
    
    .action-grid {
        grid-template-columns: repeat(3, 1fr);
        gap: 10px;
    }
    
    .action-btn {
        padding: 15px 8px;
        font-size: 11px;
    }
    
    .action-btn .icon {
        font-size: 24px;
    }
}

/* ===== SKELETON LOADING ===== */
.skeleton {
    background: linear-gradient(90deg, #f0f0f0 25%, #e0e0e0 50%, #f0f0f0 75%);
    background-size: 200% 100%;
    animation: skeleton-loading 1.5s infinite;
    border-radius: 8px;
}

@keyframes skeleton-loading {
    0% { background-position: 200% 0; }
    100% { background-position: -200% 0; }
}

/* ===== SCROLLBAR ===== */
::-webkit-scrollbar {
    width: 6px;
    height: 6px;
}

::-webkit-scrollbar-track {
    background: transparent;
}

::-webkit-scrollbar-thumb {
    background: rgba(0,0,0,0.2);
    border-radius: 3px;
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
    users = {}
    try:
        for key in redis_client.scan_iter("chatlog:*"):
            parts = key.split(":")
            if len(parts) > 1:
                users[parts[1]] = None
    except:
        pass
    return list(users.keys())

def get_user_messages(uid):
    if not check_redis():
        return []
    messages = []
    try:
        logs = redis_client.lrange(f"chatlog:{uid}", 0, -1)
        for log in logs:
            msg = parse_chat_message(log)
            if msg:
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
        "status": "offline", "is_vip": False, "is_locked": False
    }
    
    try:
        vip_until = redis_client.get(f"vip:{uid}")
        if vip_until:
            stats["is_vip"] = datetime.fromisoformat(vip_until) > datetime.now()
    except:
        pass
    
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
        error = "Senha incorreta"
    
    return f"""
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
        <title>Login - Sophia Admin</title>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
        {STYLES}
    </head>
    <body>
        <div class="login-page">
            <div class="login-card">
                <div class="login-logo">
                    <h1>🤖 Sophia AI</h1>
                    <p>Painel Administrativo v4.0</p>
                </div>
                {f'<div class="error-msg">{error}</div>' if error else ''}
                <form method="post">
                    <div class="form-group">
                        <label>Senha de Acesso</label>
                        <input type="password" name="password" class="form-input" placeholder="Digite a senha" required autofocus>
                    </div>
                    <button type="submit" class="btn-primary">
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
        return "<h1>Redis não conectado</h1>", 500
    
    filter_type = request.args.get('filter', 'all')
    search = request.args.get('q', '').strip()
    
    all_users = get_all_users()
    stats = get_global_stats()
    
    users_with_stats = [(uid, get_user_stats(uid)) for uid in all_users]
    
    # Filtros
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
        filtered.append((uid, s))
    
    filtered.sort(key=lambda x: x[1]['last_activity'] or datetime.min, reverse=True)
    
    users_html = ""
    for uid, s in filtered[:50]:  # Limita a 50
        status_badge = {"online": "badge-online", "idle": "badge-idle", "offline": "badge-offline"}.get(s['status'], "badge-offline")
        status_text = {"online": "Online", "idle": "Ausente", "offline": "Offline"}.get(s['status'], "Offline")
        
        users_html += f"""
        <div class="user-card {s['status']}" onclick="window.location.href='/chat/{uid}'">
            <div class="user-header">
                <div>
                    <div class="user-id">{uid[:20]}{'...' if len(uid) > 20 else ''}</div>
                    <div class="user-badges">
                        <span class="badge {status_badge}">{status_text}</span>
                        {'<span class="badge badge-vip">👑 VIP</span>' if s['is_vip'] else ''}
                        {'<span class="badge badge-locked">🔒</span>' if s['is_locked'] else ''}
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
    
    return f"""
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
        <title>Dashboard - Sophia Admin</title>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
        {STYLES}
    </head>
    <body>
        <header class="header">
            <div class="header-left">
                <div class="hamburger" onclick="toggleMenu()">
                    <span></span><span></span><span></span>
                </div>
                <h1>🤖 Sophia Admin</h1>
            </div>
            <div class="header-actions">
                <div class="theme-toggle" onclick="toggleTheme()"></div>
                <a href="/logout" style="color: white; font-size: 20px; padding: 10px;"><i class="fas fa-sign-out-alt"></i></a>
            </div>
        </header>
        
        <div class="container">
            <!-- Search -->
            <div class="search-container">
                <i class="fas fa-search search-icon"></i>
                <input type="text" class="search-input" placeholder="Buscar usuário por ID..." 
                       value="{html.escape(search)}" onkeyup="handleSearch(event)">
            </div>
            
            <!-- Stats -->
            <div class="stats-scroll">
                <div class="stat-card">
                    <div class="stat-number">{stats['total']}</div>
                    <div class="stat-label">👥 Total</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number" style="--primary: #10b981;">{stats['online']}</div>
                    <div class="stat-label">🟢 Online</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number" style="--primary: #f59e0b;">{stats['idle']}</div>
                    <div class="stat-label">🟡 Ausentes</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number" style="--primary: #ffd700;">{stats['vips']}</div>
                    <div class="stat-label">👑 VIPs</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number" style="--primary: #ef4444;">{stats['locked']}</div>
                    <div class="stat-label">🔒 Travados</div>
                </div>
            </div>
            
            <!-- Filters -->
            <div class="filter-chips">
                <div class="chip {'active' if filter_type == 'all' else ''}" onclick="setFilter('all')">Todos</div>
                <div class="chip {'active' if filter_type == 'online' else ''}" onclick="setFilter('online')">🟢 Online</div>
                <div class="chip {'active' if filter_type == 'idle' else ''}" onclick="setFilter('idle')">🟡 Ausentes</div>
                <div class="chip {'active' if filter_type == 'vip' else ''}" onclick="setFilter('vip')">👑 VIPs</div>
                <div class="chip {'active' if filter_type == 'locked' else ''}" onclick="setFilter('locked')">🔒 Travados</div>
            </div>
            
            <!-- Users -->
            <div class="user-grid">{users_html}</div>
        </div>
        
        <div class="toast" id="toast"></div>
        
        <script>
            // Theme
            if (localStorage.getItem('theme') === 'dark') document.body.classList.add('dark');
            
            function toggleTheme() {{
                document.body.classList.toggle('dark');
                localStorage.setItem('theme', document.body.classList.contains('dark') ? 'dark' : 'light');
            }}
            
            // Search
            let searchTimeout;
            function handleSearch(e) {{
                clearTimeout(searchTimeout);
                searchTimeout = setTimeout(() => {{
                    const q = e.target.value;
                    window.location.href = '/dashboard?q=' + encodeURIComponent(q) + '&filter={filter_type}';
                }}, 500);
            }}
            
            // Filter
            function setFilter(filter) {{
                const search = document.querySelector('.search-input').value;
                window.location.href = '/dashboard?filter=' + filter + (search ? '&q=' + encodeURIComponent(search) : '');
            }}
            
            // Menu
            function toggleMenu() {{
                document.querySelector('.hamburger').classList.toggle('active');
            }}
        </script>
    </body>
    </html>
    """

@app.route("/chat/<uid>")
def chat_view(uid):
    if not session.get("authenticated"):
        return redirect("/login")
    
    messages = get_user_messages(uid)
    stats = get_user_stats(uid)
    
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
    badges = []
    if stats['is_vip']: badges.append("👑 VIP")
    if stats['is_locked']: badges.append("🔒 Travado")
    
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
            <!-- Header -->
            <div class="chat-header-bar">
                <div class="chat-back" onclick="window.location.href='/dashboard'">
                    <i class="fas fa-arrow-left"></i>
                </div>
                <div class="chat-user-info">
                    <div class="chat-user-name">{uid[:25]}{'...' if len(uid) > 25 else ''}</div>
                    <div class="chat-user-status">{status_text} {' • '.join(badges)}</div>
                </div>
                <div style="font-size: 20px; padding: 10px; cursor: pointer;" onclick="location.reload()">
                    <i class="fas fa-sync-alt"></i>
                </div>
            </div>
            
            <!-- Messages -->
            <div class="chat-messages" id="chatMessages">
                {messages_html}
            </div>
            
            <!-- Quick Replies -->
            <div class="quick-replies" style="padding: 0 15px;">
                <div class="quick-reply" onclick="setMessage('Oi amor! 💕')">Oi amor</div>
                <div class="quick-reply" onclick="setMessage('Tudo bem? 🥰')">Tudo bem?</div>
                <div class="quick-reply" onclick="setMessage('Senti sua falta... 🥺')">Senti falta</div>
                <div class="quick-reply" onclick="setMessage('Te adoro! 💖')">Te adoro</div>
                <div class="quick-reply" onclick="setMessage('Bom dia! ☀️')">Bom dia</div>
                <div class="quick-reply" onclick="setMessage('Boa noite! 🌙')">Boa noite</div>
            </div>
            
            <!-- Photo Preview -->
            <div class="photo-preview-container" id="photoPreview">
                <img id="previewImg" class="photo-preview-img">
                <span id="photoName">foto.jpg</span>
                <button class="photo-preview-remove" onclick="removePhoto()">✕</button>
            </div>
            
            <!-- Input -->
            <div class="chat-input-area">
                <div class="chat-input-row">
                    <button class="photo-upload-btn" onclick="document.getElementById('photoInput').click()">
                        <i class="fas fa-camera"></i>
                    </button>
                    <input type="file" id="photoInput" accept="image/*" style="display:none" onchange="previewPhoto(event)">
                    <input type="text" class="chat-input" id="messageInput" placeholder="Digite sua mensagem...">
                    <button class="send-btn" onclick="sendMessage()">
                        <i class="fas fa-paper-plane"></i>
                    </button>
                </div>
            </div>
        </div>
        
        <!-- FAB -->
        <button class="fab" id="fab" onclick="toggleBottomSheet()">
            <i class="fas fa-bolt"></i>
        </button>
        
        <!-- Bottom Sheet -->
        <div class="bottom-sheet-overlay" id="overlay" onclick="toggleBottomSheet()"></div>
        <div class="bottom-sheet" id="bottomSheet">
            <div class="bottom-sheet-handle"></div>
            <div class="bottom-sheet-title">⚡ Ações Rápidas</div>
            <div class="action-grid">
                <button class="action-btn warning" onclick="executeAction('setvip')">
                    <span class="icon">👑</span>
                    <span>Ativar VIP</span>
                </button>
                <button class="action-btn success" onclick="executeAction('bonus5')">
                    <span class="icon">🎁</span>
                    <span>+5 Msgs</span>
                </button>
                <button class="action-btn success" onclick="executeAction('bonus10')">
                    <span class="icon">🎁</span>
                    <span>+10 Msgs</span>
                </button>
                <button class="action-btn" onclick="executeAction('reset')">
                    <span class="icon">🔄</span>
                    <span>Resetar</span>
                </button>
                <button class="action-btn" onclick="executeAction('clearmemory')">
                    <span class="icon">🧠</span>
                    <span>Limpar Mem.</span>
                </button>
                <button class="action-btn" onclick="executeAction('unpause')">
                    <span class="icon">▶️</span>
                    <span>Despausar</span>
                </button>
                <button class="action-btn danger" onclick="executeAction('blacklist')">
                    <span class="icon">🚫</span>
                    <span>Bloquear</span>
                </button>
                <button class="action-btn success" onclick="executeAction('unblacklist')">
                    <span class="icon">✅</span>
                    <span>Desbloquear</span>
                </button>
                <button class="action-btn" onclick="toggleBottomSheet(); setMessage('💖 Seu VIP foi ativado! Agora a gente pode conversar sem limite 😘')">
                    <span class="icon">💬</span>
                    <span>Msg VIP</span>
                </button>
            </div>
        </div>
        
        <div class="toast" id="toast"></div>
        
        <script>
            // Theme
            if (localStorage.getItem('theme') === 'dark') document.body.classList.add('dark');
            
            // Scroll to bottom
            const chatMessages = document.getElementById('chatMessages');
            chatMessages.scrollTop = chatMessages.scrollHeight;
            
            // Bottom Sheet
            function toggleBottomSheet() {{
                document.getElementById('overlay').classList.toggle('active');
                document.getElementById('bottomSheet').classList.toggle('active');
                document.getElementById('fab').classList.toggle('open');
            }}
            
            // Set message
            function setMessage(text) {{
                document.getElementById('messageInput').value = text;
                document.getElementById('messageInput').focus();
            }}
            
            // Photo handling
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
            
            // Send message
            async function sendMessage() {{
                const input = document.getElementById('messageInput');
                const message = input.value.trim();
                
                if (selectedPhoto) {{
                    // Send photo
                    const formData = new FormData();
                    formData.append('photo', selectedPhoto);
                    formData.append('caption', message);
                    
                    showToast('Enviando foto...', 'success');
                    
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
                        showToast('❌ Erro de conexão', 'error');
                    }}
                }} else if (message) {{
                    // Send text
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
                        showToast('❌ Erro de conexão', 'error');
                    }}
                }}
            }}
            
            // Execute action
            async function executeAction(action) {{
                if (action === 'blacklist' && !confirm('Bloquear este usuário?')) return;
                
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
            
            // Toast
            function showToast(message, type) {{
                const toast = document.getElementById('toast');
                toast.textContent = message;
                toast.className = 'toast ' + type + ' show';
                setTimeout(() => toast.classList.remove('show'), 3000);
            }}
            
            // Enter to send
            document.getElementById('messageInput').addEventListener('keypress', (e) => {{
                if (e.key === 'Enter') sendMessage();
            }});
            
            // Auto refresh
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
        save_admin_message(uid, f"[⚡ {action.upper()}] {message}")
        
        # Notifica usuário
        if action == "setvip":
            send_telegram_message(uid, "💖 Seu VIP foi ativado! Agora a gente pode conversar sem limite 😘")
        elif action in ["bonus5", "bonus10"]:
            amt = 5 if action == "bonus5" else 10
            send_telegram_message(uid, f"🎁 Você ganhou +{amt} mensagens extras! Aproveita 💕")
        
        return jsonify({"success": True, "message": message})
    return jsonify({"success": False, "error": message}), 500

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

@app.route("/health")
def health():
    return jsonify({"status": "ok", "redis": check_redis()})

if __name__ == "__main__":
    logger.info(f"🚀 Sophia Admin v4.0 - Porta {PORT}")
    app.run(host="0.0.0.0", port=PORT, debug=False)
