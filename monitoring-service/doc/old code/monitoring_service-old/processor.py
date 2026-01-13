import json
from datetime import datetime

class Processor:
    def __init__(self, knn_model, db, mqtt_client):
        self.model = knn_model
        self.db = db
        self.mqtt = mqtt_client

    def process(self, topic, payload_str):
        data = json.loads(payload_str)

        parts = topic.split("/")
        device_id = parts[1]

        temp = data["temperature"]
        nitrate = data["nitrate"]
        turbidity = data["turbidity"]
        leakage = data["leakage"]

        safety_status = "ok"
        send_alert = False
        alert_msg = ""

        if temp < 5 or temp > 35:
            safety_status = "temperature_alert"
            send_alert = True
            alert_msg = f"Temperature abnormal: {temp}"

        if leakage >= 1:
            safety_status = "leakage_alert"
            send_alert = True
            alert_msg = "Leakage detected!"

        prediction = "unknown"
        if safety_status == "ok":
            prediction = self.model.predict([[turbidity, nitrate]])[0]
            if prediction == "service_needed":
                send_alert = True
                alert_msg = "Filter service needed!"

        if send_alert:
            alert_topic = f"aquarium/{device_id}/alerts"
            self.mqtt.publish(alert_topic, {
                "device_id": device_id,
                "alert": alert_msg
            })

        record = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "device_id": device_id,
            "temperature": temp,
            "nitrate": nitrate,
            "turbidity": turbidity,
            "leakage": leakage,
            "prediction": prediction,
            "safety_status": safety_status
        }
        self.db.insert(record)
        print("[MONITOR] Stored:", record)
