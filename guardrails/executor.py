from __future__ import annotations
import sqlite3
from dataclasses import dataclass
from typing import Optional
from .core import SQLGuardrails, GuardrailResult, Verdict
from .text_to_sql import TextToSQLBackend

@dataclass
class ExecutionResult:
    nl_query: str
    guardrail: GuardrailResult
    executed: bool
    rows: Optional[list[tuple]] = None
    columns: Optional[list[str]] = None
    error: Optional[str] = None

class SafeSQLExecutor:
# takes a text-to-SQL backend then a live DB connection and then a SQLGuardrails instance, and guarantees nothing reaches the DB without passing the check first.
    def __init__(
        self,
        connection: sqlite3.Connection,
        text_to_sql: TextToSQLBackend,
        guardrails: SQLGuardrails,
        confirm_warn: bool = False,
    ):
        self.connection = connection
        self.text_to_sql = text_to_sql
        self.guardrails = guardrails
        self.confirm_warn = confirm_warn

    def ask(self, nl_query: str, force: bool = False) -> ExecutionResult:
        sql = self.text_to_sql.generate(nl_query)
        verdict = self.guardrails.check(sql)

        if verdict.verdict == Verdict.BLOCK:
            return ExecutionResult(nl_query, verdict, executed=False)

        if verdict.verdict == Verdict.WARN and self.confirm_warn and not force:
            return ExecutionResult(
                nl_query, verdict, executed=False,
                error="Requires confirmation: call ask(..., force=True) to proceed.",
            )

        try:
            cur = self.connection.cursor()
            cur.execute(verdict.sql)
            if cur.description:
                columns = [d[0] for d in cur.description]
                rows = cur.fetchall()
            else:
                columns, rows = [], []
                self.connection.commit()
            return ExecutionResult(nl_query, verdict, executed=True, rows=rows, columns=columns)
        except Exception as e:
            self.connection.rollback()
            return ExecutionResult(nl_query, verdict, executed=False, error=str(e))
