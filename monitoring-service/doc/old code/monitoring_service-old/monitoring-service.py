import json
import time
import requests

from mqtt_client import MqttClient

# ----------------------------
# Simple Monitoring Service
# - Dynamic threshold checks (from Resource Catalogue)
# - Prediction ONLY for nitrate + turbidity (stub left for you)
# ----------------------------

# MQTT
MQTT_BROKER = "localhost"
MQTT_PORT = 1883
BASE_TOPIC = "aquarium"
SUB_TOPIC = f"{BASE_TOPIC}/+/sensors/agg"

# Catalogue (Resource Catalogue)
CATALOGUE_BASE_URL = "http://localhost:8080"  # change if needed

# Alerts + Commands
ALERT_TOPIC_FMT = BASE_TOPIC + "/{device_id}/alerts"
PUMP_CMD_TOPIC_FMT = BASE_TOPIC + "/{device_id}/cmd/water_pump"

# Prevent pump spam
PUMP_COOLDOWN_SEC = 30 * 60  # 30 minutes


class MonitoringService:
    def __init__(self):
        self.mqtt = MqttClient(
            broker=MQTT_BROKER,
            port=MQTT_PORT,
            client_id="monitoring_service",
        )

        # device_id -> { sensor_name -> threshold_dict }
        self.threshold_cache = {}

        # device_id -> last pump timestamp
        self.last_pump_on = {}

    # ----------------------------
    # Catalogue helpers
    # ----------------------------

    def fetch_thresholds(self, device_id):
        """GET /devices/<device_id> and extract thresholds for sensors."""
        url = f"{CATALOGUE_BASE_URL}/devices/{device_id}"
        r = requests.get(url, timeout=5)
        r.raise_for_status()
        data = r.json()

        device = data.get("device", {})
        resources = device.get("resources", [])

        thresholds = {}
        for res in resources:
            if res.get("kind") != "sensor":
                continue
            name = res.get("name")
            thr = res.get("threshold")
            if name and thr:
                thresholds[name] = thr

        return thresholds

    def get_thresholds_cached(self, device_id):
        """Return cached thresholds; fetch if missing."""
        if device_id not in self.threshold_cache:
            self.threshold_cache[device_id] = self.fetch_thresholds(device_id)
        return self.threshold_cache[device_id]

    def refresh_thresholds(self, device_id):
        self.threshold_cache[device_id] = self.fetch_thresholds(device_id)
        return self.threshold_cache[device_id]

    # ----------------------------
    # Threshold checks (generic)
    # ----------------------------

    def threshold_violated(self, value, threshold):
        """Return (violated_bool, reason_str). Supports:
           - {'min': x, 'max': y}
           - {'max': y}
           - {'min': x}
           - {'allowed': [..]}  (special-case: allowed=[0] for leakage -> value > 0 is violation)
        """
        # allowed-values (e.g. leakage)
        if isinstance(threshold, dict) and "allowed" in threshold:
            allowed = threshold.get("allowed", [])
            # leakage semantic: if allowed=[0] and numeric -> any >0 means leakage occurred in window
            if allowed == [0]:
                try:
                    v = float(value)
                    if v > 0:
                        return True, f"value={v} indicates leakage event(s)"
                    return False, "ok"
                except Exception:
                    # fall back to membership check
                    pass

            if value not in allowed:
                return True, f"value={value} not in allowed={allowed}"
            return False, "ok"

        # numeric range checks
        reasons = []
        violated = False

        if isinstance(threshold, dict) and "min" in threshold:
            try:
                if float(value) < float(threshold["min"]):
                    violated = True
                    reasons.append(f"{value} < min({threshold['min']})")
            except Exception:
                return False, "non-numeric"

        if isinstance(threshold, dict) and "max" in threshold:
            try:
                if float(value) > float(threshold["max"]):
                    violated = True
                    reasons.append(f"{value} > max({threshold['max']})")
            except Exception:
                return False, "non-numeric"

        if violated:
            return True, "; ".join(reasons)

        return False, "ok"

    # ----------------------------
    # Prediction (stub)
    # ----------------------------

    def predict_water_quality(self, device_id, nitrate, turbidity):
        """STUB: call your Prediction microservice here.

        Input: nitrate + turbidity
        Output: dict like:
          {'ok': True,  'action': 'none',    'reason': '...'}
          {'ok': False, 'action': 'pump_on', 'reason': '...'}
        """
        # TODO: implement REST call, e.g.:
        #   r = requests.post(PREDICT_URL, json={...}, timeout=3)
        #   return r.json()
        return None

    # ----------------------------
    # MQTT publish helpers
    # ----------------------------

    def publish_alert(self, device_id, level, message, meta=None):
        topic = ALERT_TOPIC_FMT.format(device_id=device_id)
        payload = {
            "device_id": device_id,
            "level": level,  # "warning" | "critical"
            "message": message,
            "ts": int(time.time()),
            "meta": meta or {},
        }
        self.mqtt.publish(topic, payload)

    def publish_pump_cmd(self, device_id, duration_sec=1800):
        topic = PUMP_CMD_TOPIC_FMT.format(device_id=device_id)
        payload = {
            "device_id": device_id,
            "cmd": "on",
            "duration_sec": duration_sec,
            "ts": int(time.time()),
        }
        self.mqtt.publish(topic, payload)

    def can_pump_now(self, device_id):
        now = time.time()
        last = self.last_pump_on.get(device_id, 0)
        return (now - last) >= PUMP_COOLDOWN_SEC

    def mark_pump_on(self, device_id):
        self.last_pump_on[device_id] = time.time()

    # ----------------------------
    # MQTT callback
    # ----------------------------

    def handle_agg(self, topic, payload_str):
        try:
            payload = json.loads(payload_str)
        except Exception:
            print("[MON] bad json:", payload_str)
            return

        device_id = payload.get("device_id")
        if not device_id:
            print("[MON] missing device_id in payload:", payload)
            return

        # Collect sensor keys (everything except device_id)
        sensor_keys = [k for k in payload.keys() if k != "device_id"]

        # 1) thresholds (cached)
        try:
            thresholds = self.get_thresholds_cached(device_id)
        except Exception as e:
            print(f"[MON] cannot fetch thresholds for {device_id}: {e}")
            thresholds = {}

        # 2) if a NEW sensor key appears (not in thresholds cache), refresh once
        missing = False
        for s in sensor_keys:
            if s not in thresholds:
                missing = True
                break
        if missing:
            try:
                thresholds = self.refresh_thresholds(device_id)
            except Exception as e:
                print(f"[MON] refresh thresholds failed for {device_id}: {e}")

        # 3) threshold-check (generic)
        for s in sensor_keys:
            if s not in thresholds:
                continue  # no threshold configured -> ignore
            val = payload.get(s)
            thr = thresholds.get(s)
            violated, reason = self.threshold_violated(val, thr)
            if violated:
                self.publish_alert(
                    device_id=device_id,
                    level="warning",
                    message=f"Threshold violation: {s} ({reason})",
                    meta={"sensor": s, "value": val, "threshold": thr},
                )

        # 4) prediction ONLY for nitrate + turbidity
        if "nitrate" in payload and "turbidity" in payload:
            try:
                nitrate = float(payload["nitrate"])
                turbidity = float(payload["turbidity"])
            except Exception:
                return

            pred = self.predict_water_quality(device_id, nitrate, turbidity)
            if pred is None:
                # prediction not implemented yet
                return

            ok = pred.get("ok", True)
            action = pred.get("action", "none")
            reason = pred.get("reason", "")

            if not ok:
                self.publish_alert(
                    device_id=device_id,
                    level="critical",
                    message=f"Prediction: water quality NOT OK ({reason})",
                    meta={"prediction": pred},
                )

                if action == "pump_on":
                    if self.can_pump_now(device_id):
                        self.publish_pump_cmd(device_id, duration_sec=1800)
                        self.mark_pump_on(device_id)
                    else:
                        self.publish_alert(
                            device_id=device_id,
                            level="warning",
                            message="Pump command suppressed (cooldown active).",
                            meta={"cooldown_sec": PUMP_COOLDOWN_SEC},
                        )

    # ----------------------------
    # Run
    # ----------------------------

    def start(self):
        self.mqtt.connect_and_start()
        self.mqtt.subscribe(SUB_TOPIC, self.handle_agg)

        print("[MON] Monitoring Service started.")
        print("[MON] Subscribed to:", SUB_TOPIC)
        print("[MON] Catalogue:", CATALOGUE_BASE_URL)
        print("[MON] Prediction: STUB (not implemented)")

        # Keep main thread alive
        while True:
            time.sleep(1)


def main():
    MonitoringService().start()


if __name__ == "__main__":
    main()
