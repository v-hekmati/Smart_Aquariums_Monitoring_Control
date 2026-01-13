import json
import time

import cherrypy
import requests

from mqtt_client import MQTTClient
from service_registry import ServiceRegistry



# Persistent Store
class Store:
    def __init__(self, path):
        self.path = path
        with open(self.path, "r", encoding="utf-8") as f:
            self.data = json.load(f)

    def save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2)


# -----------------------------
# ThingSpeak REST Client 
# -----------------------------
class ThingSpeak:
    def __init__(self, user_api_key):
        self.user_api_key = user_api_key

    def create_channel(self, name, field_names):
        params = {
            "api_key": self.user_api_key,
            "name": name,
            "public_flag": "true"
        }

        index = 1
        for field in field_names:
            if index > 8:
                break
            params["field" + str(index)] = field
            index += 1

        r = requests.post("https://api.thingspeak.com/channels.json", data=params, timeout=8)
        r.raise_for_status()

        payload = r.json()
        channel_id = int(payload["id"])

        write_key = None
        for k in payload.get("api_keys", []):
            if k.get("write_flag"):
                write_key = k.get("api_key")
                break

        return channel_id, write_key

    def update_fields_ui(self, channel_id, fields):
        params = {"api_key": self.user_api_key}

        for name in fields:
            idx = fields[name]
            if 1 <= int(idx) <= 8:
                params["field" + str(idx)] = str(name)

        r = requests.put(
            "https://api.thingspeak.com/channels/" + str(channel_id) + ".json",
            data=params,
            timeout=8
        )
        r.raise_for_status()

    def write_update(self, write_key, field_values):
        params = {"api_key": write_key}

        for idx in field_values:
            params["field" + str(idx)] = field_values[idx]

        r = requests.post("https://api.thingspeak.com/update.json", data=params, timeout=8)
        r.raise_for_status()


# -----------------------------
# CherryPy API
# -----------------------------
class API:
    exposed = True

    def __init__(self, store, ts, catalog_base_url):
        self.store = store
        self.ts = ts
        self.catalog_base_url = catalog_base_url.rstrip("/")

    @cherrypy.tools.json_in()
    @cherrypy.tools.json_out()
    def POST(self, *uri):
        if uri[0] != "channels" or uri[1] != "create":
            cherrypy.response.status = 404
            return {"ok": False}

        body = cherrypy.request.json
        device_id = body["device_id"]
        device_label = body["device_label"]

        sensors = self.get_device_sensors(device_id)
        info = self.ensure_channel(device_id, device_label, sensors)
        self.store.save()

        return {
            "ok": True,
            "device_id": info["device_id"],
            "device_label": info["device_label"],
            "channel_id": info["channel_id"]
        }

   # ask from Service/resourse Catalogue list of snsores of  specific device
    def get_device_sensors(self, device_id):
        r = requests.get(self.catalog_base_url + "/devices/" + device_id, timeout=4)
        r.raise_for_status()
        d = r.json()

        resources = d.get("resources") or (d.get("device") or {}).get("resources") or []

        names = []
        if isinstance(resources, dict):
            for key in resources:
                names.append(key)
            return names

        for it in resources:
            if it.get("kind") == "sensor":
                names.append(it["name"])

        return names
    # check channel exist or not if exist then use it otherwise create it 
    def ensure_channel(self, device_id, device_label, sensors):
        label_map = self.store.data["label_to_channel"]
        device_map = self.store.data["device_to_label"]

        if device_label in label_map:
            device_map[device_id] = device_label
            self.ensure_fields(device_label, sensors)

            info = label_map[device_label]
            try:
                self.ts.update_fields_ui(info["channel_id"], info.get("fields", {}))
            except Exception as e:
                print(e)

            return {
                "device_id": device_id,
                "device_label": device_label,
                "channel_id": info["channel_id"]
            }

        if sensors:
            field_names = sensors[:8]
        else:
            field_names = ["temperature", "nitrate", "turbidity", "leakage"]

        channel_id, write_key = self.ts.create_channel(device_label, field_names)

        fields = {}
        index = 1
        for name in field_names:
            if index > 8:
                break
            fields[name] = index
            index += 1

        label_map[device_label] = {
            "channel_id": channel_id,
            "write_key": write_key,
            "fields": fields
        }
        device_map[device_id] = device_label

        return {
            "device_id": device_id,
            "device_label": device_label,
            "channel_id": channel_id
        }

    def ensure_fields(self, device_label, sensors):
        info = self.store.data["label_to_channel"][device_label]
        fields = info.get("fields", {})

        used = set()
        for v in fields.values():
            used.add(v)

        next_idx = 1
        for s in sensors:
            if s in fields:
                continue

            while next_idx in used and next_idx <= 8:
                next_idx += 1

            if next_idx > 8:
                break

            fields[s] = next_idx
            used.add(next_idx)

        info["fields"] = fields


# -----------------------------
# MQTT App
# -----------------------------
class App:
    def __init__(self, cfg, store, ts):
        self.cfg = cfg
        self.store = store
        self.ts = ts
        self.catalog_base_url = "http://" + cfg["catalog_host"] + ":" + str(cfg["catalog_port"])

        self.mqtt = MQTTClient(
            broker=cfg["mqtt_host"],
            port=cfg["mqtt_port"],
            client_id="thingspeak_adaptor"
        )
        self.mqtt.connect()
        self.mqtt.subscribe("aquarium/+/sensors/agg", self.on_agg)

    def on_agg(self, topic, payload_str):
        device_id = topic.split("/")[1]
        device_label = self.store.data["device_to_label"].get(device_id)
        if not device_label:
            return

        info = self.store.data["label_to_channel"][device_label]

        now = time.time()
        last = self.store.data.get("last_sent", {}).get(device_label, 0)
        if now - last < self.cfg.get("min_send_interval_sec", 16):
            return

        try:
            data = json.loads(payload_str)
        except Exception:
            return

        values = data.get("values", data)
        if not isinstance(values, dict):
            return

        if "device_id" in values:
            del values["device_id"]

        api = API(self.store, self.ts, self.catalog_base_url)
        api.ensure_fields(device_label, list(values.keys()))
        self.store.save()

        field_map = info.get("fields", {})
        field_values = {}

        for name in values:
            if name in field_map:
                try:
                    field_values[field_map[name]] = float(values[name])
                except Exception:
                    pass

        if not field_values:
            return

        try:
            self.ts.write_update(info["write_key"], field_values)
            self.store.data.setdefault("last_sent", {})[device_label] = now
            self.store.save()
        except Exception as e:
            print(e)


def load_config():
    with open("config.json", "r") as f:
        return json.load(f)


def main():
    cfg = load_config()

    store = Store(cfg.get("mapping_file", "thingspeak_map.json"))
    ts = ThingSpeak(cfg["thingspeak_user_api_key"])

    # enables MQTT logic
    App(cfg, store, ts)

    registry = ServiceRegistry(cfg["catalog_host"], cfg["catalog_port"])
    registry.register(cfg["service_name"], cfg["host"], cfg["port"])

    api = API(store, ts, "http://" + cfg["catalog_host"] + ":" + str(cfg["catalog_port"]))
    cherrypy.config.update({
        "server.socket_host": cfg["host"],
        "server.socket_port": cfg["port"]
    })
    cherrypy.quickstart(api, "/", {
        "/": {"request.dispatch": cherrypy.dispatch.MethodDispatcher()}
    })


if __name__ == "__main__":
    main()
