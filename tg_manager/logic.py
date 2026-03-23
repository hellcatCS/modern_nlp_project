import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.database import db, init_db
from src.functions import set_knowledge_manager
from src.knowledge import KnowledgeManager
from src.llm import LLMClient
from src.models import Message, Restaurant, User


def sanitize_text(text: str) -> str:
    return text.encode("utf-8", errors="surrogateescape").decode("utf-8", errors="replace")


class TelegramApp:
    def __init__(self):
        init_db()
        self.restaurant = Restaurant.get_or_none(Restaurant.id == 1)
        self.knowledge_manager = KnowledgeManager()
        set_knowledge_manager(self.knowledge_manager)
        self.llm = LLMClient(self.restaurant, self.knowledge_manager)
        try:
            self.knowledge_manager.ensure_seed_set_indexed(self.restaurant)
        except Exception:
            pass

    def _get_or_create_user(self, state: dict) -> User:
        app_user_id = state.get("app_user_id")
        user = None
        if app_user_id:
            user = User.get_or_none(User.id == app_user_id)
        if user is None:
            user = User.create(restaurant=self.restaurant)
            state["app_user_id"] = user.id
        return user

    @staticmethod
    def _save_message(user: User, role: str, content: str) -> None:
        Message.create(user=user, role=role, content=sanitize_text(content))

    @staticmethod
    def _get_history(user: User) -> list[dict]:
        messages = (
            Message.select()
            .where(Message.user == user)
            .order_by(Message.created_at)
        )
        return [{"role": m.role, "content": m.content} for m in messages]

    @staticmethod
    def _mark_escalated(user: User) -> None:
        user.is_escalated = True
        user.save()

    def generate_reply(self, text: str, state: dict | None) -> tuple[str, dict]:
        if state is None:
            state = {}

        with db.connection_context():
            user = self._get_or_create_user(state)
            if user.is_escalated:
                return "Уточню, вернусь с ответом)", state

            self._save_message(user, "user", text)
            history = self._get_history(user)
            response, escalated = self.llm.chat(history)
            if escalated:
                self._mark_escalated(user)
            self._save_message(user, "assistant", response)
            return response, state


_app: TelegramApp | None = None


def _get_app() -> TelegramApp:
    global _app
    if _app is None:
        _app = TelegramApp()
    return _app


def generate_reply(user_id, text, history, state):
    return _get_app().generate_reply(text, state)
