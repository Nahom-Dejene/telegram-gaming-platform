import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# --- SECTION TO EDIT ---
BOT_USERNAME = "HappuGamesBot" 
GAME_SHORT_NAME = "Fristtest"
# --- END OF SECTION ---


# THIS IS THE CORRECTED LINE
GAME_URL = "https://nahom-dejene.github.io/telegram-gaming-platform/"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a welcome message."""
    await update.message.reply_text(
        f"Greetings, {update.effective_user.first_name}! Send /play to start."
    )

async def play_direct(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a message with a button that has the game URL built-in."""
    
    # This URL is for a button that opens a website directly
    keyboard = [
        [InlineKeyboardButton("🎮 Play Game!", url=GAME_URL)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        'Press the button below to launch the game:', 
        reply_markup=reply_markup
    )


def main():
    """Starts the bot."""
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        print("Error: TELEGRAM_TOKEN environment variable not set.")
        return

    application = ApplicationBuilder().token(token).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("play", play_direct))
    
    print("Bot is running and listening for commands...")
    application.run_polling()

if __name__ == "__main__":
    main()