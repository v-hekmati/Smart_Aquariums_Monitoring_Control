import json
import paho.mqtt.client as mqtt


def topic_match(pattern, topic):
    """Very simple MQTT wildcard matcher for + and #."""
    pattern_parts = pattern.split("/")
    topic_parts = topic.split("/")

    for i in range(len(pattern_parts)):
        p = pattern_parts[i]

        # '#' means: match everything from here to the end
        if p == "#":
            return True

        # topic ended but pattern still has parts
        if i >= len(topic_parts):
            return False

        # '+' means: match exactly one level
        if p != "+" and p != topic_parts[i]:
            return False

    # if pattern ended, topic must also end (same length)
    return len(pattern_parts) == len(topic_parts)


class MQTTClient:
    """
    One simple MQTT client for the whole project.

    Methods:
      - connect()
      - publish(topic, payload, qos=0)
      - subscribe(topic_pattern, callback, qos=0)   # supports + and #

    Callback signature:
      callback(topic: str, payload_str: str)
    """

    def __init__(self, broker="localhost", port=1883, client_id=None):
        self.broker = broker
        self.port = port
        self.client = mqtt.Client(client_id=client_id)

        # list of subscriptions: {"pattern": str, "callback": fn, "qos": int}
        self.subscriptions = []

        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

    def connect(self):
        self.client.connect(self.broker, self.port)
        self.client.loop_start()

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

    def publish(self, topic, payload, qos=0):
        if isinstance(payload, dict):
            payload = json.dumps(payload)
        self.client.publish(topic, payload, qos=qos)

    def subscribe(self, topic_pattern, callback, qos=0):
        self.subscriptions.append({"pattern": topic_pattern, "callback": callback, "qos": qos})
        self.client.subscribe(topic_pattern, qos=qos)
