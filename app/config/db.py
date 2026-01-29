from __future__ import annotations

import logging
import os
import time
from contextlib import contextmanager
from datetime import date, datetime
from typing import Any, Iterable

try:
    import oracledb
except Exception as exc:  # pragma: no cover - 런타임 환경에서 확인
    oracledb = None
    _oracle_import_error = exc
else:
    _oracle_import_error = None


def _get_dsn() -> str:
    dsn = os.getenv("ORACLE_DSN")
    if dsn and dsn.startswith("jdbc:oracle:thin:@"):
        return dsn.replace("jdbc:oracle:thin:@", "")

    host = os.getenv("ORACLE_HOST", "")
    port = os.getenv("ORACLE_PORT", "1521")
    service = os.getenv("ORACLE_SERVICE", "")
    if not host or not service:
        raise RuntimeError("ORACLE_HOST/ORACLE_SERVICE가 설정되지 않았습니다.")
    return f"{host}:{port}/{service}"


@contextmanager
def get_connection() -> Iterable[Any]:
    if oracledb is None:
        raise RuntimeError(f"oracledb 모듈을 불러올 수 없습니다: {_oracle_import_error}")

    user = os.getenv("ORACLE_USER")
    password = os.getenv("ORACLE_PASSWORD")
    if not user or not password:
        raise RuntimeError("ORACLE_USER/ORACLE_PASSWORD가 설정되지 않았습니다.")

    logger = logging.getLogger("db")
    connect_timeout = int(os.getenv("ORACLE_CONNECT_TIMEOUT_SECONDS", "5") or "5")
    call_timeout_ms = int(os.getenv("ORACLE_CALL_TIMEOUT_MS", "10000") or "10000")
    start = time.monotonic()
    try:
        conn = oracledb.connect(
            user=user,
            password=password,
            dsn=_get_dsn(),
            timeout=connect_timeout,
        )
    except TypeError:
        logger.warning("oracledb.connect가 timeout 인자를 지원하지 않습니다. 기본값으로 연결합니다.")
        conn = oracledb.connect(user=user, password=password, dsn=_get_dsn())
    conn.call_timeout = call_timeout_ms
    logger.info(
        "DB 연결 성공 elapsed=%.2fs call_timeout_ms=%s",
        time.monotonic() - start,
        call_timeout_ms,
    )
    try:
        yield conn
    finally:
        conn.close()


def fetch_all(query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    logger = logging.getLogger("db")
    start = time.monotonic()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params or {})
        rows = cursor.fetchall()
        columns = [col[0].lower() for col in cursor.description]
    logger.info("DB fetch_all rows=%s elapsed=%.2fs", len(rows), time.monotonic() - start)
    return [_row_to_dict(columns, row) for row in rows]


def fetch_one(query: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
    logger = logging.getLogger("db")
    start = time.monotonic()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params or {})
        row = cursor.fetchone()
        columns = [col[0].lower() for col in cursor.description] if row else []
    logger.info("DB fetch_one hit=%s elapsed=%.2fs", row is not None, time.monotonic() - start)
    return _row_to_dict(columns, row) if row else None


def _row_to_dict(columns: list[str], row: tuple[Any, ...]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for idx, col in enumerate(columns):
        result[col] = _normalize_value(row[idx])
    return result


def _normalize_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value
