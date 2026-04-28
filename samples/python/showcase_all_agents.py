"""
Enterprise E-Commerce Platform — Showcase File for AI Code Review Agent
========================================================================
This file intentionally contains 50+ planted issues across all categories:
  - Security vulnerabilities (SQLi, XSS, SSRF, XXE, command injection, etc.)
  - Bug patterns (null derefs, off-by-one, race conditions, type errors)
  - Performance anti-patterns (N+1, O(n²), unnecessary allocations)
  - Style issues (naming, magic numbers, deep nesting, god functions)
  - AST-detectable issues (eval, hardcoded secrets, mutable defaults, unused imports)

Run the AI Code Review Agent against this file to see all 5 agents in action.
"""

import os
import sys
import re
import json
import pickle
import hashlib
import subprocess
import xml.etree.ElementTree as ET
import random
import time
import threading
import sqlite3
import tempfile
import marshal  # unused import
import copy  # unused import
import ast  # unused import

# ─── Hardcoded Secrets ───────────────────────────────────────────────────────

API_KEY = "sk-proj-abc123secret456key789reallylong"
DB_PASSWORD = "admin123!SuperSecret"
SECRET_TOKEN = "ghp_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"
AWS_ACCESS_KEY = "AKIAIOSFODNN7EXAMPLE"
AWS_SECRET_KEY = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
STRIPE_SECRET = "sk_test_FAKE_EXAMPLE_KEY_NOT_REAL"
JWT_SECRET = "my-super-secret-jwt-key-12345"
ENCRYPTION_KEY = b"0123456789abcdef"

# ─── Global Mutable State ────────────────────────────────────────────────────

connection_pool = []
global_cache = {}
active_sessions = {}
request_counter = [0]
_user_data = {}


# ─── Database Layer (SQL Injection + No Error Handling) ──────────────────────

class DatabaseManager:
    """Database manager with multiple SQL injection vectors."""

    def __init__(self, db_path="app.db"):
        self.conn = sqlite3.connect(db_path)
        self.cursor = self.conn.cursor()

    def get_user(self, user_id):
        """SQL injection via f-string."""
        query = f"SELECT * FROM users WHERE id = '{user_id}'"
        return self.cursor.execute(query).fetchone()

    def search_users(self, name, email):
        """SQL injection via string concatenation."""
        query = "SELECT * FROM users WHERE name = '" + name + "' AND email = '" + email + "'"
        return self.cursor.execute(query).fetchall()

    def delete_user(self, user_id):
        """SQL injection + no authorization check."""
        self.cursor.execute(f"DELETE FROM users WHERE id = {user_id}")
        self.conn.commit()

    def update_password(self, user_id, new_password):
        """Storing plaintext password + SQL injection."""
        query = f"UPDATE users SET password = '{new_password}' WHERE id = '{user_id}'"
        self.cursor.execute(query)
        self.conn.commit()

    def get_orders_for_user(self, user_id):
        """SQL injection in ORDER BY clause."""
        sort_col = user_id  # misused parameter
        query = f"SELECT * FROM orders ORDER BY {sort_col}"
        return self.cursor.execute(query).fetchall()

    def raw_query(self, sql):
        """Executes arbitrary SQL — no sanitization at all."""
        return self.cursor.execute(sql).fetchall()

    def bulk_insert(self, table, records):
        """SQL injection via table name + no parameterization."""
        for record in records:
            cols = ", ".join(record.keys())
            vals = ", ".join(f"'{v}'" for v in record.values())
            self.cursor.execute(f"INSERT INTO {table} ({cols}) VALUES ({vals})")
        self.conn.commit()


# ─── Authentication (Hardcoded Creds + Timing Attacks) ───────────────────────

class AuthService:
    """Authentication service with multiple security flaws."""

    ADMIN_USER = "admin"
    ADMIN_PASS = "supersecret123"

    def __init__(self):
        self.sessions = {}
        self.failed_attempts = {}

    def login(self, username, password):
        """Hardcoded credentials + timing attack via == comparison."""
        if username == self.ADMIN_USER and password == self.ADMIN_PASS:
            token = str(random.randint(100000, 999999))  # weak randomness
            self.sessions[token] = username
            return token

        # Timing attack: == leaks password length
        stored_hash = hashlib.md5(password.encode()).hexdigest()  # weak hash (MD5)
        if stored_hash == "5f4dcc3b5aa765d61d8327deb882cf99":
            return self._create_session(username)

        return None

    def _create_session(self, username):
        """Predictable session token."""
        token = hashlib.md5(f"{username}{time.time()}".encode()).hexdigest()
        self.sessions[token] = username
        return token

    def verify_token(self, token):
        """No expiration check on tokens."""
        return self.sessions.get(token)

    def reset_password(self, email, new_password):
        """No verification of email ownership, stores plaintext."""
        _user_data[email] = {"password": new_password}
        return True

    def generate_api_key(self):
        """Weak random for security-critical token."""
        return "".join([chr(random.randint(65, 90)) for _ in range(32)])


