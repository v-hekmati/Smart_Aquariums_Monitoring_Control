import cherrypy
from mqtt_client import MqttClient
from database import Database
from processor import Processor
from model import KNNModel
from http_api import HttpAPI

def main():
    db = Database()
    model = KNNModel()

    mqtt = MqttClient(broker="localhost", port=1883, client_id="monitoring")
    processor = Processor(model, db, mqtt)

    mqtt.subscribe("aquarium/+/sensors/agg", processor.process)
    mqtt.connect_and_start()

    conf = {"/":{"request.dispatch":cherrypy.dispatch.MethodDispatcher()}}
    cherrypy.tree.mount(HttpAPI(db), "/monitoring", conf)
    cherrypy.config.update({"server.socket_port":8082})

    cherrypy.engine.start()
    cherrypy.engine.block()

if __name__ == "__main__":
    main()
