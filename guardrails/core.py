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


# statement types that can never run automatically
_SCHEMA_DESTRUCTIVE_TYPES = (exp.Drop, exp.TruncateTable, exp.Alter)

# statement types that mutate rows and require a WHERE clause.
_SCOPED_MUTATION_TYPES = (exp.Delete, exp.Update)

_ALWAYS_TRUE_PATTERNS = [
    re.compile(r"^\s*1\s*=\s*1\s*$", re.IGNORECASE), # is 1?
    re.compile(r"^\s*true\s*$", re.IGNORECASE), # is true?
    re.compile(r"^\s*'[^']*'\s*=\s*'[^']*'\s*$"), # is 'a'='a'?
]


class SQLGuardrails:
    # Analyze a single SQL statement and return a verdict *before* it is handed to a database connection.
    def __init__(
        self,
        dialect: str = "sqlite",
        allowed_tables: Optional[list[str]] = None,
        read_only: bool = False,
        max_statements: int = 1,
    ):
        self.dialect = dialect
        self.allowed_tables = set(t.lower() for t in allowed_tables) if allowed_tables else None
        self.read_only = read_only
        self.max_statements = max_statements

    def check(self, sql: str) -> GuardrailResult:
        sql = sql.strip()
        if not sql:
            return GuardrailResult(sql, Verdict.BLOCK, RiskCategory.PARSE_ERROR, "Empty SQL.")

        # multi-statement check to avoid multiple queries within a statement.
        statements = self._split_statements(sql)
        if len(statements) > self.max_statements:
            return GuardrailResult(
                sql, Verdict.BLOCK, RiskCategory.MULTI_STATEMENT,
                f"Input contains {len(statements)} statements; only "
                f"{self.max_statements} allowed per request. This shape is "
                f"a classic SQL-injection / prompt-injection pattern.",
            )

        try:
            parsed = sqlglot.parse_one(sql, read=self.dialect)
        except Exception as e:
            return GuardrailResult(
                sql, Verdict.BLOCK, RiskCategory.PARSE_ERROR,
                f"Could not parse SQL confidently ({e.__class__.__name__}); "
                f"failing closed rather than guessing.",
            )

        stmt_type = type(parsed).__name__
        tables = sorted({t.name.lower() for t in parsed.find_all(exp.Table) if t.name})

        # schema-destructive statements are always blocked.
        if isinstance(parsed, _SCHEMA_DESTRUCTIVE_TYPES):
            return GuardrailResult(
                sql, Verdict.BLOCK, RiskCategory.SCHEMA_DESTRUCTIVE,
                f"{stmt_type} statements modify database structure and are "
                f"never auto-executed.",
                stmt_type, tables,
            )

        # read-only mode blocks any write.
        if self.read_only and isinstance(
            parsed, (exp.Insert, exp.Update, exp.Delete, *_SCHEMA_DESTRUCTIVE_TYPES)
        ):
            return GuardrailResult(
                sql, Verdict.BLOCK, RiskCategory.WRITE_IN_READONLY_MODE,
                "This connection is configured read-only; write statements are blocked.",
                stmt_type, tables,
            )

        # table allow-list.
        if self.allowed_tables is not None:
            disallowed = [t for t in tables if t not in self.allowed_tables]
            if disallowed:
                return GuardrailResult(
                    sql, Verdict.BLOCK, RiskCategory.DISALLOWED_TABLE,
                    f"Statement touches table(s) outside the allowed scope: {disallowed}.",
                    stmt_type, tables,
                )

        # UPDATE and DELETE must be scoped by a WHERE clause.
        if isinstance(parsed, _SCOPED_MUTATION_TYPES):
            where = parsed.args.get("where")
            if where is None:
                return GuardrailResult(
                    sql, Verdict.BLOCK, RiskCategory.UNSCOPED_MUTATION,
                    f"{stmt_type} has no WHERE clause — it would affect every "
                    f"row in the table. Blocked by default.",
                    stmt_type, tables,
                )
            where_sql = where.this.sql(dialect=self.dialect)
            if any(p.match(where_sql) for p in _ALWAYS_TRUE_PATTERNS):
                return GuardrailResult(
                    sql, Verdict.BLOCK, RiskCategory.ALWAYS_TRUE_SCOPE,
                    f"{stmt_type} WHERE clause ('{where_sql}') is a tautology "
                    f"and matches every row. Blocked as effectively unscoped.",
                    stmt_type, tables,
                )
            # we allow, but we log this query too.
            return GuardrailResult(
                sql, Verdict.WARN, RiskCategory.NONE,
                f"{stmt_type} is scoped by a WHERE clause; allowed with logging.",
                stmt_type, tables,
            )

        # everything remaining
        return GuardrailResult(
            sql, Verdict.ALLOW, RiskCategory.NONE, "No destructive pattern detected.",
            stmt_type, tables,
        )

    @staticmethod
    def _split_statements(sql: str) -> list[str]:
        """Split on semicolons that are not inside a string literal."""
        statements, current, in_string, quote_char = [], [], False, ""
        for ch in sql:
            if in_string:
                current.append(ch)
                if ch == quote_char:
                    in_string = False
            elif ch in ("'", '"'):
                in_string = True
                quote_char = ch
                current.append(ch)
            elif ch == ";":
                stmt = "".join(current).strip()
                if stmt:
                    statements.append(stmt)
                current = []
            else:
                current.append(ch)
        tail = "".join(current).strip()
        if tail:
            statements.append(tail)
        return statements
