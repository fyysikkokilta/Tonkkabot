import os
import time
import datetime
import logging
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram import Bot, Update
import data
import plots

token = os.getenv("BOT_TOKEN")
info = (
    "This bot tracks the temperature at Helsinki-Vantaa (EFHK). Use command /history to plot"
    " the temperature of last 24h, command \n/temperature to plot current temperature and "
    "command /ennuste to plot the forecast of next 50h."
)

# Set up logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(info)


async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
            f"Please send an integer argument to change the plotting range."
        )
        bio = plots.history()
    except TypeError:
        bio = plots.history()
    bio.seek(0)

    tonks = data.check_tonkka_occurrence()
    if tonks:
        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=bio,
            caption=f'Tönkkä aukesi {tonks["time"]}',
        )
    else:
        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=bio,
            caption=f"Oli vielä vähän liian kylmää :(",
        )


async def temperature(update: Update, context: ContextTypes.DEFAULT_TYPE):
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


async def forecast(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
            f"Please send an integer argument to change the plotting range."
        )
        bio = plots.forecast()
    except TypeError:
        bio = plots.forecast()
    bio.seek(0)
    await context.bot.send_photo(
        chat_id=update.effective_chat.id,
        photo=bio,
        caption="Onhan tönkkä jo ostettu? ;)",
    )


async def check_history_job(context: ContextTypes.DEFAULT_TYPE):
    """Job to check history daily"""
    data.check_history()


async def error(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log Errors caused by Updates."""
    logger.warning('Update "%s" caused error "%s"', update, context.error)


async def flush_messages(bot: Bot):
    """Flushes the messages send to the bot during downtime so that the bot
    does not start spamming when it gets online again."""

    updates = await bot.get_updates()
    while updates:
        print(f"Flushing {len(updates)} messages.")
        time.sleep(1)
        updates = await bot.get_updates(updates[-1]["update_id"] + 1)


async def post_init(app: Application):
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


def main():
    app = Application.builder().token(token).concurrent_updates(False).build()
    app.post_init = post_init
    app.run_polling()


if __name__ == "__main__":
    main()
