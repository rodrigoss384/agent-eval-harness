"""Persistência SQLite simples, versionada e serializada."""

import asyncio
import json
from pathlib import Path

import aiosqlite


class SQLiteStore:
    """Autoridade durável para runs e futuras auditorias de bias."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        self._connection: aiosqlite.Connection | None = None
        self._write_lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Abre o banco e aplica a migração inicial de forma idempotente."""
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = await aiosqlite.connect(self._database_path)
        self._connection.row_factory = aiosqlite.Row
        await self._connection.execute("PRAGMA journal_mode=WAL")
        await self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS eval_runs (
                run_id TEXT PRIMARY KEY,
                case_id TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                verdict_json TEXT NOT NULL CHECK (json_valid(verdict_json))
            );
            CREATE INDEX IF NOT EXISTS idx_eval_runs_created_at
                ON eval_runs(created_at DESC);
            CREATE TABLE IF NOT EXISTS bias_audits (
                audit_id TEXT PRIMARY KEY,
                experiment TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                result_json TEXT NOT NULL CHECK (json_valid(result_json))
            );
            CREATE TABLE IF NOT EXISTS eval_sessions (
                session_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                session_json TEXT NOT NULL CHECK (json_valid(session_json))
            );
            CREATE INDEX IF NOT EXISTS idx_eval_sessions_created_at
                ON eval_sessions(created_at DESC);
            CREATE TABLE IF NOT EXISTS session_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                event_json TEXT NOT NULL CHECK (json_valid(event_json)),
                FOREIGN KEY(session_id) REFERENCES eval_sessions(session_id)
            );
            CREATE INDEX IF NOT EXISTS idx_session_events_session_cursor
                ON session_events(session_id, event_id);
            CREATE TABLE IF NOT EXISTS datasets (
                dataset_id TEXT PRIMARY KEY,
                checksum TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                dataset_json TEXT NOT NULL CHECK (json_valid(dataset_json))
            );
            CREATE TABLE IF NOT EXISTS bias_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                audit_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                event_json TEXT NOT NULL CHECK (json_valid(event_json)),
                FOREIGN KEY(audit_id) REFERENCES bias_audits(audit_id)
            );
            CREATE INDEX IF NOT EXISTS idx_bias_events_cursor
                ON bias_events(audit_id, event_id);
            INSERT OR IGNORE INTO schema_migrations(version, applied_at)
            VALUES (1, CURRENT_TIMESTAMP);
            INSERT OR IGNORE INTO schema_migrations(version, applied_at)
            VALUES (2, CURRENT_TIMESTAMP);
            INSERT OR IGNORE INTO schema_migrations(version, applied_at)
            VALUES (3, CURRENT_TIMESTAMP);
            """
        )
        await self._connection.commit()

    def _ready_connection(self) -> aiosqlite.Connection:
        if self._connection is None:
            raise RuntimeError("O armazenamento SQLite ainda não foi inicializado.")
        return self._connection

    async def save_run(self, run_id: str, case_id: str, verdict_json: str) -> None:
        """Persiste atomicamente um veredito já validado."""
        connection = self._ready_connection()
        async with self._write_lock:
            await connection.execute(
                "INSERT INTO eval_runs(run_id, case_id, verdict_json) VALUES (?, ?, ?)",
                (run_id, case_id, verdict_json),
            )
            await connection.commit()

    async def get_run(self, run_id: str) -> str | None:
        """Retorna o documento original do veredito."""
        connection = self._ready_connection()
        cursor = await connection.execute(
            "SELECT verdict_json FROM eval_runs WHERE run_id = ?", (run_id,)
        )
        row = await cursor.fetchone()
        await cursor.close()
        return None if row is None else str(row["verdict_json"])

    async def list_runs(self, limit: int, offset: int) -> list[str]:
        """Lista documentos do mais recente para o mais antigo."""
        connection = self._ready_connection()
        cursor = await connection.execute(
            """
            SELECT verdict_json FROM eval_runs
            ORDER BY created_at DESC, run_id DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
        rows = await cursor.fetchall()
        await cursor.close()
        return [str(row["verdict_json"]) for row in rows]

    async def save_session(self, session_id: str, status: str, session_json: str) -> None:
        """Cria ou atualiza atomicamente o snapshot de uma sessão live."""
        json.loads(session_json)
        connection = self._ready_connection()
        async with self._write_lock:
            await connection.execute(
                """
                INSERT INTO eval_sessions(session_id, status, session_json)
                VALUES (?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    status = excluded.status,
                    updated_at = CURRENT_TIMESTAMP,
                    session_json = excluded.session_json
                """,
                (session_id, status, session_json),
            )
            await connection.commit()

    async def get_session(self, session_id: str) -> str | None:
        """Obtém o snapshot atual de uma sessão."""
        connection = self._ready_connection()
        cursor = await connection.execute(
            "SELECT session_json FROM eval_sessions WHERE session_id = ?", (session_id,)
        )
        row = await cursor.fetchone()
        await cursor.close()
        return None if row is None else str(row["session_json"])

    async def list_sessions(self, limit: int = 20, offset: int = 0) -> list[str]:
        """Lista sessões recentes."""
        connection = self._ready_connection()
        cursor = await connection.execute(
            """SELECT session_json FROM eval_sessions
               ORDER BY created_at DESC, session_id DESC LIMIT ? OFFSET ?""",
            (limit, offset),
        )
        rows = await cursor.fetchall()
        await cursor.close()
        return [str(row["session_json"]) for row in rows]

    async def append_session_event(self, session_id: str, event_type: str, event_json: str) -> int:
        """Persiste um marco ordenado da sessão e devolve seu cursor."""
        json.loads(event_json)
        connection = self._ready_connection()
        async with self._write_lock:
            cursor = await connection.execute(
                "INSERT INTO session_events(session_id, event_type, event_json) VALUES (?, ?, ?)",
                (session_id, event_type, event_json),
            )
            await connection.commit()
            event_id = cursor.lastrowid
            await cursor.close()
        if event_id is None:
            raise RuntimeError("SQLite não retornou o cursor do evento.")
        return event_id

    async def list_session_events(self, session_id: str, after: int) -> list[dict[str, object]]:
        """Lista marcos posteriores ao cursor informado."""
        connection = self._ready_connection()
        cursor = await connection.execute(
            """SELECT event_id, event_type, created_at, event_json
               FROM session_events WHERE session_id = ? AND event_id > ? ORDER BY event_id""",
            (session_id, after),
        )
        rows = await cursor.fetchall()
        await cursor.close()
        return [
            {
                "event_id": int(row["event_id"]),
                "event_type": str(row["event_type"]),
                "created_at": str(row["created_at"]),
                "payload": json.loads(str(row["event_json"])),
            }
            for row in rows
        ]

    async def mark_running_sessions_interrupted(self) -> None:
        """Evita que um restart deixe trabalho inexistente marcado como ativo."""
        connection = self._ready_connection()
        async with self._write_lock:
            cursor = await connection.execute(
                """SELECT session_id, session_json FROM eval_sessions
                   WHERE status IN ('queued', 'running')"""
            )
            rows = await cursor.fetchall()
            await cursor.close()
            for row in rows:
                document = json.loads(str(row["session_json"]))
                document["status"] = "interrupted"
                document["error"] = "A execução foi interrompida pelo reinício do serviço."
                await connection.execute(
                    """UPDATE eval_sessions
                       SET status = 'interrupted', session_json = ?,
                           updated_at = CURRENT_TIMESTAMP
                       WHERE session_id = ?""",
                    (json.dumps(document, ensure_ascii=False), str(row["session_id"])),
                )
            await connection.commit()

    async def mark_running_bias_audits_interrupted(self) -> None:
        """Marca auditorias abandonadas pelo restart sem sugerir retomada."""
        connection = self._ready_connection()
        async with self._write_lock:
            cursor = await connection.execute("SELECT audit_id, result_json FROM bias_audits")
            rows = await cursor.fetchall()
            await cursor.close()
            for row in rows:
                document = json.loads(str(row["result_json"]))
                if document.get("status") not in {"queued", "running"}:
                    continue
                document["status"] = "interrupted"
                document["result"] = "inconclusive"
                document["error"] = "A auditoria foi interrompida pelo reinício do serviço."
                await connection.execute(
                    "UPDATE bias_audits SET result_json = ? WHERE audit_id = ?",
                    (json.dumps(document, ensure_ascii=False), str(row["audit_id"])),
                )
            await connection.commit()

    async def save_dataset(self, dataset_id: str, checksum: str, dataset_json: str) -> None:
        """Persiste um dataset validado e imutável pelo identificador."""
        json.loads(dataset_json)
        connection = self._ready_connection()
        async with self._write_lock:
            await connection.execute(
                "INSERT INTO datasets(dataset_id, checksum, dataset_json) VALUES (?, ?, ?)",
                (dataset_id, checksum, dataset_json),
            )
            await connection.commit()

    async def get_dataset(self, dataset_id: str) -> str | None:
        connection = self._ready_connection()
        cursor = await connection.execute(
            "SELECT dataset_json FROM datasets WHERE dataset_id = ?", (dataset_id,)
        )
        row = await cursor.fetchone()
        await cursor.close()
        return None if row is None else str(row["dataset_json"])

    async def list_datasets(self) -> list[str]:
        connection = self._ready_connection()
        cursor = await connection.execute(
            "SELECT dataset_json FROM datasets ORDER BY created_at DESC, dataset_id DESC"
        )
        rows = await cursor.fetchall()
        await cursor.close()
        return [str(row["dataset_json"]) for row in rows]

    async def save_bias_audit(self, audit_id: str, experiment: str, result_json: str) -> None:
        """Cria ou atualiza o snapshot de uma auditoria."""
        json.loads(result_json)
        connection = self._ready_connection()
        async with self._write_lock:
            await connection.execute(
                """INSERT INTO bias_audits(audit_id, experiment, result_json)
                   VALUES (?, ?, ?)
                   ON CONFLICT(audit_id) DO UPDATE SET result_json = excluded.result_json""",
                (audit_id, experiment, result_json),
            )
            await connection.commit()

    async def get_bias_audit(self, audit_id: str) -> str | None:
        connection = self._ready_connection()
        cursor = await connection.execute(
            "SELECT result_json FROM bias_audits WHERE audit_id = ?", (audit_id,)
        )
        row = await cursor.fetchone()
        await cursor.close()
        return None if row is None else str(row["result_json"])

    async def list_bias_audits(self, limit: int = 20, offset: int = 0) -> list[str]:
        connection = self._ready_connection()
        cursor = await connection.execute(
            """SELECT result_json FROM bias_audits
               ORDER BY created_at DESC, audit_id DESC LIMIT ? OFFSET ?""",
            (limit, offset),
        )
        rows = await cursor.fetchall()
        await cursor.close()
        return [str(row["result_json"]) for row in rows]

    async def append_bias_event(self, audit_id: str, event_type: str, event_json: str) -> int:
        json.loads(event_json)
        connection = self._ready_connection()
        async with self._write_lock:
            cursor = await connection.execute(
                "INSERT INTO bias_events(audit_id, event_type, event_json) VALUES (?, ?, ?)",
                (audit_id, event_type, event_json),
            )
            await connection.commit()
            event_id = cursor.lastrowid
            await cursor.close()
        if event_id is None:
            raise RuntimeError("SQLite não retornou o cursor do evento de auditoria.")
        return event_id

    async def list_bias_events(self, audit_id: str, after: int) -> list[dict[str, object]]:
        connection = self._ready_connection()
        cursor = await connection.execute(
            """SELECT event_id, event_type, created_at, event_json FROM bias_events
               WHERE audit_id = ? AND event_id > ? ORDER BY event_id""",
            (audit_id, after),
        )
        rows = await cursor.fetchall()
        await cursor.close()
        return [
            {
                "event_id": int(row["event_id"]),
                "event_type": str(row["event_type"]),
                "created_at": str(row["created_at"]),
                "payload": json.loads(str(row["event_json"])),
            }
            for row in rows
        ]

    async def close(self) -> None:
        """Fecha a conexão sem efeitos se ela já estiver fechada."""
        if self._connection is not None:
            await self._connection.close()
            self._connection = None
