import os
import logging
import asyncio

import uvicorn
from http import HTTPStatus
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from dotenv import load_dotenv

from telegram import Update
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from commands import load_all, COMMAND_HANDLERS
from commands.expense import undo_callback

from commands.natural_language import (
    handle_natural_language_message,
    natural_language_callback,
)


load_dotenv()


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


BOT_TOKEN = os.environ["BOT_TOKEN"]

# Full webhook URL for production.
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")

# Default port for local webhook testing.
PORT = int(os.getenv("PORT", 8000))


async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
):
    logger.exception(
        "Exception while handling an update:",
        exc_info=context.error,
    )

    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text(
            "⚠️ Something went wrong while handling that command."
        )


async def prepare_polling(app: Application):
    try:
        await app.bot.delete_webhook(
            drop_pending_updates=True
        )

        logger.info(
            "Webhook removed successfully."
        )

    except TelegramError as e:
        logger.warning(
            f"Couldn't remove webhook: {e}"
        )


async def run_server(app: Application):
    """Run the bot in webhook mode with Uvicorn server."""

    async def telegram_webhook(request: Request):
        """Handle incoming webhook requests from Telegram."""

        if WEBHOOK_SECRET:
            received_secret = request.headers.get(
                "X-Telegram-Bot-Api-Secret-Token"
            )

            if received_secret != WEBHOOK_SECRET:
                logger.warning(
                    "Received webhook request with invalid secret"
                )

                return PlainTextResponse(
                    "Unauthorized",
                    status_code=HTTPStatus.UNAUTHORIZED,
                )

        data = await request.json()

        update = Update.de_json(
            data=data,
            bot=app.bot,
        )

        await app.update_queue.put(update)

        return PlainTextResponse("OK")

    async def health(request: Request):
        """Health check endpoint."""

        return PlainTextResponse(
            "OK",
            status_code=HTTPStatus.OK,
        )

    web_app = Starlette(
        routes=[
            Route(
                f"/{BOT_TOKEN}",
                telegram_webhook,
                methods=["POST"],
            ),
            Route(
                "/health",
                health,
                methods=["GET", "HEAD"],
            ),
        ]
    )

    # Validate webhook URL is configured.
    if not WEBHOOK_URL:
        logger.error(
            "WEBHOOK_URL environment variable is not set. "
            "Cannot run in webhook mode without a valid webhook URL."
        )

        raise ValueError(
            "WEBHOOK_URL must be set for webhook mode"
        )

    # Set up webhook with Telegram.
    try:
        await app.bot.set_webhook(
            url=WEBHOOK_URL,
            secret_token=WEBHOOK_SECRET,
            allowed_updates=Update.ALL_TYPES,
        )

        logger.info(
            "✅ Webhook configured successfully"
        )

        logger.info(
            f"   Webhook URL: {WEBHOOK_URL}"
        )

        logger.info(
            "   Secret token: "
            f"{'configured' if WEBHOOK_SECRET else 'not configured'}"
        )

    except Exception as e:
        logger.error(
            f"Failed to set webhook: {e}"
        )

        raise

    # Configure Uvicorn server.
    config = uvicorn.Config(
        app=web_app,
        host="0.0.0.0",
        port=PORT,
        log_level="info",
    )

    server = uvicorn.Server(config)

    logger.info(
        f"🚀 Starting webhook server on port {PORT}"
    )

    # Start the application and server.
    try:
        async with app:
            await app.start()
            await server.serve()

    except Exception as e:
        logger.error(
            f"Server error: {e}"
        )

        raise

    finally:
        # Ensure proper cleanup.
        try:
            await app.stop()

        except Exception as cleanup_error:
            logger.warning(
                f"Error during cleanup: {cleanup_error}"
            )


def main():
    """Main entry point for the Finance Bot."""

    logger.info("=" * 60)
    logger.info("💰 TELEGRAM FINANCE BOT")
    logger.info("=" * 60)

    # Automatically discover all commands.
    load_all()

    # Determine run mode from explicit RUN_MODE env var.
    run_mode = os.getenv(
        "RUN_MODE",
        "polling",
    ).lower()

    if run_mode == "webhook":
        logger.info(
            "🌐 Running in WEBHOOK mode"
        )

        # Validate required configuration for webhook mode.
        if not WEBHOOK_URL:
            logger.error(
                "❌ WEBHOOK_URL must be set for webhook mode"
            )

            logger.error(
                "   Example: "
                "WEBHOOK_URL=https://your-app.onrender.com/YOUR_BOT_TOKEN"
            )

            return

        app = (
            Application.builder()
            .token(BOT_TOKEN)
            .updater(None)
            .build()
        )

    elif run_mode == "polling":
        logger.info(
            "📡 Running in POLLING mode (local development)"
        )

        app = (
            Application.builder()
            .token(BOT_TOKEN)
            .build()
        )

    else:
        logger.error(
            f"❌ Invalid RUN_MODE: '{run_mode}'. "
            "Must be 'polling' or 'webhook'"
        )

        return

    # Register all Telegram commands.
    logger.info(
        f"📝 Registering {len(COMMAND_HANDLERS)} commands..."
    )

    for name, handler_func, description in COMMAND_HANDLERS:
        app.add_handler(
            CommandHandler(
                name,
                handler_func,
            )
        )

        logger.info(
            f"   /{name} - {description}"
        )

    # ---------------------------------------------------------
    # CALLBACK HANDLERS
    # ---------------------------------------------------------

    # Existing undo callback.
    app.add_handler(
        CallbackQueryHandler(
            undo_callback,
            pattern=r"^undo_(yes|no)(:\d+)?$",
        )
    )

    # Natural-language transaction confirmation/cancellation.
    app.add_handler(
        CallbackQueryHandler(
            natural_language_callback,
            pattern=r"^nl_(confirm|cancel)$",
        )
    )

    # ---------------------------------------------------------
    # NATURAL LANGUAGE TRANSACTION HANDLER
    # ---------------------------------------------------------

    # Handles ordinary text messages such as:
    #
    # "Spent ₹350 on dinner at Domino's"
    #
    # Slash commands are excluded because they are handled
    # by the CommandHandlers above.
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_natural_language_message,
        )
    )

    # Register global error handler.
    app.add_error_handler(
        error_handler
    )

    logger.info("=" * 60)

    # Start the bot.
    try:

        if run_mode == "webhook":
            asyncio.run(
                run_server(app)
            )

        else:
            app.post_init = (
                prepare_polling
            )

            app.run_polling(
                drop_pending_updates=True
            )

    except KeyboardInterrupt:
        logger.info(
            "🛑 Bot stopped by user"
        )

    except Exception as e:
        logger.exception(
            f"❌ Fatal error: {e}"
        )


if __name__ == "__main__":
    main()