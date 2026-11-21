import json
import logging
import os
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

import settings as cfg

logging.basicConfig(format="%(asctime)s %(name)s %(levelname)s %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)  # не светить токен в логах
log = logging.getLogger("guide_bot")


def load_env(path=".env"):
    """Минимальный загрузчик .env (без внешних зависимостей)."""
    p = Path(__file__).with_name(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def menu():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(cfg.BTN_CATALOG, url=cfg.SHOP_URL)],
            [InlineKeyboardButton(cfg.BTN_CHOOSE, callback_data="choose")],
            [InlineKeyboardButton(cfg.BTN_CODE, callback_data="code")],
            [InlineKeyboardButton(cfg.BTN_CONTACT, url=cfg.CONTACT_URL)],
        ]
    )


# ---------- запоминаем, кого уже приветствовали (чтобы не слать владельцу повторы) ----------
def _seen_path():
    d = Path(os.environ.get("DATA_DIR", "data"))
    try:
        d.mkdir(parents=True, exist_ok=True)
    except Exception:
        d = Path(".")
    return d / "seen.json"


def _load_seen():
    try:
        return set(json.loads(_seen_path().read_text(encoding="utf-8")))
    except Exception:
        return set()


def _save_seen(seen):
    try:
        _seen_path().write_text(json.dumps(sorted(seen)), encoding="utf-8")
    except Exception:
        log.exception("Не удалось сохранить список пользователей")


async def notify_owner(context, user):
    owner_id = os.environ.get("OWNER_ID")
    if not owner_id:
        return
    name = user.full_name or "без имени"
    contact = f"@{user.username}" if user.username else f"tg://user?id={user.id}"
    try:
        await context.bot.send_message(
            chat_id=int(owner_id), text=f"Новый человек зашёл в бота\n\nКто: {name} ({contact})"
        )
    except Exception:
        log.exception("Не удалось отправить уведомление владельцу")


def choose_markup():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(cfg.BTN_GO_COMPANY, url=cfg.COMPANY_BOT_URL)],
            [InlineKeyboardButton(cfg.BTN_CATALOG, url=cfg.SHOP_URL)],
        ]
    )


async def send_choose(message):
    await message.reply_text(cfg.CHOOSE_MESSAGE, parse_mode="HTML", reply_markup=choose_markup())


async def show_choose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await send_choose(q.message)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args and context.args[0] == "choose":
        await send_choose(update.effective_message)  # пришли из канала по кнопке «Перейти к выбору»
    else:
        await update.effective_message.reply_text(cfg.WELCOME, reply_markup=menu())
    user = update.effective_user
    if user and str(user.id) != os.environ.get("OWNER_ID", ""):
        seen = _load_seen()
        if user.id not in seen:
            seen.add(user.id)
            _save_seen(seen)
            await notify_owner(context, user)


async def show_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.message.reply_text(cfg.CODE_MESSAGE, reply_markup=menu())


def channel_menu():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(cfg.BTN_CATALOG, url=cfg.SHOP_URL)],
            [InlineKeyboardButton(cfg.BTN_CHOOSE, url=cfg.BOT_URL + "?start=choose")],
            [InlineKeyboardButton(cfg.BTN_OPEN_BOT, url=cfg.BOT_URL)],
            [InlineKeyboardButton(cfg.BTN_CONTACT, url=cfg.CONTACT_URL)],
        ]
    )


async def channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Публикует в канале пост с кнопками. Команда работает только у владельца."""
    user = update.effective_user
    if not user or str(user.id) != os.environ.get("OWNER_ID", ""):
        return
    channel_id = os.environ.get("CHANNEL_ID")
    if not channel_id:
        await update.effective_message.reply_text("Не задан CHANNEL_ID в переменных на Bothost.")
        return
    try:
        await context.bot.send_message(
            chat_id=int(channel_id), text=cfg.CHANNEL_POST, reply_markup=channel_menu()
        )
        await update.effective_message.reply_text("Готово, пост опубликован в канале. Закрепите его вручную.")
    except Exception as e:
        log.exception("Не удалось опубликовать пост в канале")
        await update.effective_message.reply_text(f"Не получилось опубликовать пост: {e}")


async def any_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(cfg.FALLBACK, reply_markup=menu())


def main():
    load_env()
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise SystemExit("Не найден BOT_TOKEN. Укажите его в переменных или в файле .env")
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler(["start", "menu", "catalog"], start))
    app.add_handler(CommandHandler("channel_post", channel_post))
    app.add_handler(CallbackQueryHandler(show_code, pattern=r"^code$"))
    app.add_handler(CallbackQueryHandler(show_choose, pattern=r"^choose$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, any_text))
    log.info("Бот запущен")
    app.run_polling()


if __name__ == "__main__":
    main()
