import sqlite3
import random
from flask import Flask, jsonify, request
from flask_cors import CORS
import re
import os
from functools import wraps
import threading
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes


app = Flask(__name__)
CORS(app)
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        admin_secret = os.getenv("ADMIN_SECRET")
        if not admin_secret:
            return jsonify({"error": "Admin secret not configured on server."}), 500
        submitted_secret = request.headers.get('X-Admin-Secret')
        if submitted_secret != admin_secret:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated_function

def is_safe_string(input_string):
    """
    Checks if a string contains only letters, numbers, spaces, and basic punctuation.
    Returns False if any potentially harmful symbols are found.
    """
    # This regex allows alphanumeric characters (a-z, A-Z, 0-9), spaces,
    # and a few safe punctuation marks like hyphens and periods.
    # It disallows characters like <, >, &, /, ;, etc.
    if re.search(r'[^a-zA-Z0-9 .-]+', input_string):
        return False
    return True
# ===============================================================
# Database Functions
# ===============================================================

def get_db_connection():
    conn = sqlite3.connect('lottery.db')
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
    """Helper function to write to the audit log."""
    conn = get_db_connection()
    conn.execute(
        'INSERT INTO audit_logs (actor, action, details) VALUES (?, ?, ?)',
        (actor, action, details)
    )
    conn.commit()
    conn.close()

# ===============================================================
# Admin API Endpoints
# ===============================================================

@app.route('/api/admin/rounds', methods=['POST'], endpoint='create_round_api')
@admin_required
def create_round():
    data = request.get_json()
    name = data.get('name')
    price = data.get('price')
    grid_size = data.get('grid_size')

    if not all([name, price, grid_size]):
        return jsonify({'error': 'Missing data'}), 400

    conn = get_db_connection()
    cursor = conn.execute(
        'INSERT INTO rounds (name, price, grid_size) VALUES (?, ?, ?)',
        (name, price, grid_size)
    )
    conn.commit()
    new_round_id = cursor.lastrowid
    conn.close()

    log_action('ADMIN', 'CREATE_ROUND', f'Created round "{name}" with ID {new_round_id}')
    return jsonify({'success': True, 'round_id': new_round_id}), 201
@app.route('/api/admin/rounds', methods=['POST'])
@admin_required
def create_round():
    data = request.get_json()
    name = data.get('name')
    price = data.get('price')
    grid_size = data.get('grid_size')

    if not all([name, price, grid_size]):
        return jsonify({'error': 'Missing data'}), 400

    # --- NEW VALIDATION STEP ---
    if not is_safe_string(name):
        return jsonify({'error': 'Invalid characters in round name.'}), 400
    # --- END OF VALIDATION STEP ---

    conn = get_db_connection()
    # ... (the rest of the function is unchanged) ...

# Find and REPLACE the entire get_all_rounds function with this:
@app.route('/api/admin/rounds', methods=['GET'], endpoint='get_all_rounds_api' )
@admin_required
def get_all_rounds():
    # Check for a query parameter like ?show=all
    show = request.args.get('show')
    
    conn = get_db_connection()
    query = "SELECT * FROM rounds"
    
    if show != 'all':
        query += " WHERE status != 'archived'" # Default behavior
        
    query += " ORDER BY creation_date DESC"
    
    rounds_cursor = conn.execute(query).fetchall()
    conn.close()
    return jsonify([dict(row) for row in rounds_cursor])
# We will add other admin endpoints here later...
# ... (keep the create_round and get_all_rounds functions) ...

@app.route('/api/admin/pending_approvals/<int:round_id>', methods=['GET'])
@admin_required
def get_pending_for_round(round_id):
    conn = get_db_connection()
    selections = conn.execute(
        "SELECT id, number, user_id, user_name FROM selections WHERE round_id = ? AND status = 'pending'", (round_id,)
    ).fetchall()
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
    # Disapproving now means deleting the selection to free up the number
    res = conn.execute("DELETE FROM selections WHERE id = ? AND status = 'pending'", (selection_id,))
    conn.commit()
    if res.rowcount == 0:
        conn.close()
        return jsonify({'error': 'Selection not found or not pending'}), 404
    conn.close()
    log_action('ADMIN', 'DISAPPROVE_SELECTION', f'Disapproved selection ID {selection_id}')
    return jsonify({'success': True})

