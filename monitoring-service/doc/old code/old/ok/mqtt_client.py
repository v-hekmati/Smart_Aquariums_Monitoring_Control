import json
import threading
import paho.mqtt.client as mqtt


class MqttClient:
    """Simple wrapper around paho-mqtt with topic-based callbacks.

    Supports wildcard subscriptions (+ and #) by matching incoming topics
    against the stored subscription filters.

    Also keeps thread-safe access to the subscriptions dict to avoid:
      RuntimeError: dictionary changed size during iteration
    """

    def __init__(self, broker="localhost", port=1883, client_id=None):
        self.broker = broker
        self.port = port
        self.client = mqtt.Client(client_id=client_id)

        self._subscriptions = {}  # topic_filter -> callback(topic, payload_str)
        self._sub_lock = threading.Lock()

        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

    def connect_and_start(self):
        """Connect to the MQTT broker and start the network loop in background."""
        self.client.connect(self.broker, self.port, 60)
        self.client.loop_start()

    # ----------------------------
    # Internal: topic matching
    # ----------------------------
    @staticmethod
    def _topic_match(topic_filter: str, topic: str) -> bool:
        """Match MQTT wildcards in topic_filter against a concrete topic.

        Supports:
          - '+' : single level wildcard
          - '#' : multi level wildcard (must be last level in filter)
        """
        f_levels = topic_filter.split("/")
        t_levels = topic.split("/")

        for i, f in enumerate(f_levels):
            if f == "#":
                return True
            if i >= len(t_levels):
                return False
            if f == "+":
                continue
            if f != t_levels[i]:
                return False

        return len(t_levels) == len(f_levels)

    def _find_callback(self, topic: str):
        """Find callback for exact or wildcard-matching subscription."""
        with self._sub_lock:
            cb = self._subscriptions.get(topic)
            if cb:
                return cb

            for filt, fn in self._subscriptions.items():
                if filt == topic:
                    continue
                if self._topic_match(filt, topic):
                    return fn

        return None

    def _on_connect(self, client, userdata, flags, rc):
        print("[MQTT] Connected with result code", rc)
        with self._sub_lock:
            topics = list(self._subscriptions.keys())
        for topic in topics:
            self.client.subscribe(topic)

    def _on_message(self, client, userdata, msg):
        topic = msg.topic
        payload_str = msg.payload.decode("utf-8")

        cb = self._find_callback(topic)
        if cb:
            cb(topic, payload_str)
        else:
            print(f"[MQTT] Message on {topic} with no registered callback: {payload_str}")

    def publish(self, topic, payload):
        """Publish a message; if payload is dict, JSON-encode it."""
        if isinstance(payload, dict):
            payload = json.dumps(payload)
        self.client.publish(topic, payload)

    def subscribe(self, topic, callback):
        """Subscribe to a topic filter with a given callback(topic, payload_str)."""
        with self._sub_lock:
            self._subscriptions[topic] = callback
        self.client.subscribe(topic)

    def stop(self):
        self.client.loop_stop()
        self.client.disconnect()
