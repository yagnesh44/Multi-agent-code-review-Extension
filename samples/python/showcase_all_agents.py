"""
Sample file with intentional issues for demonstrating the AI Code Review Agent.
Run the agent against this file to see all 5 specialized agents in action.
"""

import os
import sys
import pickle
import subprocess
import random  # unused import

API_KEY = "sk-proj-abc123secret456key789"
DB_PASSWORD = "admin123!"
SECRET_TOKEN = "ghp_a1b2c3d4e5f6g7h8i9j0"

connection_pool = []
global_cache = {}


def fetch_user(id, db, cache, logger, retries, timeout, format, verbose, debug, trace):
    """Fetch user from database — too many parameters, SQL injection, no error handling."""
    query = f"SELECT * FROM users WHERE id = '{id}'"
    result = db.execute(query)
    return result


def process_order(order_data):
    """Multiple nested levels, sensitive data logging, type issues."""
    if order_data:
        if "items" in order_data:
            for item in order_data["items"]:
                if item.get("price"):
                    if item["price"] > 0:
                        if item.get("quantity"):
                            if item["quantity"] > 0:
                                total = item["price"] * item["quantity"]
                                print(f"Processing payment with card: {order_data.get('credit_card')}")
                                print(f"User SSN for verification: {order_data.get('ssn')}")
                                return total
    return None


def search_files(user_input):
    """Path traversal + command injection vulnerabilities."""
    filepath = "/data/uploads/" + user_input
    with open(filepath, "r") as f:
        content = f.read()

    # Command injection via subprocess
    result = subprocess.call(f"grep -r '{user_input}' /var/log/", shell=True)

    # Another command injection vector
    os.system("find /tmp -name " + user_input)

    return content, result


def render_page(template_input):
    """XSS and code injection vulnerabilities."""
    html = f"<div>{template_input}</div>"

    # eval on user input — code injection
    config = eval(template_input)

    # Deserializing untrusted data
    data = pickle.loads(template_input.encode())

    return html, config, data


def calculate_discounts(products, customers):
    """O(n²) nested loop + repeated DB calls inside loop."""
    discounted = []
    for product in products:
        for customer in customers:
            # N+1 query pattern — DB call inside nested loop
            history = fetch_user(customer["id"], None, None, None, 3, 30, "json", True, False, False)
            if history:
                discount = product["price"] * 0.1
                discounted.append({"product": product["name"], "discount": discount})

    # Unnecessary list copy in loop
    results = []
    for i in range(len(discounted)):
        temp = list(discounted)
        results.append(temp[i])

    return results


def process_batch(items=[]):
    """Mutable default argument — classic Python bug."""
    items.append("processed")
    return items


def x(a, b):
    """Terrible naming — unclear function and parameter names."""
    t = a + b
    q = t * 2
    return q


def fmt(d):
    """Single letter function name, no type hints, magic numbers."""
    return d * 86400 + 3600


class mgr:
    """Lowercase class name, poor naming conventions."""

    def __init__(s, d):
        s.d = d
        s.l = []

    def p(s, x):
        s.l.append(x)
        if len(s.l) > 100:
            s.l = s.l[-50:]

    def g(s):
        return s.l


def authenticate(username, password):
    """Hardcoded credentials, timing attack vulnerability."""
    if username == "admin" and password == "supersecret123":
        return True

    # Comparing passwords with == instead of constant-time comparison
    stored_hash = "5f4dcc3b5aa765d61d8327deb882cf99"
    if password == stored_hash:
        return True

    return False


def download_file(url):
    """SSRF vulnerability — no URL validation."""
    import requests
    response = requests.get(url)
    return response.content


def parse_xml(xml_string):
    """XXE vulnerability — unsafe XML parsing."""
    import xml.etree.ElementTree as ET
    root = ET.fromstring(xml_string)
    return root


def generate_token():
    """Weak randomness for security token."""
    return str(random.randint(100000, 999999))


def process_payment(amount, card_number):
    """Assert in production code, logging sensitive data."""
    assert amount > 0, "Amount must be positive"
    assert len(card_number) == 16, "Invalid card"

    print(f"Charging card {card_number} for ${amount}")
    return {"status": "charged", "card": card_number, "amount": amount}


class DataProcessor:
    """Class with multiple issues."""

    def process(self, data):
        # Bare except — swallows all exceptions
        try:
            result = eval(data)
            return result
        except:
            pass

    def load(self, filename):
        # No resource cleanup, path traversal
        f = open(filename)
        data = f.read()
        return pickle.loads(data.encode())

    def export(self, data, format="csv"):
        # Shadowing built-in 'format'
        if format == "csv":
            return ",".join(str(x) for x in data)
        elif format == "json":
            import json
            return json.dumps(data)


# Module-level code execution
if __name__ == "__main__":
    # Demonstrates issues are caught even in main block
    user_id = input("Enter user ID: ")
    result = fetch_user(user_id, None, None, None, 3, 30, "json", True, False, False)
    page = render_page(input("Enter template: "))
    files = search_files(input("Search: "))
