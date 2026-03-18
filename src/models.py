from datetime import datetime
from peewee import (
    Model, IntegerField, CharField, TextField, DateTimeField,
    BooleanField, ForeignKeyField, TimeField
)

from src.database import db


class BaseModel(Model):
    class Meta:
        database = db


class Restaurant(BaseModel):
    name = CharField(max_length=255)
    address = CharField(max_length=500)
    phone = CharField(max_length=50, null=True)
    telegram_account = CharField(max_length=100, unique=True)
    opening_time = TimeField(default="12:00")
    closing_time = TimeField(default="23:00")
    cuisine_type = CharField(max_length=255, default="европейская")
    average_check = CharField(max_length=100, default="2000-3000 рублей")
    features = TextField(null=True)
    system_prompt = TextField(null=True)
    created_at = DateTimeField(default=datetime.utcnow)


class Table(BaseModel):
    restaurant = ForeignKeyField(Restaurant, backref="tables")
    table_number = IntegerField()
    capacity = IntegerField()
    is_active = BooleanField(default=True)


class Booking(BaseModel):
    table = ForeignKeyField(Table, backref="bookings")
    guest_name = CharField(max_length=255)
    phone = CharField(max_length=50)
    date = CharField(max_length=10)
    time = CharField(max_length=5)
    guests_count = IntegerField()
    status = CharField(max_length=20, default="confirmed")
    created_at = DateTimeField(default=datetime.utcnow)


class User(BaseModel):
    restaurant = ForeignKeyField(Restaurant, backref="users", null=True)
    created_at = DateTimeField(default=datetime.utcnow)
    is_escalated = BooleanField(default=False)


class Message(BaseModel):
    user = ForeignKeyField(User, backref="messages")
    role = CharField(max_length=50)
    content = TextField()
    created_at = DateTimeField(default=datetime.utcnow)
