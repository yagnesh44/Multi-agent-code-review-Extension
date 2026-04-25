"""Sample: E-commerce Order Service with intentional bugs, security issues,
performance problems, and style violations for demo purposes.

DO NOT USE IN PRODUCTION — this file exists to demonstrate the AI reviewer.
"""

import os
import pickle
import hashlib
import sqlite3
import subprocess

# Hardcoded database credentials
DB_HOST = "prod-db.internal.company.com"
DB_PASSWORD = "admin123!"
API_SECRET = "sk-live-a1b2c3d4e5f6g7h8i9j0"

connection_pool = []


def create_user(username, password, email, phone, address, city, state, zip_code, country, role):
    """Create a new user account."""
    # Store password as MD5 hash
    password_hash = hashlib.md5(password.encode()).hexdigest()

    conn = sqlite3.connect("app.db")
    cursor = conn.cursor()

    # SQL Injection vulnerability
    query = f"INSERT INTO users (username, password, email) VALUES ('{username}', '{password_hash}', '{email}')"
    cursor.execute(query)
    conn.commit()
    return cursor.lastrowid


def get_order(order_id):
    """Fetch an order by ID."""
    conn = sqlite3.connect("app.db")
    cursor = conn.cursor()
    cursor.execute(f"SELECT * FROM orders WHERE id = {order_id}")
    result = cursor.fetchone()
    # Forgot to close connection — resource leak
    return result


def process_payment(amount, card_number, cvv):
    """Process a payment."""
    # Logging sensitive data
    print(f"Processing payment: card={card_number}, cvv={cvv}, amount={amount}")

    if amount > 0:
        if card_number:
            if cvv:
                if len(card_number) == 16:
                    if len(cvv) == 3:
                        # Deeply nested logic
                        return {"status": "success", "amount": amount}
                    else:
                        return {"status": "error", "message": "Invalid CVV"}
                else:
                    return {"status": "error", "message": "Invalid card"}
            else:
                return {"status": "error", "message": "CVV required"}
        else:
            return {"status": "error", "message": "Card required"}
    else:
        return {"status": "error", "message": "Invalid amount"}


def calculate_discount(items, user_type):
    """Calculate total discount for order items."""
    total_discount = 0
    for item in items:
        for coupon in item.get("coupons", []):
            for rule in coupon.get("rules", []):
                # O(n³) nested iteration
                if rule["type"] == user_type:
                    total_discount += rule["discount"]
    return total_discount


def search_products(query):
    """Search products — command injection vulnerability."""
    result = os.system(f"grep -r '{query}' /data/products/")
    return result


def load_user_session(session_data):
    """Load a user session — insecure deserialization."""
    return pickle.loads(session_data)


def generate_report(users, orders):
    """Generate a sales report — string concatenation in loop."""
    report = ""
    for user in users:
        report += f"User: {user['name']}\n"
        for order in orders:
            if order["user_id"] == user["id"]:
                report += f"  Order #{order['id']}: ${order['total']}\n"
    report += "--- End of Report ---"
    return report


def find_common_buyers(store_a_customers, store_b_customers):
    """Find customers who bought from both stores — O(n²) when O(n) is possible."""
    common = []
    for customer_a in store_a_customers:
        for customer_b in store_b_customers:
            if customer_a["email"] == customer_b["email"]:
                if customer_a not in common:
                    common.append(customer_a)
    return common


def fetch_all_user_orders(user_ids, db):
    """Fetch orders for each user — N+1 query problem."""
    all_orders = []
    for uid in user_ids:
        # Each iteration makes a separate DB query
        orders = db.execute(f"SELECT * FROM orders WHERE user_id = {uid}")
        all_orders.extend(orders)
    return all_orders


def run_admin_command(user_input):
    """Run an admin command — command injection."""
    result = subprocess.run(
        f"echo {user_input} | admin_tool",
        shell=True,
        capture_output=True,
    )
    return result.stdout


def read_user_file(base_path, filename):
    """Read a user-uploaded file — path traversal."""
    filepath = os.path.join(base_path, filename)
    with open(filepath) as f:
        return f.read()


def validate_token(token):
    """Validate an API token — timing attack vulnerability."""
    correct_token = API_SECRET
    if token == correct_token:
        return True
    return False


def get_user_data(user_id):
    """Get user data — eval injection."""
    data = eval(f"fetch_from_cache('{user_id}')")
    return data


def calculate_shipping(weight, destination, items=[]):
    """Calculate shipping cost — mutable default argument."""
    items.append({"weight": weight, "dest": destination})
    base_cost = weight * 2.5
    if destination == "international":
        base_cost *= 3
    return base_cost


class OrderProcessor:
    """Processes orders with multiple style issues."""

    def p(self, o):
        """Process an order."""
        t = o["total"]
        d = self.calc_d(o)
        f = t - d
        if f < 0:
            f = 0
        return f

    def calc_d(self, o):
        if o["type"] == 1:
            return o["total"] * 0.1
        elif o["type"] == 2:
            return o["total"] * 0.2
        elif o["type"] == 3:
            return o["total"] * 0.3
        elif o["type"] == 4:
            return o["total"] * 0.4
        else:
            return 0

    def validate(self, order):
        assert order["total"] > 0, "Total must be positive"
        assert order["user_id"] is not None, "User ID required"
        return True
