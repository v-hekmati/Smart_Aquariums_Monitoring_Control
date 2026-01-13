import json
import paho.mqtt.client as mqtt

class MqttClient:
    def __init__(self, broker="localhost", port=1883, client_id=None):
        self.broker = broker
        self.port = port
        self.client = mqtt.Client(client_id=client_id)
        self._subscriptions = {}

        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

    def connect_and_start(self):
        self.client.connect(self.broker, self.port, 60)
        self.client.loop_start()

    def _on_connect(self, client, userdata, flags, rc):
        print("[MQTT] Connected with result code", rc)
        for topic in list(self._subscriptions.keys()):
            self.client.subscribe(topic)

    def _on_message(self, client, userdata, msg):
        topic = msg.topic
        payload_str = msg.payload.decode("utf-8")
        cb = self._subscriptions.get(topic)
        if cb:
            cb(topic, payload_str)

    def publish(self, topic, payload):
        if isinstance(payload, dict):
            payload = json.dumps(payload)
        self.client.publish(topic, payload)

    def subscribe(self, topic, callback):
        self._subscriptions[topic] = callback
        self.client.subscribe(topic)

    def stop(self):
        self.client.loop_stop()
        self.client.disconnect()
