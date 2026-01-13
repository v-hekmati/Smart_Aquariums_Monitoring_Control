import time
import json

import sensors
from sensors import BaseSensor
from preprocessing import Preprocessor
from actuators import Feeder, WaterPump
from mqtt_client import MQTTClient


class DeviceController:
    def __init__(self, config, mqtt_client):
        self.config = config
        self.mqtt = mqtt_client

        self.device_id = config["device_id"]
        self.interval = config["sampling_interval_sec"]
        self.base_topic = config["mqtt"]["base_topic"]

        # 1) Build sensors from config.json 
        sensor_limits = config.get("sensors", {})
        self.sensors = {}

        for sensor_name, meta in sensor_limits.items():
            min_v = meta["min_valid"]
            max_v = meta["max_valid"]
           
            # for special sensor it is possible to instantiate separate class here from sensors class
            # otherwise  BaseSensor will be used 
            if sensor_name == "leakage":
                self.sensors[sensor_name] = sensors.LeakageSensor(sensor_name, min_v, max_v)
            else:
                self.sensors[sensor_name] = BaseSensor(sensor_name, min_v, max_v)

        # 2) Actuators
        self.feeder = Feeder()
        self.pump = WaterPump()

        self.pump_default_sec = config["actuators"]["water_pump"].get("default_duration_sec", 1800)


        # 3) Preprocessing
        self.preprocessor = Preprocessor(config["window_size"], sensor_limits)

        # 4) Topics
        self.sensor_topic = f"{self.base_topic}/{self.device_id}/sensors/agg"
        self.feeder_cmd_topic = f"{self.base_topic}/{self.device_id}/cmd/feeder"
        self.pump_cmd_topic = f"{self.base_topic}/{self.device_id}/cmd/water_pump"

    def read_raw_sensors(self):
        data = {}
        for name, sensor_obj in self.sensors.items():
            data[name] = sensor_obj.read()
        return data


    def handle_feeder(self, topic, payload):
        print(f"[CMD] FEED received on {topic}: {payload}")
        self.feeder.activate()


    def handle_pump(self, topic, payload):

        print(f"[CMD] PUMP received on {topic}: {payload}")

        data = json.loads(payload)

        action = data.get("action", "on")
        duration_sec = int(data.get("duration_sec", self.pump_default_sec))

        if action == "off":
            self.pump.off()
        else:
            self.pump.on(duration_sec)


    def start(self):
        # Subscribe to commands
        self.mqtt.subscribe(self.feeder_cmd_topic, self.handle_feeder, qos=0)
        self.mqtt.subscribe(self.pump_cmd_topic, self.handle_pump, qos=0)

        print("[DEVICE] Main loop started.")
        print("[DEVICE] Active sensors:", list(self.sensors.keys()))
        print("[DEVICE] Pump default duration:", self.pump_default_sec, "sec")

        while True:
            
            self.pump.update() # check pump timeout and turn off if needed

            raw = self.read_raw_sensors()
            aggregated = self.preprocessor.process(raw) # collect samples in sliding window and aggregate when full

            if aggregated is not None:
                payload = {"device_id": self.device_id}
                payload.update(aggregated)  # add aggregated sensor values to payload

                self.mqtt.publish(self.sensor_topic, payload)
                print("[PUBLISH] Aggregated sensors:", payload)

            time.sleep(self.interval)
