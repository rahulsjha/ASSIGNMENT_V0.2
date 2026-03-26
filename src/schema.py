from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class SchemaInfo:
    table_name: str
    columns: list[str]
    column_types: dict[str, str] = field(default_factory=dict)

    def to_prompt_context(self) -> dict:
        return {
            "table": self.table_name,
            "columns": self.columns,
            "column_types": self.column_types,
        }


class SQLiteSchemaIntrospector:
    def __init__(self, db_path: str | Path, *, table_name: str) -> None:
        self.db_path = Path(db_path)
        self.table_name = table_name

    def load(self) -> SchemaInfo:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute(f'PRAGMA table_info("{self.table_name}")')
            rows = cur.fetchall()

        columns: list[str] = []
        column_types: dict[str, str] = {}
        for row in rows:
            # (cid, name, type, notnull, dflt_value, pk)
            if len(row) >= 3:
                name = str(row[1])
                typ = str(row[2])
                columns.append(name)
                column_types[name] = typ

        return SchemaInfo(table_name=self.table_name, columns=columns, column_types=column_types)
