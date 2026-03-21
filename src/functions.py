import logging
import secrets
import string
from datetime import datetime, timedelta
from langchain_core.tools import tool

from src.config import settings
from src.knowledge import KnowledgeManager
from src.models import Restaurant, Table, Booking

logger = logging.getLogger(__name__)

BOOKING_DURATION_HOURS = 2
BOOKING_CODE_ALPHABET = "".join(
    ch for ch in (string.ascii_uppercase + string.digits) if ch not in {"O", "0", "I", "1"}
)
_knowledge_manager: KnowledgeManager | None = None


def set_knowledge_manager(manager: KnowledgeManager):
    global _knowledge_manager
    _knowledge_manager = manager


def _get_knowledge_manager() -> KnowledgeManager:
    global _knowledge_manager
    if _knowledge_manager is None:
        _knowledge_manager = KnowledgeManager()
    return _knowledge_manager

def _validate_booking_slot(restaurant: Restaurant, date: str, time: str):
    try:
        start_at = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
        end_at = start_at + timedelta(hours=BOOKING_DURATION_HOURS)
    except ValueError:
        return None, None, "Неверный формат даты/времени. Используйте YYYY-MM-DD и HH:MM"

    if start_at.minute % 30 != 0:
        return None, None, "Время брони должно быть кратно 30 минутам (например, 18:00, 18:30)"

    opening = restaurant.opening_time
    closing = restaurant.closing_time
    if start_at.date() != end_at.date() or not (opening <= start_at.time() and end_at.time() <= closing):
        opening = str(restaurant.opening_time)[:5]
        closing = str(restaurant.closing_time)[:5]
        return None, None, f"Бронирование возможно только в рабочие часы: {opening}–{closing}"

    return start_at, end_at, None


def _generate_booking_code(length: int = 7) -> str:
    for _ in range(50):
        code = "".join(secrets.choice(BOOKING_CODE_ALPHABET) for _ in range(length))
        if not Booking.get_or_none(Booking.booking_code == code):
            return code
    raise RuntimeError("Не удалось сгенерировать уникальный booking_id")


def find_available_table(
    restaurant_id: int, start_at, end_at, guests_count: int
):
    tables = (
        Table
        .select()
        .where(
            (Table.restaurant == restaurant_id) &
            (Table.capacity >= guests_count) &
            (Table.is_active == True)
        )
        .order_by(Table.capacity)
    )

    for table in tables:
        existing = (
            Booking
            .select()
            .where(
                (Booking.table == table) &
                (Booking.start_at < end_at) &
                (Booking.end_at > start_at) &
                (Booking.status == "confirmed")
            )
            .count()
        )
        if existing == 0:
            return table

    return None


def get_available_tables_info(restaurant_id: int, start_at, end_at, guests_count: int) -> dict:
    result = {2: 0, 4: 0, 6: 0}

    tables = (
        Table
        .select()
        .where(
            (Table.restaurant == restaurant_id) &
            (Table.capacity >= guests_count) &
            (Table.is_active == True)
        )
    )

    for table in tables:
        existing = (
            Booking
            .select()
            .where(
                (Booking.table == table) &
                (Booking.start_at < end_at) &
                (Booking.end_at > start_at) &
                (Booking.status == "confirmed")
            )
            .count()
        )
        if existing == 0 and table.capacity in result:
            result[table.capacity] += 1

    return result


@tool
def check_availability(date: str, time: str, guests_count: int) -> str:
    """Проверить наличие свободных столиков на указанную дату и время.

    Args:
        date: Дата (YYYY-MM-DD)
        time: Время (HH:MM)
        guests_count: Количество гостей
    """
    restaurant = Restaurant.get_or_none(Restaurant.id == 1)
    if not restaurant:
        return "Ресторан не найден"

    start_at, end_at, error = _validate_booking_slot(restaurant, date, time)
    if error:
        return error

    available = get_available_tables_info(restaurant.id, start_at, end_at, guests_count)
    total = sum(available.values())

    if total == 0:
        return f"К сожалению, на {date} в {time} свободных столиков на {guests_count} гостей нет"

    parts = []
    if available[2] > 0:
        parts.append(f"{available[2]} на 2 персоны")
    if available[4] > 0:
        parts.append(f"{available[4]} на 4 персоны")
    if available[6] > 0:
        parts.append(f"{available[6]} на 6 персон")

    return f"На {date} в {time} доступно: {', '.join(parts)}"


