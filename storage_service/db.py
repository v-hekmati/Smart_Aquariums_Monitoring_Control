import mariadb


class MariaDB:
    def __init__(self, host, port, user, password, database):
        self.config = {
            "host": host,
            "port": port,
            "user": user,
            "password": password,
            "database": database,
            "autocommit": True
        }

    def connect(self):
        return mariadb.connect(**self.config)

    # -------------------------
    # INSERT aggregated sensor data (from MQTT)
    # -------------------------
    def insert_measurements(self, device_id, ts, data_dict):
        """
        data_dict example:
        {
            "temperature": 27.4,
            "nitrate": 18.2,
            ...
        }
        """
        rows = []
        for sensor, value in data_dict.items():
            # Store only numeric values (sensor measurements)
            if isinstance(value, (int, float, bool)):
                rows.append((device_id, ts, sensor, float(value)))

        # If no valid sensor data exists, do nothing
        if not rows:
            return

        conn = self.connect()
        cur = conn.cursor()
        cur.executemany(
            "INSERT INTO measurements (device_id, ts, sensor, value) VALUES (?, ?, ?, ?)",
            rows
        )
        conn.close()

    # ---------------------------------------
    # SELECT latest data for all sensors
    # ---------------------------------------
    def get_latest(self, device_id):
        conn = self.connect()
        cur = conn.cursor()

        # 1) Get latest timestamp for the device
        cur.execute(
            "SELECT MAX(ts) FROM measurements WHERE device_id = ?",(device_id,)
        )
        row = cur.fetchone()
        if row is None or row[0] is None:
            conn.close()
            return None

        last_ts = row[0]

        # 2) Get all sensor values for the same timestamp
        cur.execute(
            "SELECT sensor, value FROM measurements WHERE device_id = ? AND ts = ?",(device_id, last_ts)
        )

        measurements = {}
        for sensor, value in cur.fetchall():
            measurements[sensor] = float(value)

        conn.close()

        return {
            "device_id": device_id,
            "ts": last_ts,
            "measurements": measurements
        }
