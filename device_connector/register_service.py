import json
import requests

# create a flat list of sensors and actuators dictionaries [{},{},{},...]
def _build_resources(config):
    resources = []

    # Sensors 
    for name, meta in config.get("sensors").items():
        resources.append({
            "name": name,
            "kind": "sensor",
            "unit": meta.get("unit"),
            "threshold": meta.get("threshold"),
        })

    # Actuators
    actuators = config.get("actuators")
    if actuators:
        for name, meta in actuators.items():
            resources.append({
                "name": name,
                "kind": "actuator",
                "meta": meta or {}
            })
    else:
       
        for act_name in ["feeder", "water_pump"]:
            resources.append({
                "name": act_name,
                "kind": "actuator"
            })

    return resources

# save config to disk to be persistent 
def _save_config(config_path, config):
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)


# config is dict and return a dict - Register device connector to Service Catalogue
def register_device_connector(config, config_path="config.json"):
    # Register this device Connector in the Service + Resource Catalogue.

    # flow 
    # 1) POST /services/register 
    # 2) ensure  a device_id exists via POST /devices/register (if needed)
    # 3) always   sync resources via PUT /devices/<device_id>/resources
    # 4) always notify ThingSpeak adaptor (keeps mapping correct even if device_id changes):
    
    cat_host = config["catalogue"]["host"]
    cat_port = config["catalogue"]["port"]
    base_url = f"http://{cat_host}:{cat_port}"

    device_label = config["device_label"]
    service_name = f"device_connector_{device_label}"

    # Build resources list (so both register + update use the same list)
    resources = _build_resources(config)

    # ---------- 1) Service Catalogue  ----------
    svc_payload = {
        "name": service_name,
        "type": "device_connector",
        "host": "localhost",
        "port": 0,
        "meta": {
            "device_label": device_label,
            "location": config.get("location"),
            "aquarium_name": config.get("aquarium_name"),
        }
    }

    try:
        r = requests.post(f"{base_url}/services/register", json=svc_payload, timeout=5)
        print("[CATALOGUE] Service register:", r.status_code, r.text)
    except Exception as e:
        print("[CATALOGUE] Service register failed:", e)

    # ---------- helpers ----------
    def do_register():
        payload = {
            "device_label": device_label,
            "location": config.get("location", "unknown"),
            "aquarium_name": config.get("aquarium_name", device_label),
            "resources": resources
        }
        rr = requests.post(f"{base_url}/devices/register", json=payload, timeout=5)
        print("[CATALOGUE] Device register:", rr.status_code, rr.text)
        if rr.status_code != 200:
            return None
        return rr.json()

    def do_update(device_id):
        # update  resources in the Resource Catalogue if there are changes in resources.
        payload = {
            "device_id": device_id,
            "device_label": device_label,
            "resources": resources
        }
        rr = requests.put(f"{base_url}/devices/{device_id}/resources", json=payload, timeout=5)
        print("[CATALOGUE] Device resources update:", rr.status_code, rr.text)
        if rr.status_code == 200:
            return rr.json()
        if rr.status_code == 404:
            return {"_not_found": True}
        return None

    # ---------- 2) Device + resources ----------
    device_id = config.get("device_id")

    try:
        # A) ensure device exists and we have device_id and it saves the data (device_id - Broker data in config file )
        if not device_id:
            resp = do_register()
            if resp is None:
                print("[ERROR] Service Catalogue is not available. Device not registered")
                return config

            device_id = resp.get("device_id")
            config["device_id"] = device_id

            # store broker info if provided
            if "broker" in resp:
                config["broker"] = resp.get("broker")
            if "port" in resp:
                config["port"] = resp.get("port")
            if "base_topic" in resp:
                config["base_topic"] = resp.get("base_topic")

            _save_config(config_path, config)

        # B) ALWAYS sync resources via PUT 
        upd = do_update(device_id)

        # ----  notify ThingSpeak adaptor  to create channel  ----
        s = requests.get(f"{base_url}/services/thingspeak_adaptor", timeout=5) #/ get the url of thingspeak from catalogue 
        print("[THINGSPEAK] resolve:", s.status_code, s.text)
        if s.status_code == 200:
            data = s.json() or {}
            ts_url = data.get("service").get("url") 

            if ts_url:
                
                ts_url = ts_url.rstrip("/")
                r2 = requests.post(
                    ts_url + "/channels/create",
                    json={"device_id": device_id, "device_label": device_label},
                    timeout=8
                )
                print("[THINGSPEAK] channel create:", r2.status_code, r2.text)

        # If catalogue restarted and forgot the device_id, re-register then update again
        if upd and upd.get("_not_found"):
            resp = do_register()
            if resp is None:
                return config

            device_id = resp.get("device_id")
            config["device_id"] = device_id

            if "broker" in resp:
                config["broker"] = resp.get("broker")
            if "port" in resp:
                config["port"] = resp.get("port")
            if "base_topic" in resp:
                config["base_topic"] = resp.get("base_topic")

            _save_config(config_path, config)
            do_update(device_id)

            # notify again with the NEW device_id
            s = requests.get(f"{base_url}/services/thingspeak_adaptor", timeout=5)
            print("[THINGSPEAK] resolve:", s.status_code, s.text)
            if s.status_code == 200:
                data = s.json() or {}
                ts_url = data.get("service").get("url") # ts_url = ThingSpeak URL 
                if ts_url:
                    ts_url = ts_url.rstrip("/")
                    r2 = requests.post(
                        ts_url + "/channels/create",
                        json={"device_id": device_id, "device_label": device_label},
                        timeout=8
                    )
                    print("[THINGSPEAK] channel create:", r2.status_code, r2.text)

        return config

    except Exception as e:
        print("[CATALOGUE] Device register/update failed:", e)
        return config
