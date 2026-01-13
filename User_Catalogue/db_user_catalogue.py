import mariadb


class MariaDB:
  
    def __init__(self, host, port, user, password, database):
        self.config = {
            "host": host,
            "port": int(port),
            "user": user,
            "password": password,
            "database": database,
            "autocommit": True,
        }

    # Creates connection
    def connect(self):
        return mariadb.connect(**self.config)

    # Inserts a new user and returns the generated user_id 
    def create_user(self, username, password):
        conn = self.connect()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (username, password, telegram_chat_id) VALUES (?, ?, NULL)",
            (username, password),
        )
        user_id = cur.lastrowid
        conn.close()
        return user_id

    # Returns a list of all users
    def list_users(self):
        conn = self.connect()
        cur = conn.cursor()
        cur.execute("SELECT id, username, telegram_chat_id FROM users ORDER BY id DESC")

        users = []
        for r in cur.fetchall():
            users.append({
                "user_id": r[0],
                "username": r[1],
                "telegram_chat_id": r[2]
            })

        conn.close()
        return users

    # Returns a single user by id
    def get_user_by_id(self, user_id):
        conn = self.connect()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, username, telegram_chat_id FROM users WHERE id = ?",
            (user_id,),
        )
        r = cur.fetchone()
        conn.close()

        return {
            "user_id": r[0],
            "username": r[1],
            "telegram_chat_id": r[2]
        }

    # Returns a single user matched by password 
    def get_user_by_password(self, password):
        conn = self.connect()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, username, telegram_chat_id FROM users WHERE password = ?",
            (password,),
        )
        r = cur.fetchone()
        conn.close()

        return {
            "user_id": r[0],
            "username": r[1],
            "telegram_chat_id": r[2]
        }

    # Updates the Telegram chat_id of a user 
    def update_chat_id(self, user_id, chat_id):
        conn = self.connect()
        cur = conn.cursor()
        cur.execute(
            "UPDATE users SET telegram_chat_id = ? WHERE id = ?",
            (str(chat_id), int(user_id)),
        )
        conn.close()

    # Inserts a device or updates its label if it already exists 
    def upsert_device(self, device_id, device_label=None):
        conn = self.connect()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO devices (device_id, device_label) VALUES (?, ?) "
            "ON DUPLICATE KEY UPDATE device_label = VALUES(device_label)",
            (device_id, device_label),
        )
        conn.close()

    # Assigns a device to a user 
    def assign_device_to_user(self, user_id, device_id):
        conn = self.connect()
        cur = conn.cursor()
        cur.execute(
            "INSERT IGNORE INTO user_devices (user_id, device_id) VALUES (?, ?)",
            (int(user_id), device_id),
        )
        conn.close()

    # Removes a device assignment from a user 
    def unassign_device_from_user(self, user_id, device_id):
        conn = self.connect()
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM user_devices WHERE user_id = ? AND device_id = ?",
            (int(user_id), device_id),
        )
        conn.close()

    # Returns all devices assigned to a user
    def get_devices_for_user(self, user_id):
        conn = self.connect()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT d.device_id, d.device_label
            FROM devices d
            JOIN user_devices ud ON d.device_id = ud.device_id
            WHERE ud.user_id = ?
            ORDER BY d.device_id
            """,
            (int(user_id),),
        )

        devices = []
        for r in cur.fetchall():
            devices.append({
                "device_id": r[0],
                "device_label": r[1]
            })

        conn.close()
        return devices

    # Returns all users assigned to a device 
    def get_users_for_device(self, device_id):
        conn = self.connect()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT u.id, u.username, u.telegram_chat_id
            FROM users u
            JOIN user_devices ud ON u.id = ud.user_id
            WHERE ud.device_id = ?
            ORDER BY u.id
            """,
            (device_id,),
        )

        users = []
        for r in cur.fetchall():
            users.append({
                "user_id": r[0],
                "username": r[1],
                "telegram_chat_id": r[2]
            })

        conn.close()
        return users

    # Returns Telegram chat_ids for all users assigned to a device 
    def get_chat_ids_by_device(self, device_id):
        conn = self.connect()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT u.telegram_chat_id
            FROM users u
            JOIN user_devices ud ON u.id = ud.user_id
            WHERE ud.device_id = ?
              AND u.telegram_chat_id IS NOT NULL
            """,
            (device_id,),
        )

        chat_ids = []
        for r in cur.fetchall():
            chat_ids.append(r[0])

        conn.close()
        return chat_ids