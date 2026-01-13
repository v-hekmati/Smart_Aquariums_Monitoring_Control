import json
import time
import requests

from mqtt_client import MQTTClient
from service_registry import ServiceRegistry


def now_ts():
    return int(time.time())


# --------------------------------------------------
# Device thresholds cache 
# --------------------------------------------------
class DeviceConfigCache:
    def __init__(self, catalogue_base_url, ttl_seconds):
        self.base = catalogue_base_url.rstrip("/")
        self.ttl = ttl_seconds
        self.cache = {}   # device_id -> {"ts": int, "thresholds": {...}}

    def get_thresholds(self, device_id):
        entry = self.cache.get(device_id)
        if entry and now_ts() - entry["ts"] <= self.ttl:
            return entry["thresholds"]

        thresholds = self.fetch_from_catalogue(device_id)
        if thresholds is None:
            thresholds = {}

        self.cache[device_id] = {
            "ts": now_ts(),
            "thresholds": thresholds
        }
        return thresholds

    def fetch_from_catalogue(self, device_id):
        try:
            r = requests.get(f"{self.base}/devices/{device_id}", timeout=4)
            if r.status_code != 200:
                print(f"[RESOURCE] {device_id} -> {r.status_code}")
                return None

            data = r.json()
            device = data.get("device")
            resources = device.get("resources") if device else None
            if not isinstance(resources, list):
                return None

            out = {}
            for res in resources:
                if res.get("kind") != "sensor":
                    continue

                thr = res.get("threshold")
                if not thr:
                    continue

                mn = thr.get("min")
                mx = thr.get("max")
                if mn is None or mx is None:
                    continue

                out[res["name"]] = {
                    "min": float(mn),
                    "max": float(mx)
                }

            return out

        except Exception as e:
            print(f"[RESOURCE] fetch error: {e}")
            return None


# --------------------------------------------------
# Monitoring Service
# --------------------------------------------------
class MonitoringService:
    def __init__(self, cfg):
        self.name = cfg.get("service_name", "monitoring_service")
        self.host = cfg.get("host", "localhost")
        self.port = int(cfg.get("port", 8091))

        self.catalogue_base_url = ( f"http://{cfg.get('catalog_host', 'localhost')}:"
            f"{cfg.get('catalog_port', 8080)}"
        )

        self.mqtt = MQTTClient(
            broker=cfg.get("mqtt_broker", "localhost"),
            port=int(cfg.get("mqtt_port", 1883)),
            client_id=self.name
        )

        self.cache = DeviceConfigCache(
            self.catalogue_base_url,
            cfg.get("cache_ttl_seconds", 120)
        )

        self.pump_cooldown = int(cfg.get("pump_cooldown_sec", 180 * 60))
        self.last_pump_ts = {}

        # ---- ONE simple request for prediction service ----
        self.predict_base_url = None
        try:
            r = requests.get(
                f"{self.catalogue_base_url}/services/prediction_service",
                timeout=4
            )
            if r.status_code == 200:
                self.predict_base_url = r.json()["service"]["url"]
                print(f"[MON] prediction service -> {self.predict_base_url}")
            else:
                print("[MON] prediction service not found")
        except Exception as e:
            print(f"[MON] catalogue unreachable: {e}")

    def start(self):
        registry = ServiceRegistry(
            self.catalogue_base_url.split("//")[1].split(":")[0],
            int(self.catalogue_base_url.split(":")[-1])
        )
        registry.register(self.name, self.host, self.port)

        self.mqtt.connect()
        self.mqtt.subscribe("aquarium/+/sensors/agg", self.on_agg_sensors)
        print("[MON] Started")

        while True:
            time.sleep(1)

    def on_agg_sensors(self, topic, payload):
        try:
            data = json.loads(payload)
        except Exception:
            return

        device_id = data.get("device_id") or topic.split("/")[1]
        thresholds = self.cache.get_thresholds(device_id)

        alerts = []

        # STRICT threshold checks
        for sensor, rule in thresholds.items():
            val = data.get(sensor)
            if isinstance(val, (int, float)):
                if val < rule["min"] or val > rule["max"]:
                    alerts.append({
                        "device_id": device_id,
                        "level": "warning",
                        "message": f"{sensor} out of range",
                        "ts": now_ts()
                    })

        # Prediction (nitrate + turbidity only)
        nitrate = data.get("nitrate")
        turbidity = data.get("turbidity")

        if (
            self.predict_base_url
            and isinstance(nitrate, (int, float))
            and isinstance(turbidity, (int, float))
        ):
            pred = self.call_prediction(nitrate, turbidity)
            if pred and pred.get("water_quality") == "bad":
                alerts.append({
                    "device_id": device_id,
                    "level": "danger",
                    "message": "Bad water quality (prediction)",
                    "ts": now_ts()
                })
                self.send_pump_command(device_id)

        for a in alerts:
            self.mqtt.publish(f"aquarium/{device_id}/alerts", a)

    def call_prediction(self, nitrate, turbidity):
        try:
            r = requests.post(
                f"{self.predict_base_url}/predict",
                json={"nitrate": nitrate, "turbidity": turbidity},
                timeout=4
            )
            if r.status_code == 200:
                return r.json()
        except Exception as e:
            print(f"[MON] prediction error: {e}")
        return None

    def send_pump_command(self, device_id):
        now = now_ts()
        last = self.last_pump_ts.get(device_id, 0)
        if now - last < self.pump_cooldown:
            return

        self.mqtt.publish(
            f"aquarium/{device_id}/cmd/water_pump",
            {"device_id": device_id, "action": "on", "ts": now}
        )
        self.last_pump_ts[device_id] = now


# --------------------------------------------------
# Main
# --------------------------------------------------
def load_config():
    with open("config.json", "r") as f:
        return json.load(f)


def main():
    config = load_config()
    monitoring_service = MonitoringService(config)
    monitoring_service.start()

if __name__ == "__main__":
    main()
