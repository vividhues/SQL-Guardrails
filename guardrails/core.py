from __future__ import annotations
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import sqlglot
from sqlglot import exp


class Verdict(str, Enum):
    ALLOW = "ALLOW"
    WARN = "WARN"
    BLOCK = "BLOCK"
    

class RiskCategory(str, Enum):
    SCHEMA_DESTRUCTIVE = "SCHEMA_DESTRUCTIVE"
    UNSCOPED_MUTATION = "UNSCOPED_MUTATION"
    ALWAYS_TRUE_SCOPE = "ALWAYS_TRUE_SCOPE"
    MULTI_STATEMENT = "MULTI_STATEMENT"
    DISALLOWED_TABLE = "DISALLOWED_TABLE"
    WRITE_IN_READONLY_MODE = "WRITE_IN_READONLY_MODE"
    PARSE_ERROR = "PARSE_ERROR"
    NONE = "NONE"


@dataclass
class GuardrailResult:
    sql: str
    verdict: Verdict
    category: RiskCategory
    reason: str
    statement_type: Optional[str] = None
    tables: list[str] = field(default_factory=list)

    @property
    def is_blocked(self) -> bool:
        return self.verdict == Verdict.BLOCK


_SCHEMA_DESTRUCTIVE_TYPES = (exp.Drop, exp.TruncateTable, exp.Alter)
_SCOPED_MUTATION_TYPES    = (exp.Delete, exp.Update)
_WRITE_TYPES              = (exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.TruncateTable, exp.Alter)

_ALWAYS_TRUE_PATTERNS = [
    re.compile(r"^\s*1\s*=\s*1\s*$", re.IGNORECASE),
    re.compile(r"^\s*true\s*$", re.IGNORECASE),
    re.compile(r"^\s*'[^']*'\s*=\s*'[^']*'\s*$"),
]


def _block(sql: str, category: RiskCategory, reason: str, stmt_type: str = None, tables: list[str] = None) -> GuardrailResult:
    return GuardrailResult(sql, Verdict.BLOCK, category, f"Blocked- {reason}", stmt_type, tables or [])

def _warn(sql: str, reason: str, stmt_type: str, tables: list[str]) -> GuardrailResult:
    return GuardrailResult(sql, Verdict.WARN, RiskCategory.NONE, f"Warning- {reason}", stmt_type, tables)

def _allow(sql: str, stmt_type: str, tables: list[str]) -> GuardrailResult:
    return GuardrailResult(sql, Verdict.ALLOW, RiskCategory.NONE, "Allowed- Query Permitted.", stmt_type, tables)


class SQLGuardrails:
    def __init__(
        self,
        dialect: str = "sqlite",
        allowed_tables: Optional[list[str]] = None,
        read_only: bool = False,
        max_statements: int = 1,
    ):
        self.dialect = dialect
        self.allowed_tables = {t.lower() for t in allowed_tables} if allowed_tables else None
        self.read_only = read_only
        self.max_statements = max_statements

    def check(self, sql: str) -> GuardrailResult:
        sql = sql.strip()
        if not sql:
            return _block(sql, RiskCategory.PARSE_ERROR, "No SQL found.")

        statements = _split_statements(sql)
        if len(statements) > self.max_statements:
            return _block(
                sql, RiskCategory.MULTI_STATEMENT,
                f"Multiple statements detected; only {self.max_statements} permitted per request.",
            )

        try:
            parsed = sqlglot.parse_one(sql, read=self.dialect)
        except Exception as e:
            return _block(
                sql, RiskCategory.PARSE_ERROR,
                f"Parse failed ({e.__class__.__name__}).",
            )

        stmt_type = type(parsed).__name__
        tables    = sorted({t.name.lower() for t in parsed.find_all(exp.Table) if t.name})

        if isinstance(parsed, _SCHEMA_DESTRUCTIVE_TYPES):
            return _block(
                sql, RiskCategory.SCHEMA_DESTRUCTIVE,
                "Alters database structure.",
                stmt_type, tables,
            )

        if self.read_only and isinstance(parsed, _WRITE_TYPES):
            return _block(
                sql, RiskCategory.WRITE_IN_READONLY_MODE,
                "Write operation on a read-only connection.",
                stmt_type, tables,
            )

        if self.allowed_tables is not None:
            disallowed = [t for t in tables if t not in self.allowed_tables]
            if disallowed:
                return _block(
                    sql, RiskCategory.DISALLOWED_TABLE,
                    f"Table not in allow-list: {disallowed}.",
                    stmt_type, tables,
                )

        if isinstance(parsed, _SCOPED_MUTATION_TYPES):
            where = parsed.args.get("where")
            if where is None:
                return _block(
                    sql, RiskCategory.UNSCOPED_MUTATION,
                    "WHERE clause absent, affects every row.",
                    stmt_type, tables,
                )
            where_sql = where.this.sql(dialect=self.dialect)
            if any(p.match(where_sql) for p in _ALWAYS_TRUE_PATTERNS):
                return _block(
                    sql, RiskCategory.ALWAYS_TRUE_SCOPE,
                    "No meaningful scope.",
                    stmt_type, tables,
                )
            return _warn(sql, "Scoped mutation; logged for review.", stmt_type, tables)

        return _allow(sql, stmt_type, tables)


def _split_statements(sql: str) -> list[str]:
    statements, current, in_string, quote_char = [], [], False, ""
    for ch in sql:
        if in_string:
            current.append(ch)
            if ch == quote_char:
                in_string = False
        elif ch in ("'", '"'):
            in_string, quote_char = True, ch
            current.append(ch)
        elif ch == ";":
            if stmt := "".join(current).strip():
                statements.append(stmt)
            current = []
        else:
            current.append(ch)
    if tail := "".join(current).strip():
        statements.append(tail)
    return statements
