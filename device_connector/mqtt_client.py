import json
import paho.mqtt.client as mqtt

class MQTTClient:

    def __init__(self, broker="localhost", port=1883, client_id=None):
        self.broker = broker
        self.port = port
        self.client = mqtt.Client(client_id=client_id)

        self._subscriptions = {}

        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

    def connect(self):
        self.client.connect(self.broker, self.port)
        self.client.loop_start()

    def _on_connect(self, client, userdata, flags, rc):
        # re-subscribe after reconnect
        for topic, sub in self._subscriptions.items():
            self.client.subscribe(topic, qos=sub["qos"])

    def _on_message(self, client, userdata, msg):
        topic = msg.topic
        payload = msg.payload.decode(errors="replace")

        sub = self._subscriptions.get(topic)
        if sub is None:
            return

        callback = sub["callback"]
        callback(topic, payload)

    def publish(self, topic, payload, qos=0):
        if isinstance(payload, dict):
            payload = json.dumps(payload)
        self.client.publish(topic, payload, qos=qos)

    def subscribe(self, topic, callback, qos=0):
        self._subscriptions[topic] = {"callback": callback, "qos": qos}
        self.client.subscribe(topic, qos=qos)
