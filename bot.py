import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes # <-- THIS LINE IS FIXED

# ===============================================================
# Our Game "Database"
# Make sure these URLs are correct and are the GitHub Pages links,
# not the links to the code repository.
# ===============================================================
GAMES = {
    "game_hello": {
        "title": "🚀 Hello Gamer",
        "url": "https://nahom-dejene.github.io/telegram-gaming-platform/"
    },
    "game_color": {
        "title": "🎨 Color Clicker",
        "url": "https://nahom-dejene.github.io/telegram-gaming-platform/Games/color_clicker/"
    }
    # Add your future games here!
}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a welcome message."""
    await update.message.reply_text(
        f"Welcome, {update.effective_user.first_name}! "
        "Send the /games command to see all available games."
    )

async def games(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays the game menu."""
    
    keyboard = []
    
    # Loop through our GAMES dictionary
    for game_id, game_info in GAMES.items():
        # We now create a button with a direct `url`.
        button = InlineKeyboardButton(text=game_info["title"], url=game_info["url"])
        keyboard.append([button])
        
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Please choose a game to play:", reply_markup=reply_markup)

def main():
    """Starts the bot."""
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        print("Error: TELEGRAM_TOKEN environment variable not set.")
        return

    application = ApplicationBuilder().token(token).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("games", games))
    
    print("Multi-game platform bot is running (URL button version)...")
    application.run_polling()

if __name__ == "__main__":
    main()