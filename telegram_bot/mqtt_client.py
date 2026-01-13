import json
import paho.mqtt.client as mqtt

class MQTTClient:

    def __init__(self, broker="localhost", port=1883, client_id=None):
        self.broker = broker
        self.port = port

        self.client = mqtt.Client(client_id=client_id)
        self.client.on_message = self._on_message

        self._topic = None
        self._callback = None

    def connect(self):
        self.client.connect(self.broker, self.port)
        self.client.loop_start()

    def publish(self, topic, payload, qos=0):
        if isinstance(payload, dict):
            payload = json.dumps(payload)
        self.client.publish(topic, payload, qos=qos)

    def subscribe(self, topic, callback, qos=0):
        self._topic = topic
        self._callback = callback
        self.client.subscribe(topic, qos=qos)

    def _on_message(self, client, userdata, msg):
        if self._callback:
            self._callback(msg.topic, msg.payload.decode())
