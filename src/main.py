import sys
import logging
import shlex

from src.database import init_db, db
from src.models import User, Message, Restaurant
from src.knowledge import KnowledgeManager
from src.llm import LLMClient
from src.functions import set_knowledge_manager
from src.observability import (
    record_cli_command,
    record_llm_error,
    record_user_message,
    setup_observability,
)
from src.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Keep CLI output readable: hide verbose SDK/network logs.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("qdrant_client").setLevel(logging.WARNING)

setup_observability()

logger.info(
    "Конфиг: USE_VLLM_LLM=%s → чат: %s | эмбеддинги RAG: %s",
    settings.use_vllm_llm,
    "vLLM (%s)" % settings.vllm_base_url if settings.use_vllm_llm else "OpenAI api.openai.com",
    "HuggingFace %s" % settings.hf_embedding_model if settings.use_vllm_llm else "OpenAI Embeddings API",
)


def sanitize_text(text: str) -> str:
    return text.encode('utf-8', errors='surrogateescape').decode('utf-8', errors='replace')


class ChatSession:
    def __init__(self):
        self.restaurant = Restaurant.get_or_none(Restaurant.id == 1)
        self.knowledge_manager = KnowledgeManager()
        set_knowledge_manager(self.knowledge_manager)
        self.llm = LLMClient(self.restaurant, self.knowledge_manager)
        self.user = self._create_user()
        try:
            self.knowledge_manager.ensure_seed_set_indexed(self.restaurant)
        except Exception:
            logger.exception("Не удалось проиндексировать стартовый набор знаний")
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

    def process_command(self, command_input: str) -> str:
        try:
            parts = shlex.split(command_input)
        except ValueError as e:
            return f"Ошибка парсинга команды: {e}"

        if not parts:
            return "Пустая команда"

        command = parts[0].lower()
        record_cli_command(command)

        if command == "/help":
            return (
                "Команды:\n"
                "/upload <path> [set_name] — загрузить документ в набор знаний\n"
                "/list_docs — список загруженных документов\n"
                "/list_sets — список наборов знаний\n"
                "/activate_set <set_id> — активировать набор знаний\n"
                "/reindex [set_id] — переиндексация набора\n"
                "/help — показать команды"
            )

        if command == "/upload":
            if len(parts) < 2:
                return "Использование: /upload <path> [set_name]"
            path = parts[1]
            set_name = " ".join(parts[2:]) if len(parts) > 2 else None
            try:
                return self.knowledge_manager.upload_document(self.restaurant, path, set_name)
            except Exception as e:
                logger.exception("Ошибка загрузки документа")
                return f"Не удалось загрузить документ: {e}"

        if command == "/list_docs":
            docs = list(self.knowledge_manager.list_documents(self.restaurant))
            if not docs:
                return "Документы пока не загружены"
            lines = [
                f"#{d.id} [{d.source_type}] {d.title} (set_id={d.knowledge_set_id})"
                for d in docs
            ]
            return "Документы:\n" + "\n".join(lines)

        if command == "/list_sets":
            sets = list(self.knowledge_manager.list_sets(self.restaurant))
            if not sets:
                return "Наборы знаний пока не созданы"
            lines = [
                f"#{s.id} {s.name}{' [ACTIVE]' if s.is_active else ''}"
                for s in sets
            ]
            return "Наборы знаний:\n" + "\n".join(lines)

        if command == "/activate_set":
            if len(parts) != 2:
                return "Использование: /activate_set <set_id>"
            try:
                set_id = int(parts[1])
            except ValueError:
                return "set_id должен быть целым числом"
            return self.knowledge_manager.activate_set(self.restaurant, set_id)

        if command == "/reindex":
            if len(parts) > 2:
                return "Использование: /reindex [set_id]"
            set_id = None
            if len(parts) == 2:
                try:
                    set_id = int(parts[1])
                except ValueError:
                    return "set_id должен быть целым числом"
            try:
                return self.knowledge_manager.reindex_set(self.restaurant, set_id)
            except Exception as e:
                logger.exception("Ошибка переиндексации")
                return f"Не удалось переиндексировать набор: {e}"

        return "Неизвестная команда. Введите /help"

    def process_message(self, user_input: str) -> str:
        if self.user.is_escalated:
            return "[Диалог передан менеджеру. Ожидайте ответа.]"

        record_user_message()
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
            record_llm_error("chat")
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

                if raw_input.startswith("/"):
                    command_response = session.process_command(raw_input)
                    print(f"\nСистема: {command_response}\n")
                    continue

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
