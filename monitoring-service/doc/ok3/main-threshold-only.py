
import json
import time
from typing import Any, Dict, Optional

import requests

from mqtt_client import MQTTClient
from service_registry import ServiceRegistry


def now_ts() -> int:
    return int(time.time())


# --------------------------------------------------
# Device config cache (thresholds only)
# --------------------------------------------------
class DeviceThresholdCache:
    """
    Caches per-device sensor thresholds loaded from the Resource/Service Catalogue.

    It tries (in order):
      1) GET {base}/devices/{device_id}            (newer catalogue format)
      2) GET {base}/resources/devices/{device_id}  (older/course format)

    It extracts, per sensor:
      - threshold: threshold.min / threshold.max

    Returned shape:
      {
        "temperature": {"min": 25, "max": 29},
        "nitrate":     {"min": 0,  "max": 40},
        ...
      }
    """

    def __init__(self, catalogue_base_url: str, ttl_seconds: int = 120):
        self.base = catalogue_base_url.rstrip("/")
        self.ttl = int(ttl_seconds)
        self.cache: Dict[str, Dict[str, Any]] = {}  # device_id -> {"ts": int, "thr": {...}}

    def get_thresholds(self, device_id: str, force: bool = False) -> Dict[str, Dict[str, float]]:
        entry = self.cache.get(device_id)
        if (not force) and entry and (now_ts() - entry["ts"] <= self.ttl):
            return entry["thr"]

        thr = self._fetch_thresholds(device_id) or {}
        self.cache[device_id] = {"ts": now_ts(), "thr": thr}
        return thr

    # -------------------- internal helpers --------------------
    def _fetch_thresholds(self, device_id: str) -> Optional[Dict[str, Dict[str, float]]]:
        thr = self._fetch_from_devices_endpoint(device_id)
        if thr:
            return thr
        thr = self._fetch_from_resources_endpoint(device_id)
        if thr:
            return thr
        return None

    def _fetch_from_devices_endpoint(self, device_id: str) -> Optional[Dict[str, Dict[str, float]]]:
        url = f"{self.base}/devices/{device_id}"
        try:
            r = requests.get(url, timeout=4)
            if r.status_code != 200:
                return None
            data = r.json()
            device = data.get("device") or {}
            resources = device.get("resources")
            if not isinstance(resources, list):
                return None

            out: Dict[str, Dict[str, float]] = {}
            for res in resources:
                if res.get("kind") != "sensor":
                    continue
                name = res.get("name")
                if not name:
                    continue

                t = self._extract_threshold(res)
                if t:
                    out[name] = t
            return out or None
        except Exception as e:
            print(f"[MON] catalogue fetch error (devices endpoint): {e}")
            return None

    def _fetch_from_resources_endpoint(self, device_id: str) -> Optional[Dict[str, Dict[str, float]]]:
        url = f"{self.base}/resources/devices/{device_id}"
        try:
            r = requests.get(url, timeout=4)
            if r.status_code != 200:
                return None
            data = r.json()
            sensors = data.get("sensors") or data.get("resources") or []
            if not isinstance(sensors, list):
                return None

            out: Dict[str, Dict[str, float]] = {}
            for s in sensors:
                name = s.get("name") or s.get("sensor") or s.get("resource")
                if not name:
                    continue

                t = self._extract_threshold(s)
                if t:
                    out[name] = t
            return out or None
        except Exception as e:
            print(f"[MON] catalogue fetch error (resources endpoint): {e}")
            return None

    @staticmethod
    def _extract_threshold(obj: Dict[str, Any]) -> Optional[Dict[str, float]]:
        thr = obj.get("threshold")
        if isinstance(thr, dict):
            mn = thr.get("min")
            mx = thr.get("max")
        else:
            mn = obj.get("threshold_min")
            mx = obj.get("threshold_max")

        if mn is None or mx is None:
            return None
        try:
            return {"min": float(mn), "max": float(mx)}
        except Exception:
            return None