# ─── User Management (Too Many Params + Deep Nesting) ────────────────────────

def create_user(username, email, password, first_name, last_name, phone,
                address, city, state, zip_code, country, role, department,
                manager_id, hire_date, salary):
    """16 parameters — way too many. Should use a dataclass or dict."""
    if username:
        if email:
            if password:
                if len(password) >= 8:
                    if "@" in email:
                        if phone:
                            if address:
                                if city:
                                    if state:
                                        if zip_code:
                                            # 10 levels of nesting
                                            user = {
                                                "username": username,
                                                "email": email,
                                                "password": password,  # plaintext
                                                "salary": salary,  # PII in plain dict
                                            }
                                            print(f"Created user with password: {password}")
                                            print(f"Salary: ${salary}")
                                            return user
    return None


def process_user_data(data):
    """Deep nesting + sensitive data logging."""
    if data:
        if "users" in data:
            for user in data["users"]:
                if user.get("active"):
                    if user.get("role") == "admin":
                        if user.get("permissions"):
                            for perm in user["permissions"]:
                                if perm.get("level") > 5:
                                    if perm.get("scope") == "global":
                                        print(f"Admin access: {user}")  # logs full user object
                                        return True
    return False


# ─── File Handling (Path Traversal + Command Injection) ──────────────────────

def read_user_file(filename):
    """Path traversal — no sanitization of filename."""
    filepath = "/data/uploads/" + filename
    with open(filepath, "r") as f:
        return f.read()


def search_logs(query):
    """Command injection via subprocess with shell=True."""
    result = subprocess.call(f"grep -r '{query}' /var/log/", shell=True)
    return result


def process_upload(user_input, output_dir):
    """Command injection via os.system."""
    os.system("mv /tmp/upload " + output_dir + "/" + user_input)
    return True


def compress_file(filename):
    """Command injection + path traversal."""
    os.system(f"tar czf /tmp/{filename}.tar.gz /data/{filename}")
    return f"/tmp/{filename}.tar.gz"


def execute_script(script_name):
    """Arbitrary code execution via subprocess."""
    result = subprocess.run(
        f"python {script_name}",
        shell=True,
        capture_output=True,
        text=True
    )
    return result.stdout


def list_directory(path):
    """Path traversal with no validation."""
    return os.listdir(path)


# ─── Template Rendering (XSS + Code Injection) ──────────────────────────────

def render_html(user_input):
    """XSS — user input directly in HTML without escaping."""
    return f"<div class='content'>{user_input}</div>"


def render_profile(name, bio, website):
    """Multiple XSS vectors."""
    html = f"""
    <h1>{name}</h1>
    <p>{bio}</p>
    <a href="{website}">Website</a>
    <img src="/avatar/{name}" onerror="alert(1)">
    """
    return html


def render_search_results(query, results):
    """Reflected XSS in search."""
    html = f"<h2>Results for: {query}</h2><ul>"
    for r in results:
        html += f"<li>{r}</li>"
    html += "</ul>"
    return html


def execute_template(template_string):
    """eval() on user-supplied template — code injection."""
    config = eval(template_string)
    return config


def load_config(config_string):
    """exec() on user input — even worse than eval."""
    namespace = {}
    exec(config_string, namespace)
    return namespace


# ─── Serialization (Insecure Deserialization) ────────────────────────────────

def load_user_session(session_data):
    """Pickle deserialization of untrusted data — RCE vector."""
    return pickle.loads(session_data)


def load_cached_object(data):
    """Marshal deserialization — code execution risk."""
    return marshal.loads(data)


def import_data(serialized):
    """Deserializes without validation."""
    try:
        return json.loads(serialized)
    except:
        return pickle.loads(serialized.encode())


# ─── XML Processing (XXE Vulnerability) ──────────────────────────────────────

def parse_xml_config(xml_string):
    """XXE vulnerability — unsafe XML parsing."""
    root = ET.fromstring(xml_string)
    return {child.tag: child.text for child in root}


