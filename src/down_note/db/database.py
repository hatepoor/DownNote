"""SQLite 连接管理（SQLAlchemy ORM）、建表与轻量迁移。

短会话策略：每次操作开一个 Session（本地 SQLite 开销可忽略），随请求创建与关闭，
天然规避多线程共享连接问题。WAL 与外键约束经 connect 钩子对每个连接生效；
schema 版本用 PRAGMA user_version 记录，建表由 create_all 幂等完成。
对应开发文档：docx/v0.1.0/modules/02-数据库与配置.md
"""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from down_note import config
from down_note.db import models

SCHEMA_VERSION = 7

_engine: Engine | None = None


def resetEngine() -> None:
    """丢弃全局引擎缓存（测试在切换数据目录后必须调用，避免串库）。"""
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = None


def getEngine(dbPath: Path | str | None = None) -> Engine:
    """默认路径的引擎全局复用；显式传路径（测试）时每次新建。"""
    global _engine
    if dbPath is None and _engine is not None:
        return _engine
    path = Path(dbPath) if dbPath is not None else config.getDatabaseFile()
    # SQLite URL 需要正斜杠（Windows 反斜杠会解析失败）
    engine = create_engine(
            f"sqlite:///{path.as_posix()}",
            connect_args={"check_same_thread": False},
        )

    @event.listens_for(engine, "connect")
    def _setSqlitePragmas(dbapiConnection: object, _connectionRecord: object) -> None:
        cursor = dbapiConnection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute("PRAGMA journal_mode = WAL")
        cursor.close()

    if dbPath is None:
        _engine = engine
    return engine


@contextmanager
def getDb(dbPath: Path | str | None = None) -> Iterator[Session]:
    # expire_on_commit=False：提交后对象仍可读取（短会话模式下响应组装在会话外进行）
    session = sessionmaker(bind=getEngine(dbPath), expire_on_commit=False)()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def ensureSchema(dbPath: Path | str | None = None) -> None:
    engine = getEngine(dbPath)
    models.Base.metadata.create_all(engine)
    with engine.connect() as conn:
        version = conn.execute(text("PRAGMA user_version")).scalar() or 0
        if version < 3:
            _migrateToV3(conn)
        if version < 4:
            _migrateToV4(conn)
        if version < 5:
            _migrateToV5(conn)
        if version < 6:
            _migrateToV6(conn)
        if version < 7:
            _migrateToV7(conn)
        conn.execute(text(f"PRAGMA user_version = {SCHEMA_VERSION}"))
        conn.commit()


def _migrateToV3(conn) -> None:
    """v2 → v3：entries 增加 kind 列（旧库补列并回填 'entry'；新库 create_all 已带）。"""
    columns = {row[1] for row in conn.execute(text("PRAGMA table_info(entries)"))}
    if "kind" not in columns:
        conn.execute(
                text("ALTER TABLE entries ADD COLUMN kind VARCHAR NOT NULL DEFAULT 'entry'")
            )


def _migrateToV4(conn) -> None:
    """v3 → v4：整合日记正文格式 v2——每条前缀 HH:MM。"""
    _remergeDailyDigests(conn)


def _migrateToV5(conn) -> None:
    """v4 → v5：整合日记条目之间加分隔线——多段长文下条目边界依然分明。"""
    _remergeDailyDigests(conn)


def _migrateToV6(conn) -> None:
    """v5 → v6：整合日记正文回归纯文本（时间戳与分隔线撤除）；
    每条的心情改由日页按条展示，正文不再承担版式。"""
    _remergeDailyDigests(conn)


def _migrateToV7(conn) -> None:
    """v6 → v7：entries 增加 analyze_state 列（旧库补列并按 analyzed 回填；新库 create_all 已带）。

    analyzed 保留为兼容镜像（state == 'done' 时为 1），回填幂等、可重复执行。
    """
    columns = {row[1] for row in conn.execute(text("PRAGMA table_info(entries)"))}
    if "analyze_state" not in columns:
        conn.execute(
                text("ALTER TABLE entries ADD COLUMN analyze_state VARCHAR NOT NULL DEFAULT 'pending'")
            )
    conn.execute(text("UPDATE entries SET analyze_state = 'done' WHERE analyzed = 1"))
    conn.execute(text("UPDATE entries SET analyze_state = 'pending' WHERE analyzed = 0"))


def _remergeDailyDigests(conn) -> None:
    """把所有已整合的日子按当天原始条目重拼（整合日记是纯程序派生数据，
    原始条目、心情记录与记忆沉淀标记均不动）。"""
    days = [
            row[0]
            for row in conn.execute(
                    text("SELECT DISTINCT substr(created_at, 1, 10) FROM entries WHERE kind = 'daily'")
                ).fetchall()
        ]
    for day in days:
        blocks = [
                (row[0], row[1])
                for row in conn.execute(
                        text(
                            "SELECT created_at, content FROM entries "
                            "WHERE kind = 'entry' AND substr(created_at, 1, 10) = :day "
                            "ORDER BY created_at, id"
                        ),
                        {"day": day},
                    ).fetchall()
                if row[1]
            ]
        if not blocks:
            continue
        conn.execute(
                text(
                    "UPDATE entries SET content = :content "
                    "WHERE kind = 'daily' AND substr(created_at, 1, 10) = :day"
                ),
                {"content": models.mergeDayBlocks(blocks), "day": day},
            )
