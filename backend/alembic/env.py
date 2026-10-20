from alembic import context
from app.database import Base, get_engine
from app.config import get_settings
from app import models  # register model metadata

from app.ondc import models as ondc_models

target_metadata = Base.metadata

if context.is_offline_mode():
    context.configure(url=get_settings().database_url.get_secret_value(),
        target_metadata=target_metadata, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()
else:
    with get_engine().connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