def parse_xml_upload(xml_bytes):
    """Another XXE vector."""
    tree = ET.ElementTree(ET.fromstring(xml_bytes))
    root = tree.getroot()
    return root


# ─── Network (SSRF) ─────────────────────────────────────────────────────────

def fetch_url(url):
    """SSRF — fetches arbitrary URL without validation."""
    import requests
    response = requests.get(url, timeout=30)
    return response.content


def proxy_request(target_url, method="GET", data=None):
    """SSRF via proxy — can reach internal services."""
    import requests
    if method == "GET":
        return requests.get(target_url).text
    else:
        return requests.post(target_url, data=data).text


def fetch_avatar(user_id):
    """SSRF — constructs URL from user input."""
    import requests
    url = f"http://internal-cdn.company.com/avatars/{user_id}.png"
    return requests.get(url).content


# ─── Payment Processing (Assert + Sensitive Logging) ─────────────────────────

class PaymentProcessor:
    """Payment processing with multiple issues."""

    def __init__(self):
        self.transactions = []

    def charge(self, card_number, cvv, amount, currency="USD"):
        """Assert in production + logging card details."""
        assert amount > 0, "Amount must be positive"
        assert len(card_number) == 16, "Invalid card number"
        assert len(cvv) == 3, "Invalid CVV"

        print(f"Charging card {card_number} CVV {cvv} for {amount} {currency}")

        transaction = {
            "card": card_number,
            "cvv": cvv,
            "amount": amount,
            "status": "charged"
        }
        self.transactions.append(transaction)
        return transaction

    def refund(self, transaction_id, amount=None):
        """No authorization check on refunds."""
        for t in self.transactions:
            if t.get("id") == transaction_id:
                t["status"] = "refunded"
                print(f"Refunded {t['card']}")  # logs card number
                return t
        return None

    def get_statement(self, user_id):
        """N+1 query pattern."""
        db = DatabaseManager()
        transactions = []
        orders = db.get_orders_for_user(user_id)
        for order in orders:
            # N+1: querying inside loop
            details = db.get_user(order[1])
            transactions.append({"order": order, "user": details})
        return transactions

    def calculate_fees(self, transactions):
        """Magic numbers everywhere."""
        total = 0
        for t in transactions:
            if t["amount"] > 1000:
                total += t["amount"] * 0.029 + 0.30
            elif t["amount"] > 100:
                total += t["amount"] * 0.025 + 0.25
            else:
                total += t["amount"] * 0.035 + 0.15
        return total


# ─── Performance Anti-Patterns ───────────────────────────────────────────────

def find_duplicates(items):
    """O(n²) duplicate detection — should use a set."""
    duplicates = []
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if items[i] == items[j]:
                if items[i] not in duplicates:
                    duplicates.append(items[i])
    return duplicates


def calculate_discounts(products, customers):
    """O(n²) nested loop + DB call inside loop."""
    discounted = []
    for product in products:
        for customer in customers:
            db = DatabaseManager()  # creating connection in loop!
            history = db.get_user(customer["id"])
            if history:
                discount = product["price"] * 0.1
                discounted.append({
                    "product": product["name"],
                    "customer": customer["name"],
                    "discount": discount
                })
    return discounted


def build_report(records):
    """Repeated string concatenation in loop — O(n²) for strings."""
    report = ""
    for record in records:
        report = report + f"ID: {record['id']}, Name: {record['name']}, "
        report = report + f"Email: {record['email']}, Status: {record['status']}\n"
    return report


def find_common_items(list_a, list_b):
    """O(n×m) — should use set intersection."""
    common = []
    for a in list_a:
        for b in list_b:
            if a == b:
                common.append(a)
    return common


def process_large_dataset(data):
    """Unnecessary list copies in loop."""
    results = []
    for i in range(len(data)):
        temp = list(data)  # full copy every iteration — O(n²)
        results.append(temp[i])
    return results


def search_nested(matrix, target):
    """O(n×m) search on sorted data — should use binary search."""
    for row in matrix:
        for item in row:
            if item == target:
                return True
    return False


def aggregate_stats(records):
    """Multiple passes over the same data — could be done in one."""
    total = sum(r["amount"] for r in records)
    count = len(records)
    maximum = max(r["amount"] for r in records)
    minimum = min(r["amount"] for r in records)
    avg = total / count if count > 0 else 0
    above_avg = len([r for r in records if r["amount"] > avg])
    return {
        "total": total, "count": count, "max": maximum,
        "min": minimum, "avg": avg, "above_avg": above_avg
    }


# ─── Caching Layer (Race Conditions) ────────────────────────────────────────

