import json
import paho.mqtt.client as mqtt


def topic_match(pattern: str, topic: str) -> bool:
    """
    Very simple MQTT wildcard matcher.
    Supports:
      +  one level
      #  all remaining levels (only at the end)
    """
    p = pattern.split("/")
    t = topic.split("/")

    i = 0
    while i < len(p):
        if p[i] == "#":
            return i == len(p) - 1
        if i >= len(t):
            return False
        if p[i] != "+" and p[i] != t[i]:
            return False
        i += 1

    return i == len(t)


class MQTTClient:
    """
    Super-minimal MQTT client:
    - QoS default = 0 (override optional)
    - Supports wildcard subscriptions (+ and #)
    - NO threading.Lock (exam-friendly)
    """

    def __init__(self, broker, port=1883, client_id=None):
        self.broker = broker
        self.port = port
        self.client = mqtt.Client(client_id)

        # list of subscriptions:
        # { "pattern": str, "callback": fn, "qos": int }
        self.subscriptions = []

        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

    def connect(self):
        self.client.connect(self.broker, self.port)
        self.client.loop_start()

    # ---------- MQTT callbacks ----------

    def _on_connect(self, client, userdata, flags, rc):
        # Re-subscribe after reconnect
        for s in self.subscriptions:
            self.client.subscribe(s["pattern"], qos=s["qos"])

    def _on_message(self, client, userdata, msg):
        topic = msg.topic
        payload = msg.payload.decode()

        for s in self.subscriptions:
            if topic_match(s["pattern"], topic):
                s["callback"](topic, payload)

    # ---------- Public API ----------

    def publish(self, topic, payload, qos=0):
        if isinstance(payload, dict):
            payload = json.dumps(payload)
        self.client.publish(topic, payload, qos=qos)

    def subscribe(self, topic_pattern, callback, qos=0):
        self.subscriptions.append({
            "pattern": topic_pattern,
            "callback": callback,
            "qos": qos
        })
        self.client.subscribe(topic_pattern, qos=qos)