@tool
def create_booking(guest_name: str, phone: str, date: str, time: str, guests_count: int) -> str:
    """Создать бронирование столика в ресторане.

    Args:
        guest_name: Имя гостя
        phone: Номер телефона
        date: Дата бронирования (YYYY-MM-DD)
        time: Время бронирования (HH:MM)
        guests_count: Количество гостей
    """
    logger.info(f"Создание бронирования: {guest_name}, {phone}, {date}, {time}, {guests_count} гостей")

    restaurant = Restaurant.get_or_none(Restaurant.id == 1)
    if not restaurant:
        return "Ошибка: ресторан не найден"

    start_at, end_at, error = _validate_booking_slot(restaurant, date, time)
    if error:
        return error

    table = find_available_table(restaurant.id, start_at, end_at, guests_count)

    if not table:
        available = get_available_tables_info(restaurant.id, start_at, end_at, guests_count)
        if sum(available.values()) == 0:
            return f"К сожалению, на {date} в {time} нет свободных столиков. Попробуйте выбрать другое время."

        return f"Нет столика на {guests_count} гостей. Доступны столики: на 2 ({available[2]}), на 4 ({available[4]}), на 6 ({available[6]})"

    booking = Booking.create(
        table=table,
        booking_code=_generate_booking_code(),
        guest_name=guest_name,
        phone=phone,
        date=date,
        time=time,
        start_at=start_at,
        end_at=end_at,
        guests_count=guests_count
    )

    return (
        f"Бронирование подтверждено! Столик №{table.table_number} на {guests_count} гостей, "
        f"{date} в {time}. booking_id={booking.booking_code}"
    )


@tool
def cancel_booking(booking_id: str) -> str:
    """Отменить существующее бронирование.

    Args:
        booking_id: Публичный идентификатор брони (буквы+цифры, 6-7 символов)
    """
    logger.info(f"Отмена бронирования: booking_id={booking_id}")
    value = str(booking_id).strip().upper()

    booking = Booking.get_or_none(
        (Booking.booking_code == value) &
        (Booking.status == "confirmed")
    )
    if not booking and value.isdigit():
        booking = Booking.get_or_none(
            (Booking.id == int(value)) &
            (Booking.status == "confirmed")
        )

    if not booking:
        return f"Активное бронирование с booking_id={booking_id} не найдено"

    booking.status = "cancelled"
    booking.save()
    public_id = booking.booking_code or str(booking.id)
    return f"Бронирование booking_id={public_id} на {booking.date} в {booking.time} успешно отменено"


@tool
def transfer_to_manager(reason: str) -> str:
    """Предложить передачу диалога живому менеджеру.

    Используй когда не уверен в ответе, не понимаешь запрос, или гость просит связаться с человеком.
    ВАЖНО: после этого дождись явного согласия гостя ("да", "соедините", "передайте")
    и только затем вызывай transfer_to_manager_confirmed.

    Args:
        reason: Причина передачи менеджеру
    """
    logger.info(f"Предложение передачи менеджеру: {reason}")
    return (
        "MANAGER_TRANSFER_OFFERED: Предложи гостю перевод на менеджера и дождись согласия. "
        "Если гость согласен, вызови transfer_to_manager_confirmed."
    )


@tool
def transfer_to_manager_confirmed(reason: str) -> str:
    """Подтвердить передачу диалога менеджеру после явного согласия гостя.

    Args:
        reason: Причина передачи менеджеру
    """
    logger.info(f"Передача менеджеру подтверждена: {reason}")
    return "ESCALATED: Диалог передан менеджеру"


@tool
def retrieve_knowledge(query: str, top_k: int = 7, source: str = "") -> str:
    """Найти релевантные фрагменты знаний (меню/FAQ/политики) через RAG.

    Args:
        query: Поисковый запрос
        top_k: Сколько фрагментов вернуть (рекомендуется 5-7)
        source: Фильтр по названию документа, например "menu" или "faq"
    """
    restaurant = Restaurant.get_or_none(Restaurant.id == 1)
    if not restaurant:
        return "RETRIEVAL_STATUS: NO_RESTAURANT"

    top_k = max(1, min(top_k, 10))
    source_filter = source.strip() or None

    snippets, status = _get_knowledge_manager().retrieve_context(
        restaurant=restaurant,
        query=query,
        top_k=top_k,
        source_title=source_filter,
    )

    if not snippets:
        return f"RETRIEVAL_STATUS: {status}\nRETRIEVED_CONTEXT: []"

    lines = []
    for idx, item in enumerate(snippets[:top_k], start=1):
        text = item["content"][:500].replace("\n", " ")
        lines.append(
            f"{idx}. score={item['score']:.3f} title={item['title']} source={item['source_path']} text={text}"
        )
    return "RETRIEVAL_STATUS: OK\nRETRIEVED_CONTEXT:\n" + "\n".join(lines)


TOOLS = [
    check_availability,
    create_booking,
    cancel_booking,
    retrieve_knowledge,
    transfer_to_manager,
    transfer_to_manager_confirmed,
]