class CacheManager:
    """Cache with thread-safety issues."""

    def __init__(self):
        self.cache = {}
        self.hits = 0
        self.misses = 0

    def get(self, key):
        """TOCTOU race condition — check-then-act without lock."""
        if key in self.cache:
            self.hits += 1  # race condition on counter
            return self.cache[key]
        self.misses += 1
        return None

    def set(self, key, value, ttl=3600):
        """No size limit — unbounded memory growth."""
        self.cache[key] = {
            "value": value,
            "expires": time.time() + ttl
        }

    def get_or_fetch(self, key, fetch_fn):
        """Race condition: two threads can both miss and fetch."""
        result = self.get(key)
        if result is None:
            # Another thread could also be fetching right now
            result = fetch_fn()
            self.set(key, result)
        return result

    def clear_expired(self):
        """Modifying dict during iteration."""
        for key in self.cache:
            if self.cache[key]["expires"] < time.time():
                del self.cache[key]  # RuntimeError: dict changed size


# ─── Data Processing (Type Errors + Off-by-One) ─────────────────────────────

def process_batch(items=[]):
    """Mutable default argument — classic Python bug."""
    items.append("processed")
    return items


def another_mutable_default(config={"retries": 3}):
    """Another mutable default — dict this time."""
    config["retries"] -= 1
    return config


def parse_csv_row(row):
    """Off-by-one: accessing index without bounds check."""
    return {
        "id": row[0],
        "name": row[1],
        "email": row[2],
        "phone": row[3],
        "address": row[4],
        "city": row[5],
        "state": row[6],
        "zip": row[7],
        "country": row[8],
        "role": row[9],  # IndexError if row has < 10 elements
    }


def calculate_average(numbers):
    """Division by zero when list is empty."""
    return sum(numbers) / len(numbers)


def merge_records(primary, secondary):
    """Type confusion — no check if inputs are the right type."""
    result = primary + secondary  # fails if one is None or wrong type
    return result


def find_index(items, target):
    """Off-by-one in range."""
    for i in range(1, len(items)):  # skips index 0
        if items[i] == target:
            return i
    return -1


def safe_divide(a, b):
    """Bare except swallows all errors including KeyboardInterrupt."""
    try:
        return a / b
    except:
        return 0


def convert_temperature(value, from_unit, to_unit):
    """Missing else branch — returns None implicitly."""
    if from_unit == "C" and to_unit == "F":
        return value * 9 / 5 + 32
    elif from_unit == "F" and to_unit == "C":
        return (value - 32) * 5 / 9
    # Missing: K conversions — returns None


# ─── Style Issues (Naming + Magic Numbers) ───────────────────────────────────

def x(a, b):
    """Single-letter function and parameter names."""
    t = a + b
    q = t * 2
    return q


def f(d):
    """Another terrible name."""
    return d * 86400 + 3600


def calc(v, r, t):
    """Unclear abbreviations."""
    return v * (1 + r) ** t - v


class mgr:
    """Lowercase class name, single-letter attributes."""

    def __init__(s, d):
        s.d = d
        s.l = []
        s.c = 0

    def p(s, x):
        s.l.append(x)
        s.c += 1
        if s.c > 100:
            s.l = s.l[-50:]

    def g(s):
        return s.l

    def r(s):
        s.l = []
        s.c = 0


class data_processor:
    """Should be DataProcessor (PEP 8)."""

    def __init__(self):
        self.Data = []  # should be lowercase
        self.ProcessedCount = 0  # should be snake_case

    def ProcessData(self, input_data):
        """Method should be snake_case."""
        for Item in input_data:
            self.Data.append(Item)
            self.ProcessedCount += 1
        return self.Data

    def GetResults(self):
        """Another PascalCase method."""
        return {"data": self.Data, "count": self.ProcessedCount}


def format_currency(amount, decimal_places=2):
    """Magic number usage."""
    if amount > 999999.99:
        return f"${amount / 1000000:.{decimal_places}f}M"
    elif amount > 999.99:
        return f"${amount / 1000:.{decimal_places}f}K"
    else:
        return f"${amount:.{decimal_places}f}"


def calculate_shipping(weight, distance, zone):
    """Full of magic numbers."""
    base = 5.99
    if weight > 50:
        base += 15.00
    elif weight > 20:
        base += 8.50
    elif weight > 5:
        base += 3.25

    if distance > 1000:
        base *= 2.5
    elif distance > 500:
        base *= 1.75
    elif distance > 100:
        base *= 1.25

    if zone == 3:
        base += 12.99
    elif zone == 2:
        base += 7.49
    elif zone == 1:
        base += 3.99

    return round(base, 2)


