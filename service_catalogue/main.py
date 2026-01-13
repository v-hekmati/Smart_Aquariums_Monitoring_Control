import cherrypy
import json
import os
import random 
import time


def now_ts():
    return int(time.time())


class CatalogStorage:


    def __init__(self):
        # MQTT broker info 
        self.broker = {"broker": "localhost", "port": 1883, "base_topic": "aquarium"}

        self.services = {}  # services: service_name -> {service_id, name, url, last_seen}
        self.devices_by_id = {} # map :  device_id -> device object  - Database of all devices 
        self.device_id_by_label = {} # map : device_label -> device_id - If a device with the same label is registered again, the previously assigned device_id is returned

        # Load state (catalogue data) from json file
        self.load_state()

    # -------- Persistence --------
   
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    STATE_FILE = os.path.join(BASE_DIR, "catalog_state.json")

    def save_state(self):
        data = {
            "broker": self.broker,
            "services": self.services,
            "devices_by_id": self.devices_by_id,
            "device_id_by_label": self.device_id_by_label,
        }
        with open(self.STATE_FILE, "w") as f:
            json.dump(data, f, indent=2)

    def load_state(self):
        if not os.path.exists(self.STATE_FILE):
            return
        try:
            with open(self.STATE_FILE, "r") as f:
                data = json.load(f)
        except Exception:
            return

        self.broker = data.get("broker", self.broker)
        self.services = data.get("services", {})
        self.devices_by_id = data.get("devices_by_id", {})
        self.device_id_by_label = data.get("device_id_by_label", {})

    # -------- Services --------

    def upsert_service(self, payload):
       
        name = payload["name"]
        host = payload["host"]
        port = int(payload["port"])

       
        url = f"http://{host}:{port}"

       
        service_id = str(random.randint(100000, 999999))

        self.services[name] = {
            "service_id": service_id,
            "name": name,
            "url": url,
            "last_seen": now_ts(),
        }
        self.save_state()
        return self.services[name]

    # -------- Devices / Resources --------

    def register_or_get_device(self, payload):
        label = payload["device_label"]

        # If this label already exists, return the same device 
        if label in self.device_id_by_label:
            device_id = self.device_id_by_label[label]
            device = self.devices_by_id[device_id]
            device["last_seen"] = now_ts()

            # update resources on re-register
            if "resources" in payload:
                self.upsert_resources(device_id, payload["resources"])

            self.save_state()
            return device

        # Create new device
        device_id = str(random.randint(10000000, 99999999))
        device = {
            "device_id": device_id,
            "device_label": label,
            "created_at": now_ts(),
            "last_seen": now_ts(),
            "resources": []
        }

    
        self.devices_by_id[device_id] = device
        self.device_id_by_label[label] = device_id

        #initial resources
        self.upsert_resources(device_id, payload.get("resources", []))

        self.save_state()
        return self.devices_by_id[device_id]

    def upsert_resources(self, device_id, resources) :
        # Ensure device exists
        if device_id not in self.devices_by_id:
            # If device was just created in register_or_get_device, it might not be inserted yet
            # So create a temporary device record if needed
            self.devices_by_id[device_id] = {
                "device_id": device_id,
                "device_label": None,
                "created_at": now_ts(),
                "last_seen": now_ts(),
                "resources": []
            }

        device = self.devices_by_id[device_id]

        # Merge by resource name
        resources_by_name  = {r["name"]: r for r in device.get("resources", [])}

        base = self.broker["base_topic"]
        for r in resources:
            name = r["name"]
            kind = r["kind"]  # "sensor" or "actuator"

            item = {
                "name": name,
                "kind": kind,
                "threshold": r.get("threshold"),
            }

            # MQTT topics
            if kind == "sensor":
                item["data_topic"] = f"{base}/{device_id}/sensors/agg"
            else:  # actuator
                item["cmd_topic"] = f"{base}/{device_id}/cmd/{name}"

            resources_by_name [name] = item

        device["resources"] = list(resources_by_name.values())
        device["last_seen"] = now_ts()
        self.save_state()
        return device


class ServicesAPI:
    exposed = True

    def __init__(self, storage):
        self.storage = storage

    @cherrypy.tools.json_in()
    @cherrypy.tools.json_out()
    def POST(self, *uri):
        # POST /services/register
        if uri == ("register",):
            s = self.storage.upsert_service(cherrypy.request.json)
            return {"status": "ok", "service": s}
        raise cherrypy.HTTPError(404)

    @cherrypy.tools.json_out()
    def GET(self, *uri):
        # GET /services
        if len(uri) == 0:
            return {"services": list(self.storage.services.values())}

        # GET /services/{name}
        if len(uri) == 1:
            name = uri[0]
            if name not in self.storage.services:
                raise cherrypy.HTTPError(404, "service_not_found")
            return {"service": self.storage.services[name]}

        raise cherrypy.HTTPError(404)


class DevicesAPI:
    exposed = True

    def __init__(self, storage):
        self.storage = storage

    @cherrypy.tools.json_in()
    @cherrypy.tools.json_out()
    def POST(self, *uri):
        # POST /devices/register
        # Only for Device Connector
        if uri == ("register",):
            d = self.storage.register_or_get_device(cherrypy.request.json)
            return {
                "status": "ok",
                "device_id": d["device_id"],
                "broker": self.storage.broker,
                "resources": d.get("resources", []),
            }
        raise cherrypy.HTTPError(404)

    @cherrypy.tools.json_in()
    @cherrypy.tools.json_out()
    def PUT(self, *uri):
        # PUT /devices/{id}/resources
        #used by device connector  to update resorses
        if len(uri) == 2 and uri[1] == "resources":

            device_id = uri[0]

            body = cherrypy.request.json or {}

            # Device Connector must send device_label here

            label = body.get("device_label")

            updated = self.storage.upsert_resources(device_id, body.get("resources", []))

            if label:

                # store label for UI (admin dashboard dropdown)

                self.storage.devices_by_id[device_id]["device_label"] = label

            # persist changes
            self.storage.save_state()

            return {"status": "ok", "device": updated, "broker": self.storage.broker}
        raise cherrypy.HTTPError(404)

    @cherrypy.tools.json_out()
    def GET(self, *uri):
        # GET /devices
        # used by admin dashboard
        if len(uri) == 0:
            devices = []

            for device in self.storage.devices_by_id.values():
                devices.append({
                    "device_id": device["device_id"],
                    "device_label": device["device_label"],
                })

            return {
                "devices": devices,
                "broker": self.storage.broker,
            }

        # GET /devices/{id}
        if len(uri) == 1:
            device_id = uri[0]
            if device_id not in self.storage.devices_by_id:
                raise cherrypy.HTTPError(404, "device_not_found")
            return {
                "device": self.storage.devices_by_id[device_id],
                "broker": self.storage.broker,
            }

        raise cherrypy.HTTPError(404)



class Root:
    def __init__(self):
        storage = CatalogStorage()
        self.services = ServicesAPI(storage)
        self.devices = DevicesAPI(storage)


def run_server():
    cherrypy.config.update({"server.socket_host": "0.0.0.0", "server.socket_port": 8080})

    conf = {
        "/services": {"request.dispatch": cherrypy.dispatch.MethodDispatcher()},
        "/devices": {"request.dispatch": cherrypy.dispatch.MethodDispatcher()},
    }

    cherrypy.quickstart(Root(), "/", conf)


if __name__ == "__main__":
    run_server()