@app.route('/api/admin/run_draw/<int:round_id>', methods=['POST'])
@admin_required
def run_draw(round_id):
    conn = get_db_connection()
    round_info = conn.execute("SELECT * FROM rounds WHERE id = ?", (round_id,)).fetchone()
    
    if not round_info or round_info['status'] != 'open':
        conn.close()
        return jsonify({'error': 'Round is not open for a draw'}), 400

    confirmed_selections = conn.execute(
        "SELECT * FROM selections WHERE round_id = ? AND status = 'confirmed'", (round_id,)
    ).fetchall()

    if len(confirmed_selections) < 3:
        conn.close()
        return jsonify({'error': f'Not enough confirmed players. Need at least 3, but have {len(confirmed_selections)}.'}), 400

    # Calculate prize pool
    total_players = len(confirmed_selections)
    prize_pool = total_players * round_info['price']
    prizes = {1: prize_pool * 0.40, 2: prize_pool * 0.20, 3: prize_pool * 0.10}

    # Select 3 unique winners
    winners = random.sample(confirmed_selections, 3)

    for i, winner in enumerate(winners):
        prize_tier = i + 1
        conn.execute(
            'INSERT INTO winners (round_id, winning_number, user_id, user_name, prize_tier, prize_amount) VALUES (?, ?, ?, ?, ?, ?)',
            (round_id, winner['number'], winner['user_id'], winner['user_name'], prize_tier, prizes[prize_tier])
        )
    
    # Close the round
    conn.execute("UPDATE rounds SET status = 'completed' WHERE id = ?", (round_id,))
    conn.commit()
    conn.close()

    log_action('ADMIN', 'RUN_DRAW', f'Draw completed for round {round_id}. Winners selected.')
    return jsonify({
        'success': True, 
        'message': 'Draw complete!', 
        'winners': [dict(w) for w in winners]
    })

# ... (Add this below your get_all_rounds function) ...

@app.route('/api/admin/rounds/<int:round_id>', methods=['DELETE'])
@admin_required
def delete_round(round_id):
    conn = get_db_connection()
    
    # Security check: see if any selections have been made for this round
    selections = conn.execute('SELECT id FROM selections WHERE round_id = ?', (round_id,)).fetchone()
    
    if selections:
        conn.close()
        return jsonify({'error': 'Cannot delete a round that has player selections. Please disapprove all selections first.'}), 409 # Conflict

    # Proceed with deletion
    res = conn.execute("DELETE FROM rounds WHERE id = ?", (round_id,))
    conn.commit()
    conn.close()

    if res.rowcount == 0:
        return jsonify({'error': 'Round not found'}), 404
    
    log_action('ADMIN', 'DELETE_ROUND', f'Deleted round with ID {round_id}')
    return jsonify({'success': True, 'message': 'Round deleted successfully.'})
# ... (Add this below your other admin endpoints) ...

@app.route('/api/admin/winners/<int:round_id>', methods=['GET'])
@admin_required
def get_winners_for_round(round_id):
    """Returns a list of winners for a specific completed round."""
    conn = get_db_connection()
    winners = conn.execute(
        'SELECT * FROM winners WHERE round_id = ? ORDER BY prize_tier ASC', (round_id,)
    ).fetchall()
    conn.close()
    return jsonify([dict(row) for row in winners])

@app.route('/api/admin/audit_logs', methods=['GET'])
@admin_required
def get_audit_logs():
    """Returns the most recent audit logs."""
    conn = get_db_connection()
    # Get the last 50 logs, newest first
    logs = conn.execute('SELECT * FROM audit_logs ORDER BY log_date DESC LIMIT 50').fetchall()
    conn.close()
    return jsonify([dict(row) for row in logs])
# ... (Add this below your run_draw function) ...

