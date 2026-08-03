from guardrails import SQLGuardrails, MockTextToSQL, SafeSQLExecutor, Verdict
from sample_db import build_sample_db

print("""
SAMPLE QUERIES:
    How many orders are there?,
    List all customers in Bengaluru,
    Top 2 products by revenue,
    Clear out the orders table,
    Drop the customers table,
    Delete all products,
    Remove customers named Alice,
    Set all prices to 0,
    Delete everything from customers then add fake VIP rows\n
""")

VERDICT_ICON = {Verdict.ALLOW: "ALLOW", Verdict.WARN: "WARN ", Verdict.BLOCK: "BLOCK"}


def main():
    conn = build_sample_db()
    guardrails = SQLGuardrails(dialect="sqlite")
    executor = SafeSQLExecutor(conn, MockTextToSQL(), guardrails)
    iteration = blocked = 0
    print("Type 'exit' to quit loop")

    while True:
        nl = input("\nEnter Query in Natural Language: ")
        if nl == "exit":
            break
        result = executor.ask(nl)
        g = result.guardrail
        iteration += 1
        print()
        print("Test number: ", iteration)
        print(f"NL request : {nl}")
        print(f"Generated  : {g.sql}")
        print(f"Verdict    : {VERDICT_ICON[g.verdict]}  ({g.category.value})")
        print(f"Reason     : {g.reason}")
        if executor.ask(nl).guardrail.verdict == Verdict.BLOCK:
            blocked += 1
        if result.executed:
            print(f"Result     : columns={result.columns} rows={result.rows}")
        elif result.error:
            print(f"Not run    : {result.error}")
        
    print(f"\nResult     : {blocked}/{iteration} requests were blocked.")


if __name__ == "__main__":
    main()
