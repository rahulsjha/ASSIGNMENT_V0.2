from __future__ import annotations

import sqlite3
import time
import uuid
from pathlib import Path

from src.llm_client import OpenRouterLLMClient, build_default_llm_client
from src.schema import SQLiteSchemaIntrospector
from src.sql_validation import SQLValidator
from src.observability import get_logger
from src.types import (
    SQLValidationOutput,
    SQLExecutionOutput,
    PipelineOutput,
)


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = BASE_DIR / "data" / "gaming_mental_health.sqlite"
DEFAULT_TABLE_NAME = "gaming_mental_health"


class SQLiteExecutor:
    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH, *, max_rows: int = 100) -> None:
        self.db_path = Path(db_path)
        self.max_rows = max_rows

    def _connect_readonly(self) -> sqlite3.Connection:
        """Best-effort read-only connection.

        Uses SQLite URI mode=ro when supported; falls back to regular connect.
        """
        try:
            return sqlite3.connect(f"file:{self.db_path.as_posix()}?mode=ro", uri=True)
        except Exception:
            return sqlite3.connect(self.db_path)

    def run(self, sql: str | None) -> SQLExecutionOutput:
        start = time.perf_counter()
        error = None
        rows = []
        row_count = 0

        if sql is None:
            return SQLExecutionOutput(
                rows=[],
                row_count=0,
                timing_ms=(time.perf_counter() - start) * 1000,
                error=None,
            )

        try:
            with self._connect_readonly() as conn:
                try:
                    conn.execute("PRAGMA query_only = ON")
                except Exception:
                    pass
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                cur.execute(sql)
                rows = [dict(r) for r in cur.fetchmany(self.max_rows)]
                row_count = len(rows)
        except Exception as exc:
            error = str(exc)
            rows = []
            row_count = 0

        return SQLExecutionOutput(
            rows=rows,
            row_count=row_count,
            timing_ms=(time.perf_counter() - start) * 1000,
            error=error,
        )


class AnalyticsPipeline:
    def __init__(
        self,
        db_path: str | Path = DEFAULT_DB_PATH,
        llm_client: OpenRouterLLMClient | None = None,
        *,
        table_name: str = DEFAULT_TABLE_NAME,
    ) -> None:
        self.db_path = Path(db_path)
        self.table_name = table_name
        self.llm = llm_client or build_default_llm_client()
        self.executor = SQLiteExecutor(self.db_path)
        self._logger = get_logger(__name__)
        self._schema = SQLiteSchemaIntrospector(self.db_path, table_name=self.table_name).load()

    def run(self, question: str, request_id: str | None = None) -> PipelineOutput:
        start = time.perf_counter()
        request_id = request_id or uuid.uuid4().hex
        self._logger.info("pipeline_start", extra={"request_id": request_id})

        # Stage 1: SQL Generation
        sql_gen_output = self.llm.generate_sql(question, self._schema.to_prompt_context())
        sql = sql_gen_output.sql

        # Stage 2: SQL Validation
        validation_output = SQLValidator.validate(
            sql,
            db_path=self.db_path,
            table_name=self.table_name,
            allowed_columns=set(self._schema.columns),
        )
        if not validation_output.is_valid:
            sql = None
        else:
            sql = validation_output.validated_sql

        # Stage 3: SQL Execution
        execution_output = self.executor.run(sql)
        rows = execution_output.rows

        # Stage 4: Answer Generation
        answer_output = self.llm.generate_answer(question, sql, rows)

        # Determine status
        status = "success"
        if sql_gen_output.sql is None and sql_gen_output.error:
            status = "unanswerable"
        elif not validation_output.is_valid:
            status = "invalid_sql"
        elif execution_output.error:
            status = "error"
        elif sql is None:
            status = "unanswerable"

        # Build timings aggregate
        timings = {
            "sql_generation_ms": sql_gen_output.timing_ms,
            "sql_validation_ms": validation_output.timing_ms,
            "sql_execution_ms": execution_output.timing_ms,
            "answer_generation_ms": answer_output.timing_ms,
            "total_ms": (time.perf_counter() - start) * 1000,
        }

        # Build total LLM stats
        total_llm_stats = {
            "llm_calls": sql_gen_output.llm_stats.get("llm_calls", 0) + answer_output.llm_stats.get("llm_calls", 0),
            "prompt_tokens": sql_gen_output.llm_stats.get("prompt_tokens", 0) + answer_output.llm_stats.get("prompt_tokens", 0),
            "completion_tokens": sql_gen_output.llm_stats.get("completion_tokens", 0) + answer_output.llm_stats.get("completion_tokens", 0),
            "total_tokens": sql_gen_output.llm_stats.get("total_tokens", 0) + answer_output.llm_stats.get("total_tokens", 0),
            "model": sql_gen_output.llm_stats.get("model", "unknown"),
        }

        return PipelineOutput(
            status=status,
            question=question,
            request_id=request_id,
            sql_generation=sql_gen_output,
            sql_validation=validation_output,
            sql_execution=execution_output,
            answer_generation=answer_output,
            sql=sql,
            rows=rows,
            answer=answer_output.answer,
            timings=timings,
            total_llm_stats=total_llm_stats,
        )