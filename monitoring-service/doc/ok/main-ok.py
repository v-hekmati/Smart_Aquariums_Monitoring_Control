import json
import time

import requests

from mqtt_client import MQTTClient
from service_registry import ServiceRegistry


def now_ts():
    return int(time.time())


class DeviceConfigCache:
    """
    Simple cache for thresholds:
    - first message per device -> fetch thresholds from Resource Catalogue
    - refresh after ttl_seconds
    - refresh immediately if a new sensor key appears in MQTT payload
    """

    def __init__(self, catalogue_base_url, ttl_seconds):
        self.catalogue_base_url = catalogue_base_url.rstrip("/")
        self.ttl_seconds = int(ttl_seconds)
        self.cache = {}  # device_id -> {"ts": int, "thresholds": {...}}

        self.fallback_thresholds = {
            "temperature": {"min": 25, "max": 29},
            "leakage": {"min": 0, "max": 0},
        }

    def get_thresholds(self, device_id):
        entry = self.cache.get(device_id)
        if entry and (now_ts() - entry["ts"] <= self.ttl_seconds):
            return entry["thresholds"]

        thresholds = self.fetch_from_catalogue(device_id)
        if not thresholds:
            thresholds = self.fallback_thresholds

        self.cache[device_id] = {"ts": now_ts(), "thresholds": thresholds}
        return thresholds

    def force_refresh(self, device_id):
        thresholds = self.fetch_from_catalogue(device_id)
        if not thresholds:
            thresholds = self.fallback_thresholds
        self.cache[device_id] = {"ts": now_ts(), "thresholds": thresholds}
        return thresholds

    def fetch_from_catalogue(self, device_id):
        """
        Default:
          GET {catalogue_base_url}/resources/devices/<device_id>
 """ """
        Expected JSON example in Resource Catalogue endpoint/format:
          {
            "device_id": "12aaff42",
            "sensors": [
              {"name":"temperature", "min":25, "max":29},
              {"name":"leakage", "min":0, "max":0},
              {"name":"nitrate", "min":0, "max":40},
              {"name":"turbidity", "min":0, "max":5}
            ]
          }
        """
        url = f"{self.catalogue_base_url}/resources/devices/{device_id}"
        try:
            r = requests.get(url, timeout=4)
            if r.status_code != 200:
                print(f"[RESOURCE] GET {url} -> {r.status_code} {r.text}")
                return None

            data = r.json()
            sensors = data.get("sensors") or data.get("resources") or []
            out = {}

            for s in sensors:
                name = s.get("name") or s.get("sensor") or s.get("resource")
                if not name:
                    continue

                mn = s.get("min")
                mx = s.get("max")

                # allow catalogue to omit nitrate/turbidity min/max (prediction handles them)
                if mn is None or mx is None:
                    continue

                out[name] = {"min": float(mn), "max": float(mx)}

            if not out:
                return None

            print(f"[RESOURCE] Loaded thresholds for {device_id}: {out}")
            return out

        except Exception as e:
            print(f"[RESOURCE] fetch failed for {device_id}: {e}")
            return None