# ─── Inventory System (God Function + Multiple Responsibilities) ─────────────

def process_inventory_update(warehouse_id, product_id, quantity, action,
                              user_id, reason, timestamp, priority):
    """God function doing too many things."""
    db = DatabaseManager()

    # Validate inputs (deeply nested)
    if warehouse_id:
        if product_id:
            if quantity is not None:
                if action in ("add", "remove", "transfer", "adjust"):
                    if user_id:
                        # Get current stock
                        current = db.raw_query(
                            f"SELECT quantity FROM inventory "
                            f"WHERE warehouse_id = '{warehouse_id}' "
                            f"AND product_id = '{product_id}'"
                        )

                        if action == "remove":
                            if current and current[0][0] >= quantity:
                                new_qty = current[0][0] - quantity
                                db.raw_query(
                                    f"UPDATE inventory SET quantity = {new_qty} "
                                    f"WHERE warehouse_id = '{warehouse_id}' "
                                    f"AND product_id = '{product_id}'"
                                )
                                # Log the action
                                print(f"User {user_id} removed {quantity} of {product_id}")
                                # Send notification
                                if new_qty < 10:
                                    print(f"LOW STOCK ALERT: {product_id} = {new_qty}")
                                    # Email notification — command injection
                                    os.system(f"echo 'Low stock: {product_id}' | mail -s 'Alert' admin@co.com")
                                return {"status": "success", "new_quantity": new_qty}
                            else:
                                return {"status": "error", "message": "Insufficient stock"}

                        elif action == "add":
                            if current:
                                new_qty = current[0][0] + quantity
                            else:
                                new_qty = quantity
                            db.raw_query(
                                f"UPDATE inventory SET quantity = {new_qty} "
                                f"WHERE warehouse_id = '{warehouse_id}' "
                                f"AND product_id = '{product_id}'"
                            )
                            return {"status": "success", "new_quantity": new_qty}

                        elif action == "transfer":
                            # Transfer needs a destination
                            if reason:  # abusing 'reason' as dest warehouse
                                db.raw_query(
                                    f"UPDATE inventory SET quantity = quantity - {quantity} "
                                    f"WHERE warehouse_id = '{warehouse_id}' "
                                    f"AND product_id = '{product_id}'"
                                )
                                db.raw_query(
                                    f"UPDATE inventory SET quantity = quantity + {quantity} "
                                    f"WHERE warehouse_id = '{reason}' "
                                    f"AND product_id = '{product_id}'"
                                )
                                return {"status": "transferred"}

    return {"status": "error", "message": "Invalid input"}


# ─── Email Service (SSRF + Header Injection) ────────────────────────────────

def send_email(to_address, subject, body):
    """Email header injection + logging sensitive content."""
    print(f"Sending to {to_address}: {subject}\n{body}")

    # Header injection via subject
    headers = f"Subject: {subject}\r\nTo: {to_address}\r\n"

    # Using os.system for email — command injection
    os.system(f"echo '{body}' | sendmail {to_address}")

    return True


def send_notification(user_email, message):
    """SSRF via webhook."""
    import requests
    webhook_url = f"http://internal-api.company.com/notify?email={user_email}&msg={message}"
    requests.post(webhook_url)


# ─── Encryption (Weak Crypto) ────────────────────────────────────────────────

def hash_password(password):
    """MD5 for password hashing — cryptographically broken."""
    return hashlib.md5(password.encode()).hexdigest()


def encrypt_data(data, key=ENCRYPTION_KEY):
    """XOR 'encryption' — not real encryption."""
    encrypted = bytearray()
    for i, byte in enumerate(data.encode()):
        encrypted.append(byte ^ key[i % len(key)])
    return bytes(encrypted)


def generate_reset_token(email):
    """Predictable token based on email + time."""
    raw = f"{email}{int(time.time())}"
    return hashlib.sha1(raw.encode()).hexdigest()  # SHA1 is weak


def verify_signature(data, signature):
    """Timing attack via string comparison."""
    expected = hashlib.sha256(data.encode() + JWT_SECRET.encode()).hexdigest()
    return signature == expected  # timing leak


# ─── Logging Service (Sensitive Data Exposure) ───────────────────────────────