@app.route('/api/admin/archive_round/<int:round_id>', methods=['POST'])
@admin_required
def archive_round(round_id):
    """Changes a completed round's status to 'archived'."""
    conn = get_db_connection()
    
    # We can only archive rounds that are 'completed'.
    res = conn.execute("UPDATE rounds SET status = 'archived' WHERE id = ? AND status = 'completed'", (round_id,))
    conn.commit()
    conn.close()

    if res.rowcount == 0:
        return jsonify({'error': 'Round not found or not in a completed state'}), 404
    
    log_action('ADMIN', 'ARCHIVE_ROUND', f'Archived round with ID {round_id}')
    return jsonify({'success': True, 'message': 'Round archived successfully.'})


# ... (rest of your app.py) ...
# ===============================================================
# Player API Endpoints
# ===============================================================

@app.route('/api/rounds/open', methods=['GET'])
@app.route('/api/rounds/open', methods=['GET'])
def get_open_rounds():
    """Returns a list of rounds players can join with player counts."""
    conn = get_db_connection()
    # This SQL query now joins with the selections table to count confirmed players for each round
    rounds_cursor = conn.execute("""
        SELECT 
            r.id, r.name, r.price, r.grid_size, r.status,
            COUNT(s.id) as confirmed_players
        FROM rounds r
        LEFT JOIN selections s ON r.id = s.round_id AND s.status = 'confirmed'
        WHERE r.status = 'open'
        GROUP BY r.id
    """).fetchall()
    conn.close()
    return jsonify([dict(row) for row in rounds_cursor])
# ... (Add this below your get_open_rounds function) ...

@app.route('/api/game_state/<int:round_id>')
def get_round_game_state(round_id):
    """Returns the grid size and all selections for a specific round."""
    conn = get_db_connection()
    
    # First, get the round details (especially the grid_size)
    round_info = conn.execute('SELECT * FROM rounds WHERE id = ?', (round_id,)).fetchone()
    if not round_info:
        return jsonify({'error': 'Round not found'}), 404
    
    # Then, get all selections for that round
    selections_cursor = conn.execute(
        'SELECT number, status, user_name FROM selections WHERE round_id = ?', (round_id,)
    ).fetchall()
    conn.close()
    
    # Create a dictionary for quick lookups of selected numbers
    selections = {row['number']: dict(row) for row in selections_cursor}
    
    return jsonify({
        'round_id': round_info['id'],
        'round_name': round_info['name'],
        'grid_size': round_info['grid_size'],
        'selections': selections
    })


@app.route('/api/select_number', methods=['POST'])
def select_number():
    """Handles a player's number selection for a specific round."""
    data = request.get_json()
    round_id = data.get('round_id')
    number = data.get('number')
    user_name = data.get('user_name')
    user_id = data.get('user_id') # We'll keep simulating this for now

    if not all([round_id, number, user_name, user_id]):
        return jsonify({'error': 'Missing data'}), 400
    
    # We need to check if the number is already taken in the DB
    conn = get_db_connection()
    try:
        conn.execute(
            'INSERT INTO selections (round_id, number, user_id, user_name) VALUES (?, ?, ?, ?)',
            (round_id, number, user_id, user_name)
        )
        conn.commit()
        log_action('PLAYER', 'SELECT_NUMBER', f'User {user_name} selected number {number} in round {round_id}')
        return jsonify({'success': True, 'message': f'Your selection of number {number} is pending approval!'})
    except sqlite3.IntegrityError:
        # This error occurs if the (round_id, number) combination already exists (violates UNIQUE constraint)
        return jsonify({'error': 'Number is not available'}), 409
    finally:
        conn.close()
