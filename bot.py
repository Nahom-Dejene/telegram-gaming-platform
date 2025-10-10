import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

# --- VERY IMPORTANT: EDIT THIS LINE ---
# Put your full, working GitHub Pages URL here.
GAME_URL = "https://YourUsername.github.io/telegram-gaming-platform/"
# --- END OF EDIT SECTION ---


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a welcome message."""
    await update.message.reply_text(
        f"Greetings, {update.effective_user.first_name}! Send /play to start the game."
    )

async def play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a message with a 'Play' button."""
    
    # We create a special button with `callback_game=True`.
    # This tells Telegram that this button is for a game.
    # We don't specify the game here, just that it's a game button.
    keyboard = [
        [InlineKeyboardButton("🎮 Click Here to Play!", callback_game=True)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # The bot sends the message with our special button.
    await update.message.reply_text('Ready to play?', reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the button press and provides the game URL."""
    
    # Get the signal (the 'query') from the button press.
    query = update.callback_query
    
    # This is the magic command. It 'answers' the signal by telling
    # the user's Telegram app to open a specific URL.
    await query.answer(url=GAME_URL)

def main():
    """Starts the bot and sets up the handlers."""
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        print("Error: TELEGRAM_TOKEN environment variable not set.")
        return

    application = ApplicationBuilder().token(token).build()

    # Command handler for /play
    application.add_handler(CommandHandler("play", play))
    
    # CallbackQueryHandler. This is the listener for our button press.
    # When ANY callback query comes in, it will be handled by the `button_handler` function.
    application.add_handler(CallbackQueryHandler(button_handler))
    
    print("Bot is running with the definitive callback logic...")
    application.run_polling()

if __name__ == "__main__":
    main()