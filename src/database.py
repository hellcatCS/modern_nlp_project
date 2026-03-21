import hashlib
from pathlib import Path
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
    from src.models import (
        Restaurant,
        Table,
        Booking,
        User,
        Message,
        KnowledgeSet,
        KnowledgeDocument,
        KnowledgeChunk,
    )

    db.connect()
    db.create_tables(
        [
            Restaurant,
            KnowledgeSet,
            KnowledgeDocument,
            KnowledgeChunk,
            Table,
            User,
            Message,
        ],
        safe=True,
    )
    if not db.table_exists("booking"):
        Booking.create_table(safe=True)
    _ensure_booking_schema()
    _seed_default_restaurant()
    _seed_sample_knowledge()


def _ensure_booking_schema():
    existing_columns = {
        row[0]
        for row in db.execute_sql(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'booking'
            """
        ).fetchall()
    }

    if "booking_code" not in existing_columns:
        db.execute_sql("ALTER TABLE booking ADD COLUMN booking_code VARCHAR(7)")

    db.execute_sql(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS booking_booking_code_unique
        ON booking (booking_code)
        WHERE booking_code IS NOT NULL
        """
    )


def _seed_default_restaurant():
    from src.models import Restaurant, Table

    if Restaurant.select().count() > 0:
        return

    restaurant = Restaurant.create(
        name="Гастроном",
        address="ул. Пушкина, д. 10",
        phone="+7 (999) 123-45-67",
        telegram_account="gastronom_manager",
        opening_time="12:00",
        closing_time="23:00",
        cuisine_type="европейская, авторская",
        average_check="2500-3500 рублей",
        features="живая музыка по пятницам и субботам, летняя веранда"
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


def _seed_sample_knowledge():
    from src.models import Restaurant, KnowledgeSet, KnowledgeDocument

    restaurant = Restaurant.get_or_none(Restaurant.id == 1)
    if not restaurant:
        return

    if KnowledgeSet.select().where(KnowledgeSet.restaurant == restaurant).count() > 0:
        return

    default_set = KnowledgeSet.create(
        restaurant=restaurant,
        name="Основное меню v1",
        description="Синтетический sample-набор знаний: меню, FAQ, политики.",
        is_active=True,
    )

    root_dir = Path(__file__).resolve().parent.parent
    sample_dir = root_dir / "sample_knowledge"
    sample_files = [
        sample_dir / "menu.md",
        sample_dir / "faq.md",
        sample_dir / "policies.json",
    ]

    for source_path in sample_files:
        if not source_path.exists():
            continue
        content = source_path.read_text(encoding="utf-8")
        KnowledgeDocument.create(
            knowledge_set=default_set,
            title=source_path.stem,
            source_type=source_path.suffix.lower().lstrip("."),
            source_path=str(source_path),
            content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
            content=content,
        )