@app.route('/api/winners/recent', methods=['GET'])
def get_recent_winners():
    """Returns the most recent winners across all rounds, with a configurable limit."""
    # Get the 'limit' from the URL query string (e.g., ?limit=20), default to 5
    try:
        limit = int(request.args.get('limit', 5))
    except ValueError:
        limit = 5
    
    # Prevent asking for too many records
    if limit > 50:
        limit = 50

    conn = get_db_connection()
    winners_cursor = conn.execute("""
        SELECT w.user_name, w.prize_amount, r.name as round_name 
        FROM winners w
        JOIN rounds r ON w.round_id = r.id
        ORDER BY w.draw_date DESC 
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return jsonify([dict(row) for row in winners_cursor])
# ... (rest of your app.py) ...
# # ... (after your last API endpoint) ...

# ===============================================================
# TELEGRAM BOT LOGIC
# ===============================================================
GAME_LOBBY_URL = "https://nahom-dejene.github.io/telegram-gaming-platform/"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Greets the user and sends the 'Play Game' button."""
    keyboard = [[InlineKeyboardButton("🎮 Open Game Lobby", url=GAME_LOBBY_URL)]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    welcome_message = f"Greetings, {update.effective_user.first_name}!\n\nWelcome to the Lottery Platform. Press the button below to join a round."
    await update.message.reply_text(welcome_message, reply_markup=reply_markup)

# In app.py, replace the old run_bot function with this one.

def run_bot():
    """Starts the Telegram bot with detailed error logging."""
    print("--- [BOT THREAD] Starting Telegram Bot Polling ---")
    
    try:
        token = os.getenv("TELEGRAM_TOKEN")
        if not token:
            print("--- [BOT THREAD] CRITICAL: TELEGRAM_TOKEN not set. Halting bot thread. ---")
            return

        print(f"--- [BOT THREAD] Token found with length: {len(token)}. Initializing ApplicationBuilder. ---")
        
        # Build the application
        application = ApplicationBuilder().token(token).build()
        print("--- [BOT THREAD] Application built successfully. ---")

        # Add the command handler
        application.add_handler(CommandHandler("start", start))
        print("--- [BOT THREAD] /start handler added. ---")
        
        # Get the updater to start polling manually
        updater = application.updater
        if not updater:
             print("--- [BOT THREAD] CRITICAL: Updater object not found. Cannot start polling. ---")
             return
             
        print("--- [BOT THREAD] Starting updater polling loop... ---")
        updater.start_polling()
        print("--- [BOT THREAD] Bot is now officially running and polling for updates. ---")
        
        # We need to keep this thread alive.
        updater.idle()
        print("--- [BOT THREAD] Bot has stopped polling (idle). ---")

    except Exception as e:
        # Catch ANY and ALL exceptions during startup and log them.
        print("--- [BOT THREAD] !!! AN UNEXPECTED ERROR OCCURRED DURING BOT STARTUP !!! ---")
        print(f"--- [BOT THREAD] ERROR TYPE: {type(e).__name__} ---")
        print(f"--- [BOT THREAD] ERROR DETAILS: {e} ---")
        # For more detailed debugging, you could also import traceback and print the stack trace
        import traceback
        traceback.print_exc()
        print("--- [BOT THREAD] Halting bot thread due to error. ---")
# ===============================================================
# Main Execution: Start Bot Thread and Flask App
# ===============================================================

# This top-level code will run when Gunicorn imports the file on Render
print("--- Starting bot thread from top level ---")
bot_thread = threading.Thread(target=run_bot)
bot_thread.daemon = True
bot_thread.start()

# ADD THIS NEW FUNCTION TO app.py
@app.route('/debug/env')
def debug_env():
    """A temporary endpoint to check environment variables on the server."""
    token = os.getenv("TELEGRAM_TOKEN")
    
    if token:
        token_status = {
            "token_is_set": True,
            "token_length": len(token),
            "first_4_chars": token[:4],
            "last_4_chars": token[-4:]
        }
    else:
        token_status = {
            "token_is_set": False,
            "message": "TELEGRAM_TOKEN environment variable was not found."
        }
        
    return jsonify({
        "environment_check": "OK",
        "telegram_token_status": token_status
    })

if __name__ == '__main__':
    print("--- Running in local development mode ---")
    # use_reloader=False is CRITICAL to prevent the bot thread from starting twice
    app.run(debug=True, use_reloader=False, host='0.0.0.0', port=5000)