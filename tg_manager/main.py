import asyncio
from telethon import TelegramClient, events

from logic import generate_reply

# ========= Telegram =========
api_id = ...
api_hash = "..."

tg_client = TelegramClient("manager_antonio_session", api_id, api_hash)

# ========= In-memory storage =========
# потом можно заменить на БД / json / redis
user_data = {}

MAX_HISTORY = 20

ALERT_CHAT_NAME = "Manager Alerts"


def get_user_data(user_id):
    if user_id not in user_data:
        user_data[user_id] = {
            "history": [],
            "state": {}
        }
    return user_data[user_id]


def append_history(history, role, content):
    history.append({
        "role": role,
        "content": content
    })


def trim_history(history, max_len=MAX_HISTORY):
    return history[-max_len:]

async def notify_alert(message: str):
    try:
        await tg_client.send_message(ALERT_CHAT_NAME, message)
    except Exception as e:
        print("Alert send error:", e)

@tg_client.on(events.NewMessage(incoming=True))
async def handler(event):
    if event.out or not event.is_private:
        return

    user_id = event.sender_id
    user_text = (event.raw_text or "").strip()

    if not user_text:
        return

    data = get_user_data(user_id)
    history = data["history"]
    state = data["state"]

    append_history(history, "user", user_text)
    data["history"] = trim_history(history)

    try:
        await asyncio.sleep(1.0)

        loop = asyncio.get_running_loop()
        reply, new_state = await loop.run_in_executor(
            None,
            lambda: generate_reply(
                user_id=user_id,
                text=user_text,
                history=data["history"],
                state=state
            )
        )

        if not reply:
            reply = "Извините, не удалось сформировать ответ."

        data["state"] = new_state if new_state is not None else state
        append_history(data["history"], "assistant", reply)
        data["history"] = trim_history(data["history"])

        await event.reply(reply)


    except Exception as e:
        print("Telegram error:", e)

        alert_text = (

            f"🚨 Ошибка бота\n"

            f"user_id: {user_id}\n"

            f"text: {user_text}\n"

            f"error: {repr(e)}"

        )

        await notify_alert(alert_text)

        await event.reply("Извините, что-то пошло не так. Попробуйте ещё раз чуть позже.")

async def main():
    try:
        await tg_client.start()
        print("Менеджер запущен")
        await notify_alert("✅ Бот запущен")
        await tg_client.run_until_disconnected()
    except Exception as e:
        print("Fatal bot error:", e)
        await notify_alert(f"💥 Бот упал при запуске или в main loop:\n{repr(e)}")
        raise


with tg_client:
    tg_client.loop.run_until_complete(main())