import os
import re
from functools import wraps
from flask import Flask, jsonify, request
from flask_cors import CORS
import sqlite3
import random
import asyncio

# Telegram Bot Imports
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, ContextTypes

# ===============================================================
# Initialize Flask App & Telegram Bot
# ===============================================================
app = Flask(__name__)
CORS(app)

# --- Bot Configuration ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GAME_LOBBY_URL = "https://nahom-dejene.github.io/telegram-gaming-platform/"

if TELEGRAM_TOKEN:
    bot_app = Application.builder().token(TELEGRAM_TOKEN).build()
else:
    print("WARNING: TELEGRAM_TOKEN environment variable not set. Bot webhook will be disabled.")
    bot_app = None

# ===============================================================
# Database & Validation
# ===============================================================
def get_db_connection():
    # check_same_thread=False is important for Flask's multithreading in development
    conn = sqlite3.connect('lottery.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    with open('schema.sql', 'r') as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()
    print("Database initialized with new schema.")

def log_action(actor, action, details):
    conn = get_db_connection()
    conn.execute('INSERT INTO audit_logs (actor, action, details) VALUES (?, ?, ?)', (actor, action, details))
    conn.commit()
    conn.close()

def is_safe_string(input_string):
    if re.search(r'[^a-zA-Z0-9 .-]+', input_string):
        return False
    return True

# ===============================================================
# Admin Authentication (Ready for deployment)
# ===============================================================
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # NOTE: This is disabled for local dev. Uncomment before final deployment.
        # admin_secret = os.getenv("ADMIN_SECRET")
        # if not admin_secret: return jsonify({"error": "Admin secret not configured."}), 500
        # submitted_secret = request.headers.get('X-Admin-Secret')
        # if submitted_secret != admin_secret: return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated_function

# ===============================================================
# Admin API Endpoints
# ===============================================================
@app.route('/api/admin/rounds', methods=['POST'])
@admin_required
def create_round():
    data = request.get_json()
    name, price, grid_size = data.get('name'), data.get('price'), data.get('grid_size')
    if not all([name, price, grid_size]) or not is_safe_string(name):
        return jsonify({'error': 'Invalid or missing data'}), 400
    conn = get_db_connection()
    cursor = conn.execute('INSERT INTO rounds (name, price, grid_size) VALUES (?, ?, ?)', (name, price, grid_size))
    conn.commit()
    new_round_id = cursor.lastrowid
    conn.close()
    log_action('ADMIN', 'CREATE_ROUND', f'Created round "{name}" with ID {new_round_id}')
    return jsonify({'success': True, 'round_id': new_round_id}), 201

@app.route('/api/admin/rounds', methods=['GET'])
@admin_required
def get_all_rounds():
    show = request.args.get('show')
    conn = get_db_connection()
    query = "SELECT * FROM rounds"
    if show != 'all': query += " WHERE status != 'archived'"
    query += " ORDER BY creation_date DESC"
    rounds = conn.execute(query).fetchall()
    conn.close()
    return jsonify([dict(row) for row in rounds])

@app.route('/api/admin/rounds/<int:round_id>', methods=['DELETE'])
@admin_required
def delete_round(round_id):
    conn = get_db_connection()
    selections = conn.execute('SELECT id FROM selections WHERE round_id = ?', (round_id,)).fetchone()
    if selections:
        conn.close()
        return jsonify({'error': 'Cannot delete round with player selections.'}), 409
    res = conn.execute("DELETE FROM rounds WHERE id = ?", (round_id,))
    conn.commit()
    conn.close()
    if res.rowcount == 0: return jsonify({'error': 'Round not found'}), 404
    log_action('ADMIN', 'DELETE_ROUND', f'Deleted round ID {round_id}')
    return jsonify({'success': True})

@app.route('/api/admin/pending_approvals/<int:round_id>', methods=['GET'])
@admin_required
def get_pending_for_round(round_id):
    conn = get_db_connection()
    selections = conn.execute("SELECT id, number, user_id, user_name FROM selections WHERE round_id = ? AND status = 'pending'", (round_id,)).fetchall()
    conn.close()
    return jsonify([dict(row) for row in selections])

@app.route('/api/admin/approve_selection', methods=['POST'])
@admin_required
def approve_selection():
    selection_id = request.get_json().get('selection_id')
    conn = get_db_connection()
    conn.execute("UPDATE selections SET status = 'confirmed' WHERE id = ? AND status = 'pending'", (selection_id,))
    conn.commit()
    if conn.total_changes == 0:
        conn.close()
        return jsonify({'error': 'Selection not found or not pending'}), 404
    conn.close()
    log_action('ADMIN', 'APPROVE_SELECTION', f'Approved selection ID {selection_id}')
    return jsonify({'success': True})

@app.route('/api/admin/disapprove_selection', methods=['POST'])
@admin_required
def disapprove_selection():
    selection_id = request.get_json().get('selection_id')
    conn = get_db_connection()
    res = conn.execute("DELETE FROM selections WHERE id = ? AND status = 'pending'", (selection_id,))
    conn.commit()
    if res.rowcount == 0:
        conn.close()
        return jsonify({'error': 'Selection not found or not pending'}), 404
    conn.close()
    log_action('ADMIN', 'DISAPPROVE_SELECTION', f'Disapproved selection ID {selection_id}')
    return jsonify({'success': True})

# In app.py, replace the existing run_draw function

@app.route('/api/admin/run_draw/<int:round_id>', methods=['POST'])
@admin_required
def run_draw(round_id):
    # ... (The first part of the function is the same: get round info, get selections, check count) ...
    conn = get_db_connection()
    round_info = conn.execute("SELECT * FROM rounds WHERE id = ?", (round_id,)).fetchone()
    if not round_info or round_info['status'] != 'open':
        conn.close()
        return jsonify({'error': 'Round is not open for a draw'}), 400
    confirmed_selections = conn.execute("SELECT * FROM selections WHERE round_id = ? AND status = 'confirmed'", (round_id,)).fetchall()
    if len(confirmed_selections) < 3:
        conn.close()
        return jsonify({'error': f'Need at least 3 confirmed players, have {len(confirmed_selections)}.'}), 400
    
    # ... (Prize calculation is the same) ...
    prize_pool = len(confirmed_selections) * round_info['price']
    prizes = {1: prize_pool * 0.40, 2: prize_pool * 0.20, 3: prize_pool * 0.10}
    winners = random.sample(confirmed_selections, 3)

    # --- NEW LOGIC: SEND TELEGRAM MESSAGES ---
    if bot_app:
        print("Attempting to send winner notifications via Telegram...")
        for i, winner in enumerate(winners):
            prize_tier = i + 1
            winner_user_id = winner['user_id']
            message = (
                f"🎉 Congratulations, {winner['user_name']}! 🎉\n\n"
                f"You have won in the lottery round: **{round_info['name']}**.\n\n"
                f"**Your Rank:** {prize_tier}\n"
                f"**Your Winning Number:** {winner['number']}\n"
                f"**Your Prize:** {prizes[prize_tier]:.2f} Birr\n\n"
                "We will be in contact with you shortly regarding your prize."
            )
            try:
                # We need to run this async function within our sync Flask context
                asyncio.run(bot_app.bot.send_message(chat_id=winner_user_id, text=message, parse_mode='Markdown'))
                print(f"Successfully sent message to user ID: {winner_user_id}")
            except Exception as e:
                print(f"ERROR: Could not send message to user ID {winner_user_id}. Reason: {e}")
    # --- END OF NEW LOGIC ---

    # ... (The rest of the function is the same: save winners to DB, close round) ...
    for i, winner in enumerate(winners):
        prize_tier = i + 1
        conn.execute('INSERT INTO winners (round_id, winning_number, user_id, user_name, prize_tier, prize_amount) VALUES (?, ?, ?, ?, ?, ?)',
                     (round_id, winner['number'], winner['user_id'], winner['user_name'], prize_tier, prizes[prize_tier]))
    conn.execute("UPDATE rounds SET status = 'completed' WHERE id = ?", (round_id,))
    conn.commit()
    conn.close()
    log_action('ADMIN', 'RUN_DRAW', f'Draw completed for round {round_id}.')
    return jsonify({'success': True, 'winners': [dict(w) for w in winners]})

@app.route('/api/admin/archive_round/<int:round_id>', methods=['POST'])
@admin_required
def archive_round(round_id):
    conn = get_db_connection()
    res = conn.execute("UPDATE rounds SET status = 'archived' WHERE id = ? AND status = 'completed'", (round_id,))
    conn.commit()
    conn.close()
    if res.rowcount == 0: return jsonify({'error': 'Round not found or not completed'}), 404
    log_action('ADMIN', 'ARCHIVE_ROUND', f'Archived round ID {round_id}')
    return jsonify({'success': True})

@app.route('/api/admin/winners/<int:round_id>', methods=['GET'])
@admin_required
def get_winners_for_round(round_id):
    conn = get_db_connection()
    winners = conn.execute('SELECT * FROM winners WHERE round_id = ? ORDER BY prize_tier ASC', (round_id,)).fetchall()
    conn.close()
    return jsonify([dict(row) for row in winners])

@app.route('/api/admin/audit_logs', methods=['GET'])
@admin_required
def get_audit_logs():
    conn = get_db_connection()
    logs = conn.execute('SELECT * FROM audit_logs ORDER BY log_date DESC LIMIT 50').fetchall()
    conn.close()
    return jsonify([dict(row) for row in logs])

# ===============================================================
# Player API Endpoints
# ===============================================================
@app.route('/api/rounds/open', methods=['GET'])
def get_open_rounds():
    conn = get_db_connection()
    rounds = conn.execute("""
        SELECT r.id, r.name, r.price, r.grid_size, COUNT(s.id) as confirmed_players
        FROM rounds r LEFT JOIN selections s ON r.id = s.round_id AND s.status = 'confirmed'
        WHERE r.status = 'open' GROUP BY r.id ORDER BY r.creation_date DESC
    """).fetchall()
    conn.close()
    return jsonify([dict(row) for row in rounds])

@app.route('/api/game_state/<int:round_id>')
def get_round_game_state(round_id):
    conn = get_db_connection()
    round_info = conn.execute('SELECT * FROM rounds WHERE id = ?', (round_id,)).fetchone()
    if not round_info: return jsonify({'error': 'Round not found'}), 404
    selections_cursor = conn.execute('SELECT number, status, user_name FROM selections WHERE round_id = ?', (round_id,)).fetchall()
    conn.close()
    selections = {row['number']: dict(row) for row in selections_cursor}
    return jsonify({'round_id': round_info['id'], 'round_name': round_info['name'], 'grid_size': round_info['grid_size'], 'selections': selections})

@app.route('/api/select_number', methods=['POST'])
def select_number():
    data = request.get_json()
    round_id, number, user_name, user_id = data.get('round_id'), data.get('number'), data.get('user_name'), data.get('user_id')
    if not all([round_id, number, user_name, user_id]): return jsonify({'error': 'Missing data'}), 400
    conn = get_db_connection()
    try:
        conn.execute('INSERT INTO selections (round_id, number, user_id, user_name) VALUES (?, ?, ?, ?)', (round_id, number, user_id, user_name))
        conn.commit()
        log_action('PLAYER', 'SELECT_NUMBER', f'User {user_name} selected #{number} in round {round_id}')
        return jsonify({'success': True, 'message': f'Your selection for number {number} is pending approval!'})
    except sqlite3.IntegrityError:
        return jsonify({'error': 'Number is not available'}), 409
    finally:
        conn.close()

@app.route('/api/winners/recent', methods=['GET'])
def get_recent_winners():
    limit = int(request.args.get('limit', 5))
    if limit > 50: limit = 50
    conn = get_db_connection()
    winners = conn.execute("""
        SELECT w.user_name, w.prize_amount, r.name as round_name FROM winners w
        JOIN rounds r ON w.round_id = r.id ORDER BY w.draw_date DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return jsonify([dict(row) for row in winners])

# Add this to the Player API Endpoints section in app.py

@app.route('/api/winners/history', methods=['GET'])
def get_winner_history():
    """Returns the full winner details for the last 3 completed rounds."""
    conn = get_db_connection()
    # First, get the IDs of the last 3 completed/archived rounds
    recent_rounds = conn.execute(
        "SELECT id, name FROM rounds WHERE status IN ('completed', 'archived') ORDER BY id DESC LIMIT 3"
    ).fetchall()
    
    history = []
    for round_row in recent_rounds:
        winners = conn.execute(
            "SELECT * FROM winners WHERE round_id = ? ORDER BY prize_tier ASC", (round_row['id'],)
        ).fetchall()
        history.append({
            "round_name": round_row['name'],
            "winners": [dict(w) for w in winners]
        })
        
    conn.close()
    return jsonify(history)

# ===============================================================
# TELEGRAM BOT LOGIC
# ===============================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Greets the user and sends a proper Web App button."""
    web_app = WebAppInfo(url=GAME_LOBBY_URL)
    keyboard = [[InlineKeyboardButton("🎮 Open Game Lobby", web_app=web_app)]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # --- MAKE THIS CHANGE ---
    welcome_message = (
        f"Greetings, {update.effective_user.first_name}!\n\n"
        "This is the NEW version of the bot. Press the button below to launch the Web App."
    )
    # --- END OF CHANGE ---

    await update.message.reply_text(welcome_message, reply_markup=reply_markup)
if bot_app:
    bot_app.add_handler(CommandHandler("start", start))

@app.route('/telegram-webhook', methods=['POST'])
async def webhook():
    """Handles updates from Telegram."""
    if bot_app:
        update_data = request.get_json()
        async with bot_app:
            await bot_app.process_update(Update.de_json(data=update_data, bot=bot_app.bot))
        return 'OK', 200
    else:
        return 'Bot not configured', 500

# ===============================================================
# One-Time Webhook Setup (Run this locally)
# ===============================================================
async def setup_webhook():
    if bot_app:
        webhook_url = "https://telegram-gaming-platform.onrender.com/telegram-webhook" # Use your actual Render URL
        async with bot_app:
            await bot_app.bot.set_webhook(url=webhook_url)
            print(f"Webhook set to: {webhook_url}")
            webhook_info = await bot_app.bot.get_webhook_info()
            print(f"Webhook info: {webhook_info}")
    else:
        print("Cannot set webhook, TELEGRAM_TOKEN is not set.")

