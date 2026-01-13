import sqlite3
import os

class Database:
    def __init__(self, path="monitoring.db"):
        self.path = path
        self._ensure_tables()

    def _ensure_tables(self):
        conn = sqlite3.connect(self.path)
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS sensor_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            device_id TEXT,
            temperature REAL,
            nitrate REAL,
            turbidity REAL,
            leakage REAL,
            prediction TEXT,
            safety_status TEXT
        )""")
        conn.commit()
        conn.close()

    def insert(self, record: dict):
        conn = sqlite3.connect(self.path)
        c = conn.cursor()
        c.execute(
            "INSERT INTO sensor_data (timestamp, device_id, temperature, nitrate, turbidity, leakage, prediction, safety_status) VALUES (?,?,?,?,?,?,?,?)",
            (
                record.get("timestamp"),
                record.get("device_id"),
                record.get("temperature"),
                record.get("nitrate"),
                record.get("turbidity"),
                record.get("leakage"),
                record.get("prediction"),
                record.get("safety_status")
            )
        )
        conn.commit()
        conn.close()

    def get_last(self, device_id):
        conn = sqlite3.connect(self.path)
        c = conn.cursor()
        c.execute(
            "SELECT timestamp, device_id, temperature, nitrate, turbidity, leakage, prediction, safety_status FROM sensor_data WHERE device_id=? ORDER BY id DESC LIMIT 1",
            (device_id,)
        )
        row = c.fetchone()
        conn.close()
        if not row:
            return None
        keys = ["timestamp","device_id","temperature","nitrate","turbidity","leakage","prediction","safety_status"]
        return dict(zip(keys,row))
