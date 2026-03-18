import logging
from langchain_core.tools import tool

from src.models import Restaurant, Table, Booking

logger = logging.getLogger(__name__)

BOOKING_DURATION_HOURS = 2


def find_available_table(restaurant_id: int, date: str, time: str, guests_count: int):
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
                (Booking.date == date) &
                (Booking.time == time) &
                (Booking.status == "confirmed")
            )
            .count()
        )
        if existing == 0:
            return table

    return None


def get_available_tables_info(restaurant_id: int, date: str, time: str) -> dict:
    result = {2: 0, 4: 0, 6: 0}

    tables = (
        Table
        .select()
        .where(
            (Table.restaurant == restaurant_id) &
            (Table.is_active == True)
        )
    )

    for table in tables:
        existing = (
            Booking
            .select()
            .where(
                (Booking.table == table) &
                (Booking.date == date) &
                (Booking.time == time) &
                (Booking.status == "confirmed")
            )
            .count()
        )
        if existing == 0 and table.capacity in result:
            result[table.capacity] += 1

    return result


@tool
def check_availability(date: str, time: str) -> str:
    """Проверить наличие свободных столиков на указанную дату и время.

    Args:
        date: Дата (YYYY-MM-DD)
        time: Время (HH:MM)
    """
    restaurant = Restaurant.get_or_none(Restaurant.id == 1)
    if not restaurant:
        return "Ресторан не найден"

    available = get_available_tables_info(restaurant.id, date, time)
    total = sum(available.values())

    if total == 0:
        return f"К сожалению, на {date} в {time} свободных столиков нет"

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

    table = find_available_table(restaurant.id, date, time, guests_count)

    if not table:
        available = get_available_tables_info(restaurant.id, date, time)
        if sum(available.values()) == 0:
            return f"К сожалению, на {date} в {time} нет свободных столиков. Попробуйте выбрать другое время."

        return f"Нет столика на {guests_count} гостей. Доступны столики: на 2 ({available[2]}), на 4 ({available[4]}), на 6 ({available[6]})"

    booking = Booking.create(
        table=table,
        guest_name=guest_name,
        phone=phone,
        date=date,
        time=time,
        guests_count=guests_count
    )

    return f"Бронирование подтверждено! Столик №{table.table_number} на {guests_count} гостей, {date} в {time}. Номер брони: {booking.id}"


@tool
def cancel_booking(phone: str, date: str) -> str:
    """Отменить существующее бронирование.

    Args:
        phone: Номер телефона, на который было сделано бронирование
        date: Дата бронирования для отмены (YYYY-MM-DD)
    """
    logger.info(f"Отмена бронирования: {phone}, {date}")

    booking = Booking.get_or_none(
        (Booking.phone == phone) &
        (Booking.date == date) &
        (Booking.status == "confirmed")
    )

    if not booking:
        return f"Бронирование на {date} по номеру {phone} не найдено"

    booking.status = "cancelled"
    booking.save()

    return f"Бронирование на {date} в {booking.time} успешно отменено"


@tool
def transfer_to_manager(reason: str) -> str:
    """Передать диалог живому менеджеру. Используй когда не уверен в ответе, не понимаешь запрос, или гость просит связаться с человеком.

    Args:
        reason: Причина передачи менеджеру
    """
    logger.info(f"Передача менеджеру: {reason}")
    return "ESCALATED: Диалог передан менеджеру"


TOOLS = [check_availability, create_booking, cancel_booking, transfer_to_manager]
