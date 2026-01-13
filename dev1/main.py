import json
from mqtt_client import MQTTClient
from controller import DeviceController
from register_service import register_device_connector


def load_config(path = "config.json"):
    with open(path, "r") as f:
        return json.load(f)


def main():
    config_path = "config.json"
    config = load_config(config_path)

    # rgistartion  in Service and Resource Catalogue  
    config = register_device_connector(config, config_path=config_path)

    # Setup MQTT client using  mqtt data from config file 
    mqtt_conf = config["mqtt"]
    mqtt_client = MQTTClient(
        broker=mqtt_conf.get("broker", "localhost"),
        port=mqtt_conf.get("port", 1883),
        client_id=f"device_connector_{config['device_label']}",
    )

    # Create controller ( preprocessing + sensor data publishing  ,... )
    controller = DeviceController(config, mqtt_client)

    # Connect to MQTT and start main loop
    mqtt_client.connect()
    controller.start()


if __name__ == "__main__":
    main()
