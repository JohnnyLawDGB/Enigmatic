"""Opt-in, lightweight persistence for inscription metadata."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable

from enigmatic_dgb.ordinals.inscriptions import InscriptionMetadata, InscriptionPayload
from enigmatic_dgb.ordinals.indexer import OrdinalLocation


class OrdinalIndexStore:
    """Interface for storing and retrieving inscription payloads."""

    def add_inscription(self, payload: InscriptionPayload, address: str | None = None) -> None:
        raise NotImplementedError

    def get_by_txid(self, txid: str) -> list[InscriptionPayload]:
        raise NotImplementedError

    def all(self, limit: int | None = None) -> list[InscriptionPayload]:
        raise NotImplementedError

    def by_address(self, address: str, limit: int | None = None) -> list[InscriptionPayload]:
        raise NotImplementedError


class SQLiteOrdinalIndexStore(OrdinalIndexStore):
    """Persist inscriptions to a local SQLite database."""

    DEFAULT_DB_PATH = Path.home() / ".enigmatic-dgb" / "ordinals.sqlite"

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path else self.DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS inscriptions (
                txid TEXT NOT NULL,
                vout INTEGER NOT NULL,
                height INTEGER,
                protocol TEXT,
                content_type TEXT,
                length INTEGER,
                decoded_text TEXT,
                address TEXT,
                created_at INTEGER DEFAULT (strftime('%s', 'now')),
                PRIMARY KEY (txid, vout)
            )
            """
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_inscriptions_address ON inscriptions(address)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_inscriptions_height ON inscriptions(height)")
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "SQLiteOrdinalIndexStore":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # pragma: no cover - convenience
        self.close()

    def add_inscription(self, payload: InscriptionPayload, address: str | None = None) -> None:
        metadata = payload.metadata
        length = metadata.length if metadata.length is not None else len(payload.raw_payload or b"")
        decoded_text = payload.decoded_text
        if decoded_text and len(decoded_text) > 240:
            decoded_text = decoded_text[:240]
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO inscriptions (txid, vout, height, protocol, content_type, length, decoded_text, address)
            VALUES (:txid, :vout, :height, :protocol, :content_type, :length, :decoded_text, :address)
            """,
            {
                "txid": metadata.location.txid,
                "vout": metadata.location.vout,
                "height": metadata.location.height,
                "protocol": metadata.protocol,
                "content_type": metadata.content_type,
                "length": length,
                "decoded_text": decoded_text,
                "address": address,
            },
        )
        self.conn.commit()

    def get_by_txid(self, txid: str) -> list[InscriptionPayload]:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT txid, vout, height, protocol, content_type, length, decoded_text, address FROM inscriptions WHERE txid = ? ORDER BY vout",
            (txid,),
        )
        rows = cursor.fetchall()
        return [self._row_to_payload(row) for row in rows]

    def all(self, limit: int | None = None) -> list[InscriptionPayload]:
        cursor = self.conn.cursor()
        sql = (
            "SELECT txid, vout, height, protocol, content_type, length, decoded_text, address FROM inscriptions "
            "ORDER BY (height IS NULL), height DESC, txid, vout"
        )
        if limit is not None:
            sql += " LIMIT ?"
            cursor.execute(sql, (limit,))
        else:
            cursor.execute(sql)
        rows = cursor.fetchall()
        return [self._row_to_payload(row) for row in rows]

    def by_address(self, address: str, limit: int | None = None) -> list[InscriptionPayload]:
        cursor = self.conn.cursor()
        sql = (
            "SELECT txid, vout, height, protocol, content_type, length, decoded_text, address FROM inscriptions "
            "WHERE address = ? ORDER BY (height IS NULL), height DESC, txid, vout"
        )
        params: Iterable[object]
        params = (address,)
        if limit is not None:
            sql += " LIMIT ?"
            params = (address, limit)
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        return [self._row_to_payload(row) for row in rows]

    def _row_to_payload(self, row: sqlite3.Row) -> InscriptionPayload:
        location = OrdinalLocation(
            txid=row["txid"],
            vout=row["vout"],
            height=row["height"],
            ordinal_hint=None,
            tags=set(),
        )
        metadata = InscriptionMetadata(
            location=location,
            protocol=row["protocol"],
            version=None,
            content_type=row["content_type"],
            length=row["length"],
            codec=None,
            notes=row["address"],
        )
        return InscriptionPayload(metadata=metadata, raw_payload=b"", decoded_text=row["decoded_text"], decoded_json=None)


__all__ = ["OrdinalIndexStore", "SQLiteOrdinalIndexStore"]
