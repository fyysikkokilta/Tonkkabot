"""
Main module for Tonkkabot.

This module contains the main Telegram bot application that tracks temperature
at Helsinki-Vantaa airport and provides weather information and plots.
"""

import datetime
import logging
import os
import time

from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes

import data
import plots

token = os.getenv("BOT_TOKEN")
BOT_INFO = (
    "This bot tracks the temperature at Helsinki-Vantaa (EFHK). Use command /history to plot"
    " the temperature of last 24h, command \n/temperature to plot current temperature and "
    "command /ennuste to plot the forecast of next 50h."
)

# Set up logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


async def start(update: Update) -> None:
    """Handle the /start command.

    Args:
        update: The update object containing the message
        context: The context object (unused)
    """
    await update.message.reply_text(BOT_INFO)


async def history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /history command.

    Args:
        update: The update object containing the message
        context: The context object containing command arguments
    """
    hours = next(iter(context.args), None)

    try:
        hours = int(hours)
        if (1 < hours) & (24 >= hours):
            bio = plots.history(hours)
        else:
            await update.message.reply_text("Argument must be between 2 and 24.")
            bio = plots.history()
    except ValueError:
        await update.message.reply_text(
            "Please send an integer argument to change the plotting range."
        )
        bio = plots.history()
    except TypeError:
        bio = plots.history()
    bio.seek(0)

    tonks = data.check_tonkka_occurrence()
    if tonks:
        await update.message.reply_photo(
            photo=bio,
            caption=f'Tönkkä aukesi {tonks["time"]}',
        )
    else:
        await update.message.reply_photo(
            photo=bio,
            caption="Oli vielä vähän liian kylmää :(",
        )


async def temperature(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /temperature command.

    Args:
        update: The update object containing the message
        context: The context object (unused)
    """
    temp, timestamp = data.temperature()
    if temp is None or timestamp is None:
        await update.message.reply_text(
            "Ei lämpötilatietoja saatavilla tällä hetkellä."
        )
        return

    await update.message.reply_text(
        f"{str(temp)}"
        + "\N{DEGREE SIGN}"
        + f"C (at {timestamp.hour:02d}:{timestamp.minute:02d})"
    )


async def forecast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /forecast command.

    Args:
        update: The update object containing the message
        context: The context object containing command arguments
    """
    hours = next(iter(context.args), None)
    try:
        hours = int(hours)
        if (1 < hours) & (48 >= hours):
            bio = plots.forecast(hours)
        else:
            await update.message.reply_text("Argument must be between 2 and 48.")
            bio = plots.forecast()
    except ValueError:
        await update.message.reply_text(
            "Please send an integer argument to change the plotting range."
        )
        bio = plots.forecast()
    except TypeError:
        bio = plots.forecast()
    bio.seek(0)
    await update.message.reply_photo(
        photo=bio,
        caption="Onhan tönkkä jo ostettu? ;)",
    )


async def check_history_job() -> None:
    """Job to check history daily.

    Args:
        context: The context object (unused)
    """
    data.check_history()


async def error(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log Errors caused by Updates.

    Args:
        update: The update object that caused the error
        context: The context object containing the error
    """
    logger.warning('Update "%s" caused error "%s"', update, context.error)


async def flush_messages(bot: Bot) -> None:
    """Flushes the messages send to the bot during downtime so that the bot
    does not start spamming when it gets online again.

    Args:
        bot: The bot instance to flush messages for
    """
    updates = await bot.get_updates()
    while updates:
        print(f"Flushing {len(updates)} messages.")
        time.sleep(1)
        updates = await bot.get_updates(updates[-1]["update_id"] + 1)


async def post_init(app: Application) -> None:
    """Initialize the application after it's built.

    Args:
        app: The application instance to initialize
    """
    await flush_messages(app.bot)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("history", history))
    app.add_handler(CommandHandler("temperature", temperature))
    app.add_handler(CommandHandler("forecast", forecast))

    # Add job to run daily at midnight
    job_queue = app.job_queue
    job_queue.run_daily(
        check_history_job,
        time=datetime.time(0, 0, 0),
        name="Check year",
    )

    app.add_error_handler(error)

    logger.info("Post init done.")


def main() -> None:
    """Main function to run the bot."""
    app = Application.builder().token(token).concurrent_updates(False).build()
    app.post_init = post_init
    app.run_polling()


if __name__ == "__main__":
    main()
