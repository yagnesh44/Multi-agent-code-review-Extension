import os


def read_config(filepath):
    """Read a configuration file."""
    with open(filepath, "r") as f:
        data = f.read()
    return data


def process_items(items):
    """Double all positive items."""
    result = []
    for item in items:
        if item > 0:
            result.append(item * 2)
    return result


class UserService:
    def __init__(self, db):
        self.db = db

    def get_user(self, user_id):
        return self.db.query(f"SELECT * FROM users WHERE id = {user_id}")

    def create_user(self, name, email):
        self.db.execute("INSERT INTO users (name, email) VALUES (?, ?)", (name, email))
