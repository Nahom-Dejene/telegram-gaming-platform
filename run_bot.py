import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# --- IMPORTANT: VERIFY THIS URL ---
# This must be the public URL to your GitHub Pages frontend.
GAME_LOBBY_URL = "https://nahom-dejene.github.io/telegram-gaming-platform/"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Greets the user and sends the 'Play Game' button."""
    
    # Create the button that links to your game lobby
    keyboard = [
        [InlineKeyboardButton("🎮 Open Game Lobby", url=GAME_LOBBY_URL)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    welcome_message = (
        f"Greetings, {update.effective_user.first_name}!\n\n"
        "Welcome to the Lottery Platform. Press the button below to see all open games and join a round."
    )
    
    await update.message.reply_text(welcome_message, reply_markup=reply_markup)

def main():
    """Starts the Telegram bot."""
    print("Starting bot...")

    # Get the Telegram Bot Token from environment variables
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        print("Error: TELEGRAM_TOKEN environment variable not set.")
        return

    # Set up the bot application
    application = ApplicationBuilder().token(token).build()

    # Register the /start command handler
    application.add_handler(CommandHandler("start", start))

    # Start the bot. This will run forever until you stop it.
    print("Bot is running. Polling for updates...")
    application.run_polling()

if __name__ == "__main__":
    main()