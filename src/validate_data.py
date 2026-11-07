import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "instamart.db"

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Check 1: Customers count
assert cursor.execute("SELECT COUNT(*) FROM customers").fetchone()[0] == 1200

# Check 2: Products count
assert cursor.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 40

# Check 3: Orders count
assert cursor.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 12309

# Check 4: Completed orders
assert cursor.execute(
    "SELECT COUNT(*) FROM orders WHERE status='completed'"
).fetchone()[0] == 11110

# Check 5: Cancelled orders
assert cursor.execute(
    "SELECT COUNT(*) FROM orders WHERE status='cancelled'"
).fetchone()[0] == 1199

# Check 6: No pending orders
assert cursor.execute(
    "SELECT COUNT(*) FROM orders WHERE status='pending'"
).fetchone()[0] == 0

# Check 7: No missing order amounts
assert cursor.execute(
    "SELECT COUNT(*) FROM orders WHERE order_amount IS NULL"
).fetchone()[0] == 0

# Check 8: Completed orders have no missing delivery times
assert cursor.execute(
    "SELECT COUNT(*) FROM orders WHERE status='completed' AND delivery_minutes IS NULL"
).fetchone()[0] == 0

# Check 9: Cancelled orders have missing delivery times
assert cursor.execute(
    "SELECT COUNT(*) FROM orders WHERE status='cancelled' AND delivery_minutes IS NULL"
).fetchone()[0] == 1199

# Check 10: Completed revenue
revenue = cursor.execute(
    "SELECT ROUND(SUM(order_amount), 2) FROM orders WHERE status='completed'"
).fetchone()[0]

assert revenue == 2998668.80

# Check 11: order_ts stored as TEXT
columns = cursor.execute("PRAGMA table_info(orders)").fetchall()
order_ts_type = next(col[2] for col in columns if col[1] == "order_ts")
assert order_ts_type.upper() == "TEXT"

conn.close()

print("ALL CHECKPOINTS PASSED")