class Logger:
    """Logger that exposes sensitive data."""

    def __init__(self):
        self.logs = []

    def log_request(self, request):
        """Logs full request including auth headers and body."""
        entry = {
            "url": request.get("url"),
            "headers": request.get("headers"),  # includes Authorization
            "body": request.get("body"),  # includes passwords
            "cookies": request.get("cookies"),  # includes session tokens
            "ip": request.get("ip"),
            "timestamp": time.time()
        }
        self.logs.append(entry)
        print(f"REQUEST: {json.dumps(entry)}")

    def log_payment(self, payment_info):
        """Logs credit card details."""
        print(f"PAYMENT: card={payment_info['card_number']}, "
              f"cvv={payment_info['cvv']}, amount={payment_info['amount']}")

    def log_error(self, error, context):
        """Logs full stack trace with potentially sensitive locals."""
        print(f"ERROR: {error}\nCONTEXT: {json.dumps(context)}")

    def export_logs(self, filename):
        """Path traversal in log export."""
        with open(filename, "w") as f:
            json.dump(self.logs, f)


# ─── Report Generator (Resource Leaks) ──────────────────────────────────────

def generate_report(template_path, data):
    """File handle never closed."""
    f = open(template_path, "r")
    template = f.read()
    # f.close() missing — resource leak

    for key, value in data.items():
        template = template.replace(f"{{{key}}}", str(value))

    output = open("/tmp/report.html", "w")
    output.write(template)
    # output.close() missing — another leak

    return "/tmp/report.html"


def read_multiple_files(file_list):
    """Opens files without closing — multiple resource leaks."""
    contents = {}
    for filepath in file_list:
        f = open(filepath, "r")
        contents[filepath] = f.read()
        # Never closed
    return contents


# ─── Worker Pool (Thread Safety Issues) ──────────────────────────────────────

class TaskQueue:
    """Task queue with race conditions."""

    def __init__(self):
        self.queue = []
        self.processed = 0
        self.errors = 0

    def add_task(self, task):
        """No synchronization — race condition."""
        self.queue.append(task)

    def process_next(self):
        """TOCTOU: check and pop without lock."""
        if len(self.queue) > 0:
            task = self.queue.pop(0)  # race: another thread might pop first
            self.processed += 1  # race on counter
            return task
        return None

    def get_stats(self):
        """Reading counters without synchronization."""
        return {
            "pending": len(self.queue),
            "processed": self.processed,
            "errors": self.errors,
            "rate": self.processed / (time.time() + 1)  # division issue at epoch
        }


# ─── Data Export (Bare Except + Type Issues) ─────────────────────────────────

class DataExporter:
    """Exporter with multiple issues."""

    def export_csv(self, data, filename):
        """Bare except, path traversal, no encoding handling."""
        try:
            f = open(filename, "w")
            for row in data:
                line = ",".join(str(v) for v in row.values())
                f.write(line + "\n")
            f.close()
        except:
            pass  # silently swallows ALL errors

    def export_json(self, data, filename):
        """Another bare except."""
        try:
            with open(filename, "w") as f:
                json.dump(data, f)
        except:
            return False

    def export_xml(self, data, filename):
        """Building XML via string concatenation — injection risk."""
        xml = '<?xml version="1.0"?>\n<data>\n'
        for item in data:
            xml += f"  <record>\n"
            for key, value in item.items():
                xml += f"    <{key}>{value}</{key}>\n"  # XML injection
            xml += f"  </record>\n"
        xml += "</data>"

        with open(filename, "w") as f:
            f.write(xml)


# ─── URL Router (Open Redirect + Regex DoS) ─────────────────────────────────

def redirect_user(url):
    """Open redirect — no validation of target URL."""
    return {"status": 302, "location": url}


def validate_email_regex(email):
    """ReDoS — catastrophic backtracking on crafted input."""
    pattern = r"^([a-zA-Z0-9_.+-]+)*@([a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}$"
    return bool(re.match(pattern, email))


def validate_url(url):
    """Incomplete URL validation — bypassable."""
    if url.startswith("http://") or url.startswith("https://"):
        return True
    return False


# ─── Utility Functions (Various Issues) ──────────────────────────────────────

def retry(func, max_retries=3, delay=1):
    """Uses time.sleep in a retry loop — blocks thread."""
    for i in range(max_retries):
        try:
            return func()
        except Exception as e:
            if i < max_retries - 1:
                time.sleep(delay * (i + 1))
            else:
                raise


def flatten_dict(d, parent_key="", sep="_"):
    """Recursive without depth limit — stack overflow on circular refs."""
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep).items())
        else:
            items.append((new_key, v))
    return dict(items)