# --------------------------------------------------
# Monitoring Service (threshold checks + prediction)
# --------------------------------------------------
class MonitoringService:
    def __init__(self, cfg: Dict[str, Any]):
        self.name = cfg.get("service_name", "monitoring_service")
        self.host = cfg.get("host", "localhost")
        self.port = int(cfg.get("port", 8091))

        self.catalog_host = cfg.get("catalog_host", "localhost")
        self.catalog_port = int(cfg.get("catalog_port", 8080))
        self.catalogue_base_url = f"http://{self.catalog_host}:{self.catalog_port}"

        self.mqtt = MQTTClient(
            broker=cfg.get("mqtt_broker", "localhost"),
            port=int(cfg.get("mqtt_port", 1883)),
            client_id=self.name,
        )

        self.cache = DeviceThresholdCache(
            self.catalogue_base_url,
            cfg.get("cache_ttl_seconds", 120),
        )

        # anti-spam pump command
        self.pump_cooldown_sec = int(cfg.get("pump_cooldown_sec", 180 * 60))
        self.last_pump_on_ts: Dict[str, int] = {}

        # Prediction service URL (from catalogue; fallback to config)
        self.predict_base_url: Optional[str] = None
        self._init_prediction_url(cfg)

    # -------------------- startup --------------------
    def _init_prediction_url(self, cfg: Dict[str, Any]) -> None:
        # 1) try to resolve from catalogue
        try:
            r = requests.get(f"{self.catalogue_base_url}/services/prediction_service", timeout=4)
            if r.status_code == 200:
                js = r.json()
                svc = js.get("service") or {}
                url = svc.get("url")
                if isinstance(url, str) and url.startswith("http"):
                    self.predict_base_url = url.rstrip("/")
                    print(f"[MON] prediction service -> {self.predict_base_url}")
                    return
        except Exception as e:
            print(f"[MON] prediction service lookup failed: {e}")

        # 2) fallback to config
        ph = cfg.get("predict_host")
        pp = cfg.get("predict_port")
        if ph and pp:
            self.predict_base_url = f"http://{ph}:{int(pp)}"
            print(f"[MON] prediction service (fallback) -> {self.predict_base_url}")
        else:
            print("[MON] prediction service not configured")

    def start(self) -> None:
        registry = ServiceRegistry(self.catalog_host, self.catalog_port)
        registry.register(self.name, self.host, self.port)

        self.mqtt.connect()
        self.mqtt.subscribe("aquarium/+/sensors/agg", self.on_agg_sensors)
        print("[MON] Started")

        while True:
            time.sleep(1)

    # -------------------- message handling --------------------
    def on_agg_sensors(self, topic: str, payload: str) -> None:
        try:
            data = json.loads(payload)
        except Exception:
            print(f"[MON] Bad JSON on {topic}: {payload}")
            return

        device_id = self._extract_device_id(topic, data)
        if not device_id:
            print(f"[MON] Could not determine device_id from topic/payload: {topic}")
            return

        thresholds = self.cache.get_thresholds(device_id)
        alerts = []

        # Threshold checks for ALL sensors that have thresholds in catalogue
        for sensor_name, t in thresholds.items():
            val = data.get(sensor_name)
            if not isinstance(val, (int, float)):
                continue

            if self._outside(float(val), t.get("min"), t.get("max")):
                alerts.append(self._make_alert(
                    device_id=device_id,
                    level="warning",
                    message=f"Threshold violation: {sensor_name} ({val} outside [{t.get('min')}, {t.get('max')}])",
                    ts=data.get("ts", now_ts()),
                    meta={"sensor": sensor_name, "value": val, "threshold": t},
                ))

        # Prediction uses ONLY nitrate + turbidity
        nitrate = data.get("nitrate")
        turbidity = data.get("turbidity")
        if (
            self.predict_base_url
            and isinstance(nitrate, (int, float))
            and isinstance(turbidity, (int, float))
        ):
            pred = self._call_prediction(float(nitrate), float(turbidity))
            if pred and pred.get("water_quality") == "bad":
                alerts.append(self._make_alert(
                    device_id=device_id,
                    level="danger",
                    message="Bad water quality (prediction based on nitrate & turbidity)",
                    ts=data.get("ts", now_ts()),
                    meta={"prediction": pred, "nitrate": nitrate, "turbidity": turbidity},
                ))
                self._publish_pump_on_with_cooldown(device_id)

        # publish alerts
        for a in alerts:
            self.mqtt.publish(f"aquarium/{device_id}/alerts", a)

    # -------------------- utils --------------------
    @staticmethod
    def _extract_device_id(topic: str, data: Dict[str, Any]) -> Optional[str]:
        if isinstance(data.get("device_id"), str):
            return data["device_id"]
        parts = topic.split("/")
        if len(parts) >= 2 and parts[0] == "aquarium":
            return parts[1]
        return None

    @staticmethod
    def _outside(val: float, mn: Any, mx: Any) -> bool:
        try:
            mn_f = float(mn)
            mx_f = float(mx)
        except Exception:
            return False
        return val < mn_f or val > mx_f

    @staticmethod
    def _make_alert(device_id: str, level: str, message: str, ts: int, meta: Dict[str, Any]) -> Dict[str, Any]:
        return {"device_id": device_id, "level": level, "message": message, "ts": int(ts), "meta": meta}

    def _call_prediction(self, nitrate: float, turbidity: float) -> Optional[Dict[str, Any]]:
        try:
            r = requests.post(
                f"{self.predict_base_url}/predict",
                json={"nitrate": nitrate, "turbidity": turbidity},
                timeout=4,
            )
            if r.status_code != 200:
                print(f"[MON] prediction failed -> {r.status_code} {r.text}")
                return None
            return r.json()
        except Exception as e:
            print(f"[MON] prediction error: {e}")
            return None

    def _publish_pump_on_with_cooldown(self, device_id: str) -> None:
        now = now_ts()
        last = self.last_pump_on_ts.get(device_id, 0)
        if (now - last) < self.pump_cooldown_sec:
            return

        self.mqtt.publish(
            f"aquarium/{device_id}/cmd/water_pump",
            {"device_id": device_id, "command": "water_pump", "action": "on", "ts": now},
        )
        self.last_pump_on_ts[device_id] = now


# --------------------------------------------------
# Main
# --------------------------------------------------
def load_config() -> Dict[str, Any]:
    with open("config.json", "r") as f:
        return json.load(f)


def main() -> None:
    config = load_config()
    MonitoringService(config).start()


if __name__ == "__main__":
    main()
