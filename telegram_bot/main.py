import json
import time
import requests
import telepot
from telepot.loop import MessageLoop
from datetime import datetime
from mqtt_client import MQTTClient
from service_registry import ServiceRegistry


def load_config(path="config.telegram.json"):
    with open(path, "r") as f:
        return json.load(f)


class TelegramAquaBot:
    def __init__(self, token, catalog_base, mqtt,
                 user_catalogue_name="user_catalogue",
                 storage_name="storage_service"):

        self.bot = telepot.Bot(token)
        self.catalog_base = catalog_base.rstrip("/")
        self.mqtt = mqtt

        self.user_catalogue_name = user_catalogue_name
        self.storage_name = storage_name

        self.user_catalogue_url = ""
        self.storage_url = ""

        self.device_labels = {}  # device_id -> label

    # --- service discovery ---
    def discover(self):
        self.user_catalogue_url = self._service_url(self.user_catalogue_name)
        self.storage_url = self._service_url(self.storage_name)

        print("[DISCOVERY] user_catalogue =", self.user_catalogue_url)
        print("[DISCOVERY] storage       =", self.storage_url)

    def _service_url(self, name):
        r = requests.get(f"{self.catalog_base}/services/{name}", timeout=4)
        j = r.json()
        return j["service"]["url"].rstrip("/")

    # --- telegram helpers ---
    def send(self, chat_id, text, markup=None):
        if markup:
            self.bot.sendMessage(chat_id, text, reply_markup=markup)
        else:
            self.bot.sendMessage(chat_id, text)

    def devices_menu(self, chat_id, devices):
        keyboard = []

        for d in devices:
            if isinstance(d, dict):
                device_id = str(d.get("device_id") or d.get("id"))
                label = d.get("device_label", device_id)
            else:
                device_id = str(d)
                label = device_id

            self.device_labels[device_id] = label
            keyboard.append([
                {"text": f"🐠 {label}", "callback_data": f"DEV|{device_id}"}
            ])

        self.send(chat_id, "Your devices:", {"inline_keyboard": keyboard})

    def actions_menu(self, chat_id, device_id):
        label = self.device_labels.get(device_id, device_id)

        kb = [
            [
                {"text": "📊 report", "callback_data": f"ACT|{device_id}|REPORT"},
                {"text": "🍽 feeder", "callback_data": f"ACT|{device_id}|FEEDER"},
            ],
            [
                {"text": "🚰 water pump", "callback_data": f"ACT|{device_id}|WATER_PUMP"},
            ],
        ]

        self.send(
            chat_id,
            f"Device selected: {label}\nChoose an action:",
            {"inline_keyboard": kb},
        )

    # --- HTTP calls ---
    def auth(self, password, chat_id):
        r = requests.post(
            f"{self.user_catalogue_url}/auth",
            json={"password": password, "chat_id": str(chat_id)},
            timeout=5,
        )
        return r.json()

    def latest_report(self, device_id):
        r = requests.get(
            f"{self.storage_url}/devices/{device_id}/latest",
            timeout=5,
        )
        return r.json()

    def device_chat_ids(self, device_id):
        r = requests.get(
            f"{self.user_catalogue_url}/device_chat_ids",
            params={"device_id": device_id},
            timeout=5,
        )
        return r.json().get("chat_ids", [])

    # --- MQTT publish ---
    def send_cmd(self, device_id, cmd):
        if cmd == "FEEDER":
            topic = f"aquarium/{device_id}/cmd/feeder"
            payload = {"cmd": "feeder", "ts": int(time.time())}
        else:
            topic = f"aquarium/{device_id}/cmd/water_pump"
            payload = {"cmd": "water_pump", "ts": int(time.time())}

        self.mqtt.publish(topic, payload, qos=0)

    # --- Telegram handlers ---
    def on_chat(self, msg):
        content_type, chat_type, chat_id = telepot.glance(msg)
        if content_type != "text":
            return

        text = msg.get("text", "").strip()

        if text == "/start":
            self.send(chat_id, "Please enter your password:")
            return

        auth = self.auth(text, chat_id)
        if auth.get("status") != "ok":
            self.send(chat_id, "Wrong password. Try again.")
            return

        self.send(chat_id, "✅ Login successful")
        self.devices_menu(chat_id, auth.get("devices", []))

    def on_callback(self, msg):
        _, _, data = telepot.glance(msg, flavor="callback_query")
        chat_id = msg["message"]["chat"]["id"]

        if data.startswith("DEV|"):
            device_id = data.split("|")[1]
            self.actions_menu(chat_id, device_id)
            return

        if data.startswith("ACT|"):
            _, device_id, action = data.split("|")

            if action == "REPORT":
                rep = self.latest_report(device_id)

                label = self.device_labels.get(device_id, device_id)
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                text = (
                    f"📊 Latest data for {label}\n"
                    f"🕒 {now}\n\n"
                    f"{json.dumps(rep, ensure_ascii=False, indent=2)}"
                )

                self.send(chat_id, text)
                return

            self.send_cmd(device_id, action)
            self.send(chat_id, f"✅ Command sent: {action}")

    # --- MQTT alert callback ---
    def on_alert(self, topic, payload):
        device_id = topic.split("/")[1]
        label = self.device_labels.get(device_id, device_id)

        try:
            j = json.loads(payload)
            msg = j.get("message", "Alert")
            level = j.get("level", "warning")
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            text = (
                f"⚠️ ALERT ({level})\n"
                f"🐠 Device: {label}\n"
                f"🕒 {now}\n\n"
                f"{msg}"
            )
        except Exception:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            text = (
                f"⚠️ ALERT\n"
                f"🐠 Device: {label}\n"
                f"🕒 {now}\n\n"
                f"{payload}"
            )

        for cid in self.device_chat_ids(device_id):
            self.send(cid, text)

    def start(self):
        self.discover()

        self.mqtt.connect()
        self.mqtt.subscribe("aquarium/+/alerts", self.on_alert)
        print('[MQTT] Subscribed to "aquarium/+/alerts"')

        print("[Telegram] Bot is running...")
        MessageLoop(
            self.bot,
            {"chat": self.on_chat, "callback_query": self.on_callback},
        ).run_forever()


def main():
    cfg = load_config("config.telegram.json")

    token = cfg["telegram"]["token"]

    catalog_host = cfg["catalog"]["host"]
    catalog_port = cfg["catalog"]["port"]
    catalog_base = f"http://{catalog_host}:{catalog_port}"

    mqtt_broker = cfg["mqtt"]["broker"]
    mqtt_port = cfg["mqtt"]["port"]

    user_catalogue_name = cfg["services"]["user_catalogue_name"]
    storage_name = cfg["services"]["storage_name"]
    ServiceRegistry(catalog_host, catalog_port).register("telegram_bot", "localhost", 8011)

    mqtt = MQTTClient(
        broker=mqtt_broker,
        port=mqtt_port,
        client_id="telegram_bot",
    )

    bot = TelegramAquaBot(
        token,
        catalog_base,
        mqtt,
        user_catalogue_name=user_catalogue_name,
        storage_name=storage_name,
    )

    bot.start()


if __name__ == "__main__":
    main()
