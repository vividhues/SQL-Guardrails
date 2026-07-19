import sqlite3

def build_sample_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE customers (
            id INTEGER PRIMARY KEY, name TEXT, email TEXT
        );
        CREATE TABLE products (
            id INTEGER PRIMARY KEY, name TEXT, price REAL, stock INTEGER
        );
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY, customer_id INTEGER, product_id INTEGER,
            quantity INTEGER, order_date TEXT
        );

        INSERT INTO customers VALUES
            (1, 'Asmita', 'asmita@example.com'),
            (2, 'Advaith', 'advaith@example.com');

        INSERT INTO products VALUES
            (1, 'Wireless Mouse', 799.0, 120),
            (2, 'Mechanical Keyboard', 3499.0, 45),
            (3, 'USB-C Hub', 1299.0, 80);

        INSERT INTO orders VALUES
            (1, 1, 1, 2, '2026-06-01'),
            (2, 1, 2, 1, '2026-06-03'),
            (3, 2, 3, 1, '2026-06-10'),
            (4, 3, 2, 1, '2026-07-01');
    """)
    conn.commit()
    return conn