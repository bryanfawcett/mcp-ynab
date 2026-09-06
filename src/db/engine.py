import contextvars

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import event, inspect, text

from src.db.tables import Base

# Keyed by db_path, so multi-tenant mode (src/server/http.py) can give each
# tenant its own isolated SQLite file without any changes to the cache/delta
# layer above: they always call get_session() with no arguments, and it
# resolves to whichever path is current for this request (see _current_db_path).
_engines: dict[str, AsyncEngine] = {}
_session_factories: dict[str, async_sessionmaker[AsyncSession]] = {}
_default_db_path: str | None = None

# Set by callers that need to scope get_session() to a specific tenant's
# database for the duration of a request (see use_db_path). Falls back to
# _default_db_path — the single database used by stdio mode and single-tenant
# HTTP deployments — when unset.
_current_db_path: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_db_path", default=None
)


def _set_wal_mode(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


async def init_db(db_path: str) -> None:
    """Idempotent per db_path: safe to call on every request."""
    global _default_db_path
    if _default_db_path is None:
        _default_db_path = db_path
    if db_path in _engines:
        return

    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False)
    event.listen(engine.sync_engine, "connect", _set_wal_mode)

    # Migrate: drop stale cache tables — cache rebuilds automatically
    async with engine.begin() as conn:
        def _migrate_cache_tables(connection):
            insp = inspect(connection)
            # Drop old "cached_entities" (renamed to "cached_entity")
            if insp.has_table("cached_entities"):
                connection.execute(text("DROP TABLE cached_entities"))
            # Drop tables with old budget_id column
            for table in ("cached_entity", "server_knowledge"):
                if insp.has_table(table):
                    columns = [c["name"] for c in insp.get_columns(table)]
                    if "budget_id" in columns:
                        connection.execute(text(f"DROP TABLE {table}"))

        await conn.run_sync(_migrate_cache_tables)
        await conn.run_sync(Base.metadata.create_all)

    _engines[db_path] = engine
    _session_factories[db_path] = async_sessionmaker(engine, expire_on_commit=False)


def current_db_path() -> str | None:
    """The db_path get_session() will use right now, or None if none is set yet."""
    return _current_db_path.get() or _default_db_path


def use_db_path(db_path: str) -> contextvars.Token:
    """Scope get_session() to db_path for the current asyncio task.

    Reset with reset_db_path(token) once the caller is done (e.g. at the end
    of a request) — a plain contextvars.Token, not a context manager, since
    the caller (an ASGI middleware) needs to hold it across an await.
    """
    return _current_db_path.set(db_path)


def reset_db_path(token: contextvars.Token) -> None:
    _current_db_path.reset(token)


def get_session() -> AsyncSession:
    path = current_db_path()
    if path is None or path not in _session_factories:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _session_factories[path]()


async def close_db() -> None:
    global _default_db_path
    for engine in _engines.values():
        await engine.dispose()
    _engines.clear()
    _session_factories.clear()
    _default_db_path = None