class MonitoringService:
    def __init__(self, cfg):
        self.name = cfg.get("service_name", "monitoring_service")
        self.host = cfg.get("host", "localhost")
        self.port = int(cfg.get("port", 8091))

        self.catalog_host = cfg.get("catalog_host", "localhost")
        self.catalog_port = int(cfg.get("catalog_port", 8080))
        self.catalogue_base_url = f"http://{self.catalog_host}:{self.catalog_port}"

        self.mqtt_broker = cfg.get("mqtt_broker", "localhost")
        self.mqtt_port = int(cfg.get("mqtt_port", 1883))

        self.predict_host = cfg.get("predict_host", "localhost")
        self.predict_port = int(cfg.get("predict_port", 8092))
        self.predict_url = f"http://{self.predict_host}:{self.predict_port}/predict"

        self.cache = DeviceConfigCache(self.catalogue_base_url, cfg.get("cache_ttl_seconds", 120))

        self.mqtt = MQTTClient(
            broker=self.mqtt_broker,
            port=self.mqtt_port,
            client_id=self.name
        )

        # ---------------- COOLDOWN POLICY (anti-spam) ----------------
        # We do NOT want to publish "pump ON" on every incoming sensor message.
        # So we remember the last time we sent the pump command for each device.
        # If the time difference is less than cooldown_sec (e.g., 180 minutes),
        # we skip sending the command.
        self.pump_cooldown_sec = int(cfg.get("pump_cooldown_sec", 180 * 60))  # default: 180 minutes
        self.last_pump_on_ts = {}  # device_id -> last command timestamp (epoch seconds)

    def start(self):
        registry = ServiceRegistry(catalog_host=self.catalog_host, catalog_port=self.catalog_port)
        registry.register(self.name, self.host, self.port)

        self.mqtt.connect()
        self.mqtt.subscribe("aquarium/+/sensors/agg", self.on_agg_sensors)
        print("[MON] Started. Subscribed to aquarium/+/sensors/agg")

        while True:
            time.sleep(1)

    def on_agg_sensors(self, topic, payload_str):
        try:
            data = json.loads(payload_str)
        except Exception:
            print(f"[MON] Bad JSON on {topic}: {payload_str}")
            return

        device_id = self.extract_device_id(topic, data)
        if not device_id:
            print(f"[MON] Could not determine device_id from topic/payload: {topic}")
            return

        thresholds = self.cache.get_thresholds(device_id)

        if self.new_sensor_detected(thresholds, data):
            print(f"[MON] New sensor detected for {device_id} -> refresh thresholds")
            thresholds = self.cache.force_refresh(device_id)

        alerts = []

        # Threshold checks (except nitrate/turbidity)
        for sensor_name, rule in thresholds.items():
            if sensor_name in ("nitrate", "turbidity"):
                continue
            if sensor_name not in data:
                continue

            val = data.get(sensor_name)
            if not isinstance(val, (int, float)):
                continue

            if val < rule["min"] or val > rule["max"]:
                alerts.append(self.make_alert(device_id, data, sensor_name, val, rule))

        # Prediction (nitrate + turbidity)
        nitrate = data.get("nitrate")
        turbidity = data.get("turbidity")

        prediction = None
        if isinstance(nitrate, (int, float)) and isinstance(turbidity, (int, float)):
            prediction = self.call_prediction(float(nitrate), float(turbidity))

        if prediction and prediction.get("water_quality") == "bad":
            alerts.append({
                "device_id": device_id,
                "level": "danger",
                "message": "Water quality prediction: BAD (based on nitrate & turbidity)",
                "ts": data.get("ts", now_ts()),
                "meta": {"prediction": prediction}
            })

            # Publish pump command ONLY if cooldown has expired
            self.publish_water_pump_on_with_cooldown(device_id)

        for alert in alerts:
            self.publish_alert(device_id, alert)

    def extract_device_id(self, topic, data):
        if isinstance(data.get("device_id"), str):
            return data["device_id"]
        parts = topic.split("/")
        if len(parts) >= 2 and parts[0] == "aquarium":
            return parts[1]
        return None

    def new_sensor_detected(self, thresholds, data):
        known = set(thresholds.keys()) | {"device_id", "ts", "nitrate", "turbidity"}
        for k in data.keys():
            if k not in known and isinstance(data.get(k), (int, float)):
                return True
        return False

    def make_alert(self, device_id, data, sensor_name, value, rule):
        return {
            "device_id": device_id,
            "level": "warning",
            "message": f"Threshold violation: {sensor_name} ({value} outside [{rule['min']}, {rule['max']}])",
            "ts": data.get("ts", now_ts()),
            "meta": {"sensor": sensor_name, "value": value, "threshold": rule}
        }

    def call_prediction(self, nitrate, turbidity):
        try:
            r = requests.post(self.predict_url, json={"nitrate": nitrate, "turbidity": turbidity}, timeout=4)
            if r.status_code != 200:
                print(f"[MON] prediction failed -> {r.status_code} {r.text}")
                return None
            return r.json()
        except Exception as e:
            print(f"[MON] prediction call error -> {e}")
            return None

    def publish_alert(self, device_id, alert):
        topic = f"aquarium/{device_id}/alerts"
        self.mqtt.publish(topic, alert)
        print(f"[MON] alert -> {topic} {alert.get('message')}")

    def publish_water_pump_on_with_cooldown(self, device_id):
        """
        Cooldown logic:
          - If we NEVER sent pump ON for this device -> send now.
          - Else if (now - last_sent) >= cooldown_sec -> send now.
          - Else -> skip (avoid spamming command).
        """
        now = now_ts()
        last = self.last_pump_on_ts.get(device_id, 0)

        # Not enough time passed -> skip
        if (now - last) < self.pump_cooldown_sec:
            remaining = self.pump_cooldown_sec - (now - last)
            print(f"[MON] pump command skipped (cooldown). device={device_id} remaining={remaining}s")
            return

        # Cooldown passed -> publish and remember timestamp
        self.publish_water_pump_on(device_id)
        self.last_pump_on_ts[device_id] = now

    def publish_water_pump_on(self, device_id):
        topic = f"aquarium/{device_id}/cmd/water_pump"
        cmd = {"device_id": device_id, "command": "water_pump", "action": "on", "ts": now_ts()}
        self.mqtt.publish(topic, cmd)
        print(f"[MON] command -> {topic} ON")


def load_config():
    with open("config.json", "r") as f:
        return json.load(f)


def main():

    config = load_config()
    monitoring_service = MonitoringService(config)
    monitoring_service.start()


if __name__ == "__main__":
    main()
