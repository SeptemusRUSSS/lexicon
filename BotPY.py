# Wordly Bot — запуск Mini App, стрики, ежедневные напоминания
# Запуск:  pip install aiogram  →  BOT_TOKEN=... WEBAPP_URL=... python bot.py

import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

BOT_TOKEN = os.getenv("BOT_TOKEN", "ВСТАВЬ_ТОКЕН_ОТ_BOTFATHER")
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://твой-логин.github.io/wordly/")
REMIND_HOUR = 19  # час напоминания (по времени сервера)

DB_FILE = Path("users.json")
logging.basicConfig(level=logging.INFO)

bot = Bot(BOT_TOKEN)
dp = Dispatcher()


# ---------- "база данных" = один JSON-файл ----------
def load_db() -> dict:
    if DB_FILE.exists():
        try:
            return json.loads(DB_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            logging.warning("users.json повреждён, начинаю с пустой базы")
    return {}


def save_db(db: dict) -> None:
    tmp = DB_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(db, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(DB_FILE)  # атомарная запись, чтобы файл не побился


def today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


# ---------- клавиатура с кнопкой Mini App ----------
def main_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📚 Открыть Wordly", web_app=WebAppInfo(url=WEBAPP_URL))]],
        resize_keyboard=True,
    )


# ---------- команды ----------
@dp.message(Command("start"))
async def cmd_start(message: Message):
    db = load_db()
    uid = str(message.from_user.id)
    if uid not in db:
        db[uid] = {"streak": 0, "last": "", "remind": True, "name": message.from_user.first_name or ""}
        save_db(db)
    await message.answer(
        "Привет! Это Wordly — карточки для запоминания английских слов "
        "с интервальными повторениями.\n\n"
        "Жми кнопку внизу, чтобы начать. После сессии нажми "
        "«📤 Сохранить стрик в боте» — и я буду напоминать тебе, "
        "чтобы стрик не сгорел 🔥\n\n"
        "Команды: /remind — вкл/выкл напоминания, /stats — мой стрик",
        reply_markup=main_kb(),
    )


@dp.message(Command("remind"))
async def cmd_remind(message: Message):
    db = load_db()
    uid = str(message.from_user.id)
    user = db.setdefault(uid, {"streak": 0, "last": "", "remind": True, "name": ""})
    user["remind"] = not user.get("remind", True)
    save_db(db)
    await message.answer("Напоминания включены 🔔" if user["remind"] else "Напоминания выключены 🔕")


@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    db = load_db()
    user = db.get(str(message.from_user.id))
    if not user or not user.get("last"):
        await message.answer("Пока нет данных — пройди сессию в приложении и нажми «📤 Сохранить стрик».")
        return
    studied = "сегодня уже занимался ✅" if user["last"] == today() else "сегодня ещё не занимался ⏳"
    await message.answer(f"🔥 Стрик: {user['streak']} дн.\nПоследнее занятие: {user['last']}\nСтатус: {studied}")


# ---------- данные из Mini App (tg.sendData) ----------
@dp.message(F.web_app_data)
async def webapp_data(message: Message):
    try:
        data = json.loads(message.web_app_data.data)
    except (json.JSONDecodeError, AttributeError):
        return
    if data.get("type") != "session":
        return
    db = load_db()
    uid = str(message.from_user.id)
    user = db.setdefault(uid, {"streak": 0, "last": "", "remind": True, "name": ""})
    user["streak"] = int(data.get("streak", 0))
    user["last"] = today()
    save_db(db)
    await message.answer(
        f"Записал! 🔥 Стрик: {user['streak']} дн., сегодня +{data.get('xp', 0)} XP.\n"
        f"Завтра напомню, чтобы не сгорел 😉",
        reply_markup=main_kb(),
    )


# ---------- ежедневные напоминания ----------
async def reminder_loop():
    sent_for_day = ""  # чтобы не слать дважды за день
    while True:
        now = datetime.now()
        if now.hour == REMIND_HOUR and sent_for_day != today():
            sent_for_day = today()
            db = load_db()
            for uid, user in db.items():
                if not user.get("remind", True):
                    continue
                if user.get("last") == today():
                    continue  # уже занимался — не трогаем
                streak = user.get("streak", 0)
                text = (
                    f"🔥 Твой стрик {streak} {plural(streak)} сгорит сегодня! Зайди на 5 минут 👇"
                    if streak > 0
                    else "📚 Пять минут с карточками — и день не зря. Заглянешь?"
                )
                try:
                    await bot.send_message(int(uid), text, reply_markup=main_kb())
                except Exception as e:
                    logging.info(f"Не доставлено {uid}: {e}")  # заблокировал бота и т.п.
                await asyncio.sleep(0.1)  # не упираемся в лимиты Telegram
        await asyncio.sleep(60)


def plural(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return "день"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return "дня"
    return "дней"


# ---------- запуск ----------
async def main():
    asyncio.create_task(reminder_loop())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