def deep_merge(dict_a, dict_b):
    """Recursive merge without cycle detection."""
    result = dict_a.copy()
    for key, value in dict_b.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def format_output(data, format="json"):
    """Shadows built-in 'format'."""
    if format == "json":
        return json.dumps(data)
    elif format == "csv":
        return ",".join(str(v) for v in data)
    elif format == "xml":
        return f"<data>{data}</data>"


def sanitize_input(text):
    """Incomplete sanitization — blacklist approach is bypassable."""
    dangerous = ["<script>", "javascript:", "onerror="]
    for d in dangerous:
        text = text.replace(d, "")
    return text  # <ScRiPt>, java\nscript:, etc. still work


# ─── Order Processing Pipeline (Multiple Responsibility + Bugs) ──────────────

class OrderPipeline:
    """Order processing with business logic bugs and design issues."""

    def __init__(self):
        self.orders = []
        self.inventory = {}
        self.notifications = []

    def submit_order(self, user_id, items, payment_info, shipping_address):
        """Multiple issues: no validation, logging PII, no transaction."""
        order = {
            "id": random.randint(1000, 9999),  # collision-prone IDs
            "user": user_id,
            "items": items,
            "payment": payment_info,  # storing full card details
            "address": shipping_address,
            "status": "pending",
            "created": time.time()
        }

        # Log full order including payment info
        print(f"New order: {json.dumps(order)}")

        # Check inventory without locking
        for item in items:
            stock = self.inventory.get(item["sku"], 0)
            if stock < item["quantity"]:
                return {"error": f"Insufficient stock for {item['sku']}"}

        # Deduct inventory (race condition — no atomic operation)
        for item in items:
            self.inventory[item["sku"]] -= item["quantity"]

        # Charge payment (no rollback if this fails after inventory deduction)
        processor = PaymentProcessor()
        result = processor.charge(
            payment_info["card_number"],
            payment_info["cvv"],
            sum(i["price"] * i["quantity"] for i in items)
        )

        if result["status"] != "charged":
            # BUG: inventory already deducted but payment failed — no rollback
            return {"error": "Payment failed"}

        self.orders.append(order)
        return order

    def cancel_order(self, order_id):
        """No authorization — anyone can cancel any order."""
        for order in self.orders:
            if order["id"] == order_id:
                order["status"] = "cancelled"
                # BUG: doesn't restore inventory
                return order
        return None

    def get_order_history(self, user_id):
        """O(n) scan every time — no indexing."""
        return [o for o in self.orders if o["user"] == user_id]

    def calculate_total(self, items):
        """Floating point arithmetic for money — precision issues."""
        total = 0.0
        for item in items:
            total += item["price"] * item["quantity"]
            if item.get("discount_pct"):
                total -= total * (item["discount_pct"] / 100)
        tax = total * 0.0875  # magic number tax rate
        return total + tax

    def apply_coupon(self, order_id, coupon_code):
        """No coupon validation, negative discount possible."""
        for order in self.orders:
            if order["id"] == order_id:
                # No check if coupon is valid or already used
                discount = eval(f"order['total'] * {coupon_code}")  # eval injection!
                order["discount"] = discount
                return order
        return None


# ─── Search Engine (ReDoS + Injection) ───────────────────────────────────────

class SearchEngine:
    """Search with multiple vulnerability vectors."""

    def __init__(self):
        self.index = {}
        self.query_log = []

    def search(self, query, filters=None):
        """Logs search queries including potentially sensitive content."""
        self.query_log.append({
            "query": query,
            "filters": filters,
            "timestamp": time.time()
        })

        # SQL injection in search
        db = DatabaseManager()
        results = db.raw_query(
            f"SELECT * FROM products WHERE name LIKE '%{query}%'"
        )
        return results

    def advanced_search(self, pattern):
        """ReDoS via user-supplied regex."""
        try:
            compiled = re.compile(pattern)  # user-controlled regex
            return [k for k in self.index if compiled.match(k)]
        except:
            return []

    def autocomplete(self, prefix):
        """O(n) full scan for autocomplete — should use trie."""
        suggestions = []
        for key in self.index:
            if key.lower().startswith(prefix.lower()):
                suggestions.append(key)
        return sorted(suggestions)[:10]

    def export_query_log(self, filepath):
        """Path traversal + sensitive data in export."""
        with open(filepath, "w") as f:
            json.dump(self.query_log, f)


# ─── Analytics Dashboard (Unsafe Eval + XSS) ────────────────────────────────

