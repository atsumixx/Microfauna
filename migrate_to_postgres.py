import sqlite3
import psycopg2
import psycopg2.extras
import os
from datetime import datetime

# SQLite connection
sqlite_conn = sqlite3.connect('sales.db')
sqlite_conn.row_factory = sqlite3.Row
sqlite_cursor = sqlite_conn.cursor()

# PostgreSQL connection (set DATABASE_URL env var)
postgres_conn = psycopg2.connect(os.environ['DATABASE_URL'])
postgres_cursor = postgres_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

# Migrate items
sqlite_cursor.execute("SELECT * FROM items")
items = sqlite_cursor.fetchall()
for item in items:
    postgres_cursor.execute("""
        INSERT INTO items (id, name, price, active)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (id) DO NOTHING
    """, (item['id'], item['name'], item['price'], bool(item['active'])))

# Migrate sales
sqlite_cursor.execute("SELECT * FROM sales")
sales = sqlite_cursor.fetchall()
for sale in sales:
    postgres_cursor.execute("""
        INSERT INTO sales (id, customer_name, date, total, notes, created_at)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO NOTHING
    """, (sale['id'], sale['customer_name'], sale['date'], sale['total'], sale['notes'], sale['created_at']))

# Migrate sale_items
sqlite_cursor.execute("SELECT * FROM sale_items")
sale_items = sqlite_cursor.fetchall()
for si in sale_items:
    postgres_cursor.execute("""
        INSERT INTO sale_items (id, sale_id, item_name, quantity, price, subtotal)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO NOTHING
    """, (si['id'], si['sale_id'], si['item_name'], si['quantity'], si['price'], si['subtotal']))

# Migrate expenses
sqlite_cursor.execute("SELECT * FROM expenses")
expenses = sqlite_cursor.fetchall()
for exp in expenses:
    postgres_cursor.execute("""
        INSERT INTO expenses (id, description, amount, category, date, notes, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO NOTHING
    """, (exp['id'], exp['description'], exp['amount'], exp['category'], exp['date'], exp['notes'], exp['created_at']))

postgres_conn.commit()
sqlite_conn.close()
postgres_conn.close()

print("Migration completed!")