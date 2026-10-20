from functools import lru_cache
from sqlalchemy import MetaData, create_engine
from sqlalchemy.orm import DeclarativeBase, Session
from app.config import get_settings


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention={
        "ix": "ix_%(table_name)s_%(column_0_name)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    })


@lru_cache
def get_engine():
    return create_engine(get_settings().database_url.get_secret_value(), pool_pre_ping=True, connect_args={"connect_timeout": 5})


def get_db():
    with Session(get_engine()) as session:
        yield session