class AnalyticsDashboard:
    """Dashboard with client-side injection issues."""

    def __init__(self):
        self.metrics = {}
        self.custom_formulas = {}

    def add_custom_metric(self, name, formula):
        """Stores user formula for later eval — code injection."""
        self.custom_formulas[name] = formula

    def calculate_metric(self, name, data):
        """eval() on stored formula — delayed code injection."""
        if name in self.custom_formulas:
            return eval(self.custom_formulas[name])  # RCE
        return None

    def render_chart(self, title, data_points):
        """XSS in chart title."""
        html = f"""
        <div class="chart">
            <h3>{title}</h3>
            <script>
                var data = {json.dumps(data_points)};
                renderChart(data);
            </script>
        </div>
        """
        return html

    def generate_embed_code(self, dashboard_id, user_token):
        """Exposes user token in embed code."""
        return f'<iframe src="/dashboard/{dashboard_id}?token={user_token}"></iframe>'


# ─── Rate Limiter (Race Condition + Bypass) ──────────────────────────────────

class RateLimiter:
    """Rate limiter with thread-safety and bypass issues."""

    def __init__(self, max_requests=100, window=60):
        self.max_requests = max_requests
        self.window = window
        self.requests = {}

    def is_allowed(self, client_id):
        """TOCTOU race — check and increment not atomic."""
        now = time.time()
        if client_id not in self.requests:
            self.requests[client_id] = []

        # Clean old entries (modifying list during iteration risk)
        self.requests[client_id] = [
            t for t in self.requests[client_id]
            if now - t < self.window
        ]

        if len(self.requests[client_id]) >= self.max_requests:
            return False

        self.requests[client_id].append(now)
        return True

    def get_remaining(self, client_id):
        """No synchronization with is_allowed."""
        if client_id in self.requests:
            return self.max_requests - len(self.requests[client_id])
        return self.max_requests


# ─── Config Manager (Insecure Defaults + Eval) ──────────────────────────────

class ConfigManager:
    """Configuration with insecure patterns."""

    DEFAULTS = {
        "debug": True,  # debug enabled by default in production
        "log_level": "DEBUG",
        "cors_origins": "*",  # allows all origins
        "session_timeout": 86400 * 30,  # 30 day sessions
        "max_upload_size": 1073741824,  # 1GB — too large
        "rate_limit": 0,  # disabled
    }

    def __init__(self):
        self.config = dict(self.DEFAULTS)

    def load_from_file(self, filepath):
        """Eval-based config loading — code injection."""
        with open(filepath, "r") as f:
            for line in f:
                if "=" in line:
                    key, value = line.strip().split("=", 1)
                    self.config[key.strip()] = eval(value.strip())  # RCE

    def load_from_env(self):
        """No validation of environment variables."""
        for key in self.DEFAULTS:
            env_val = os.environ.get(key.upper())
            if env_val:
                self.config[key] = env_val

    def get(self, key, default=None):
        return self.config.get(key, default)

    def dump(self):
        """Dumps config including secrets."""
        print(f"CONFIG: {json.dumps(self.config, default=str)}")
        return self.config


# ─── Session Store (Predictable + No Expiry) ────────────────────────────────

class SessionStore:
    """Session management with multiple weaknesses."""

    def __init__(self):
        self.sessions = {}
        self._counter = 0

    def create_session(self, user_data):
        """Predictable sequential session IDs."""
        self._counter += 1
        session_id = f"sess_{self._counter}"  # trivially guessable
        self.sessions[session_id] = {
            "data": user_data,
            "created": time.time(),
            # No expiry field
        }
        return session_id

    def get_session(self, session_id):
        """No expiration check."""
        return self.sessions.get(session_id, {}).get("data")

    def destroy_session(self, session_id):
        """No verification of ownership."""
        if session_id in self.sessions:
            del self.sessions[session_id]

    def list_all_sessions(self):
        """Exposes all active sessions — information disclosure."""
        return self.sessions


# ─── Main Entry Point ────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Direct user input into vulnerable functions
    user_id = input("Enter user ID: ")
    db = DatabaseManager()
    user = db.get_user(user_id)

    query = input("Search: ")
    results = db.search_users(query, query)

    filename = input("File to read: ")
    content = read_user_file(filename)

    template = input("Template: ")
    rendered = execute_template(template)

    url = input("URL to fetch: ")
    data = fetch_url(url)

    xml = input("XML config: ")
    config = parse_xml_config(xml)

    session = input("Session data: ")
    loaded = load_user_session(session.encode())

    payment = PaymentProcessor()
    payment.charge(input("Card: "), input("CVV: "), float(input("Amount: ")))
