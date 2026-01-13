import json
import time
import cherrypy

from mqtt_client import MQTTClient
from db import MariaDB
from service_registry import ServiceRegistry


def load_config(path="config.json"):
    with open(path, "r") as f:
        return json.load(f)

# create timestamp
def now_ts():
    return int(time.time())

# It subscribes to a topic, gets the mqtt data , and saves it in the db system
class StorageMQTTWorker:
    def __init__(self, db, mqtt, topic):
        self.db = db
        self.mqtt = mqtt
        self.topic = topic

    def start(self):
        self.mqtt.connect()
        self.mqtt.subscribe(self.topic, self.on_message, qos=0)  # aquarium/+/sensors/agg
        print(f"[MQTT] SUB -> {self.topic}")

    def on_message(self, topic, payload_str):
        
        
            payload = json.loads(payload_str)

            device_id = payload["device_id"] # extract device id 
            ts = payload.get("ts", now_ts()) # create timestamp 

            data = dict(payload)
            data.pop("device_id") # remove device_id from payload
            data.pop("ts", None)  # remove timesatamp from payload

            self.db.insert_measurements(str(device_id), int(ts), data) # insert sensed data in db 

 #-------------------------------------------------------------------------------------------------       


# API class to serve service to other (telegram)
class StorageAPI:
    exposed = True

    def __init__(self, db):
        self.db = db

    @cherrypy.tools.json_out()
    def GET(self, *uri, **params):
        # GET /devices/<device_id>/latest
        if len(uri) != 3 or uri[0] != "devices" or uri[2] != "latest":
            cherrypy.response.status = 404
            return {"status": "error", "message": "Not found"}

        device_id = uri[1]
        result = self.db.get_latest(str(device_id)) # get the latest data for specified device_id from database 
        if result is None: # if result is none throw an error 
            cherrypy.response.status = 404
            return {
                "status": "error",
                "message": "No data for this device_id",
                "device_id": device_id,
            }

        return {"status": "ok", "device_id": device_id, "data": result} # send the latest data as json 

 #-------------------------------------------------------------------------------------------------      

def main():
    # read config from config.json
    cfg = load_config("config.json")

    service_cfg = cfg.get("service", {})
    host_cfg = cfg.get("host", {})
    db_cfg = cfg.get("db", {})
    mqtt_cfg = cfg.get("mqtt", {})
    cat_cfg = cfg.get("catalogue", {})

    service_name = service_cfg.get("name", "storage_service")

    bind_host = host_cfg.get("bind_host", "0.0.0.0")
    http_port = int(host_cfg.get("port", 8090))
    advertise_host = host_cfg.get("advertise_host", "localhost")

    mqtt_broker = mqtt_cfg.get("broker", "localhost")
    mqtt_port = int(mqtt_cfg.get("port", 1883))
    mqtt_topic = mqtt_cfg.get("topic", "aquarium/+/sensors/agg")

    catalog_host = cat_cfg.get("host", "localhost")
    catalog_port = int(cat_cfg.get("port", 8080))

    # instantiate db class 
    db = MariaDB(
        host=db_cfg.get("host", "127.0.0.1"),
        port=int(db_cfg.get("port", 3306)),
        user=db_cfg.get("user", "root"),
        password=db_cfg.get("password", ""),
        database=db_cfg.get("name", "smart_aquariums"),
    )

    # the Storage service registers itself in the service catalog
    registry = ServiceRegistry(catalog_host, catalog_port)
    registry.register(service_name, advertise_host, http_port)
    print(f"[REG] {service_name} -> http://{advertise_host}:{http_port}")


    # instantiate MQTT client class 
    mqtt = MQTTClient(broker=mqtt_broker, port=mqtt_port, client_id=service_name)
    StorageMQTTWorker(db, mqtt, mqtt_topic).start()

    cherrypy.config.update({
        "server.socket_host": bind_host,
        "server.socket_port": http_port,
    })

    conf = {"/": {"request.dispatch": cherrypy.dispatch.MethodDispatcher()}}
    cherrypy.tree.mount(StorageAPI(db), "/", conf)

    cherrypy.engine.start()
    cherrypy.engine.block()


if __name__ == "__main__":
    main()
