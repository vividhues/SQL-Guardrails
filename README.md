# SQL Guardrails

Blocks bad SQL (`DROP`, unwanted `DELETE`/`UPDATE` or stacked queries) before it reaches your database.

## How it works

Natural language → SQL is generated → the SQL is parsed and checked → only safe SQL runs.

```
"clear the orders table" → DELETE FROM orders; → BLOCKED (no WHERE clause)
"how many orders?"        → SELECT COUNT(*) FROM orders; → ALLOWED
```

## Install

```bash
pip install -r requirements.txt
# Run the demo
python demo.py
```

## Demo code

```python
from guardrails import SQLGuardrails, Verdict

verdict = SQLGuardrails().check(generated_sql)
if verdict.verdict == Verdict.BLOCK:
    print("Blocked:", verdict.reason)
else:
    run(generated_sql)
```

## What gets blocked

- `DROP`, `TRUNCATE`, `ALTER`
- `DELETE` / `UPDATE` with no `WHERE` clause
- `WHERE 1=1` style fake conditions
- Multiple stacked statements (`SELECT 1; DROP TABLE x;`)
- SQL that fails to parse
