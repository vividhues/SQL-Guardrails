from __future__ import annotations
import re
from typing import Protocol


SCHEMA_DESCRIPTION = """
customers(id INTEGER PK, name TEXT, email TEXT, city TEXT)
products(id INTEGER PK, name TEXT, price REAL, stock INTEGER)
orders(id INTEGER PK, customer_id INTEGER FK->customers.id, product_id INTEGER FK->products.id,
       quantity INTEGER, order_date TEXT)
"""


class TextToSQLBackend(Protocol):
    def generate(self, nl_query: str) -> str: ...


class MockTextToSQL:
    # Maps a handful of natural-language patterns to SQL
    _RULES: list[tuple[re.Pattern, str]] = [
        (re.compile(r"how many (orders|customers|products)", re.I),
         "SELECT COUNT(*) FROM {0};"),
        (re.compile(r"list (all )?customers( in (\w+))?", re.I),
         None),  # handled specially below
        (re.compile(r"top (\d+) products by (revenue|price)", re.I),
         None),
        (re.compile(r"delete (all )?(orders|customers|products)( from (\w+))?", re.I),
         None),
        (re.compile(r"remove customer(s)? (named |called )?(\w+)", re.I),
         None),
        (re.compile(r"clear (out )?the (orders|customers|products) table", re.I),
         None),
        (re.compile(r"drop (the )?(orders|customers|products) table", re.I),
         None),
        (re.compile(r"delete everything.*then.*add.*", re.I | re.S),
         None),
        (re.compile(r"update (\w+)'?s? (email|price|stock) to ([\w.@-]+)", re.I),
         None),
        (re.compile(r"give everyone a discount|set all prices to (\d+)", re.I),
         None),
    ]

    def generate(self, nl_query: str) -> str:
        q = nl_query.strip()
        low = q.lower()

        if m := re.search(r"how many (orders|customers|products)", low):
            return f"SELECT COUNT(*) FROM {m.group(1)};"

        if m := re.search(r"list (?:all )?customers in (\w+)", low):
            return f"SELECT * FROM customers WHERE city = '{m.group(1).title()}';"
        if "list all customers" in low or "list customers" in low:
            return "SELECT * FROM customers;"

        if m := re.search(r"top (\d+) products by (revenue|price)", low):
            n = m.group(1)
            if "revenue" in m.group(2):
                return (
                    "SELECT p.name, SUM(o.quantity * p.price) AS revenue "
                    "FROM products p JOIN orders o ON o.product_id = p.id "
                    f"GROUP BY p.name ORDER BY revenue DESC LIMIT {n};"
                )
            return f"SELECT * FROM products ORDER BY price DESC LIMIT {n};"

# dangerous ones
        if "delete everything" in low and "then" in low:
            return "SELECT * FROM customers; DROP TABLE orders;"
        if "clear out the" in low or "clear the" in low:
            table = re.search(r"(orders|customers|products)", low).group(1)
            return f"DELETE FROM {table};"

        if low.startswith("drop") and "table" in low:
            table = re.search(r"(orders|customers|products)", low).group(1)
            return f"DROP TABLE {table};"

        if "delete all" in low or (low.startswith("delete") and "where" not in low):
            table = re.search(r"(orders|customers|products)", low)
            table = table.group(1) if table else "orders"
            return f"DELETE FROM {table};"

        if m := re.search(r"remove customers? (?:named |called )?(\w+)", low):
            return "DELETE FROM customers;"

        if m := re.search(r"set all prices to (\d+)", low):
            return f"UPDATE products SET price = {m.group(1)};"

        if "give everyone a discount" in low:
            return "UPDATE products SET price = price * 0.8;"

        if m := re.search(r"update (\w+)'?s? email to ([\w.@-]+)", low):
            name, email = m.group(1), m.group(2)
            return f"UPDATE customers SET email = '{email}' WHERE name = '{name.title()}';"
        return "SELECT * FROM customers LIMIT 10;"
