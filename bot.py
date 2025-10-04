import os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# This function will be called when a user sends the /start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a welcome message when the /start command is issued."""
    await update.message.reply_text(
        f"Greetings, {update.effective_user.first_name}! Welcome to our gaming realm."
    )

def main():
    """Starts the bot."""
    # --- IMPORTANT ---
    # We get the bot token from an environment variable.
    # This is a security best practice. Do NOT write your token directly in the code.
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        print("Error: TELEGRAM_TOKEN environment variable not set.")
        return

    # Create the Application and pass it your bot's token.
    application = ApplicationBuilder().token(token).build()

    # Register the /start command handler
    application.add_handler(CommandHandler("start", start))

    # Start the Bot. This will run until you press Ctrl-C
    print("Bot is running...")
    application.run_polling()

if __name__ == "__main__":
    main()