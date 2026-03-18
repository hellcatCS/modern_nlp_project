from peewee import PostgresqlDatabase
from urllib.parse import urlparse

from src.config import settings

parsed = urlparse(settings.database_url)
db = PostgresqlDatabase(
    parsed.path[1:],
    user=parsed.username,
    password=parsed.password,
    host=parsed.hostname,
    port=parsed.port
)


def init_db():
    from src.models import Restaurant, Table, Booking, User, Message
    db.connect()
    db.create_tables([Restaurant, Table, Booking, User, Message])
    _seed_default_restaurant()


def _seed_default_restaurant():
    from src.models import Restaurant, Table

    if Restaurant.select().count() > 0:
        return

    restaurant = Restaurant.create(
        name="Гастроном",
        address="ул. Пушкина, д. 10",
        phone="+7 (999) 123-45-67",
        telegram_account="gastronom_manager"
    )

    tables_config = [
        (2, 5),
        (4, 8),
        (6, 3),
    ]

    table_num = 1
    for capacity, count in tables_config:
        for _ in range(count):
            Table.create(
                restaurant=restaurant,
                table_number=table_num,
                capacity=capacity
            )
            table_num += 1
