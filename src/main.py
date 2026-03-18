import sys
import logging

from src.database import init_db, db
from src.models import User, Message, Restaurant
from src.llm import LLMClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def sanitize_text(text: str) -> str:
    return text.encode('utf-8', errors='surrogateescape').decode('utf-8', errors='replace')


class ChatSession:
    def __init__(self):
        self.restaurant = Restaurant.get_or_none(Restaurant.id == 1)
        self.llm = LLMClient(self.restaurant)
        self.user = self._create_user()
        logger.info(f"Создан новый пользователь: {self.user.id}")

    def _create_user(self) -> User:
        return User.create(restaurant=self.restaurant)

    def _save_message(self, role: str, content: str):
        Message.create(user=self.user, role=role, content=sanitize_text(content))

    def _get_history(self) -> list[dict]:
        messages = (
            Message
            .select()
            .where(Message.user == self.user)
            .order_by(Message.created_at)
        )
        return [{"role": m.role, "content": m.content} for m in messages]

    def _mark_escalated(self):
        self.user.is_escalated = True
        self.user.save()

    def process_message(self, user_input: str) -> str:
        if self.user.is_escalated:
            return "[Диалог передан менеджеру. Ожидайте ответа.]"

        self._save_message("user", user_input)
        history = self._get_history()

        try:
            response, escalated = self.llm.chat(history)
            if escalated:
                self._mark_escalated()
            self._save_message("assistant", response)
            return response
        except Exception as e:
            logger.error(f"Ошибка LLM: {e}")
            return "Извините, произошла техническая ошибка. Попробуйте позже."


def main():
    sys.stdin = open(sys.stdin.fileno(), mode='r', encoding='utf-8', errors='surrogateescape')
    sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', errors='replace')

    logger.info("Инициализация базы данных")
    init_db()

    session = ChatSession()
    restaurant_name = session.restaurant.name if session.restaurant else "наш ресторан"
    print(f"Добро пожаловать в ресторан '{restaurant_name}'! Чем могу помочь?")
    print("(Для выхода введите 'exit' или нажмите Ctrl+C)\n")

    try:
        while True:
            try:
                raw_input = input("Вы: ").strip()
                if not raw_input:
                    continue
                if raw_input.lower() == "exit":
                    print("До свидания!")
                    break

                user_input = sanitize_text(raw_input)
                response = session.process_message(user_input)
                print(f"\nМенеджер: {response}\n")

            except EOFError:
                print("\nДо свидания!")
                break
            except KeyboardInterrupt:
                print("\nДо свидания!")
                break
    finally:
        db.close()


if __name__ == "__main__":
    main()
