import os
import json
import cherrypy

from db_user_catalogue import MariaDB
from service_registry import ServiceRegistry


# Reads configuration 
def load_config():
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, "config.json")
    with open(path, "r") as f:
        return json.load(f)


# Builds a standard JSON error response  
def json_error(status, message):
    cherrypy.response.status = status
    return {"status": "error", "message": message}


class UserCatalogueAPI:
    # Creates the API object and stores the database handle for later use 
    def __init__(self, db):
        self.db = db

    # Returns users  and also supports creating a new user 
    @cherrypy.expose
    @cherrypy.tools.json_in()
    @cherrypy.tools.json_out()
    def users(self, user_id=None):
        method = cherrypy.request.method.upper()

        if method == "GET":
            user_id = user_id or cherrypy.request.params.get("user_id")
            if user_id:
                u = self.db.get_user_by_id(int(user_id))
                if not u:
                    return json_error(404, "User not found")
                return {"status": "ok", "user": u}
            return {"status": "ok", "users": self.db.list_users()}

        if method == "POST":
            data = cherrypy.request.json or {}
            username = (data.get("username") or "").strip()
            password = (data.get("password") or "").strip()
            if not username or not password:
                return json_error(400, "username and password are required")
            user_id = self.db.create_user(username, password)
            return {"status": "ok", "user_id": user_id}

        return json_error(405, "Method not allowed")

    # Lists all devices assigned to a given user_id 
    @cherrypy.expose
    @cherrypy.tools.json_out()
    def user_devices(self, user_id=None):
        if cherrypy.request.method.upper() != "GET":
            return json_error(405, "Method not allowed")

        user_id = user_id or cherrypy.request.params.get("user_id")
        if not user_id:
            return json_error(400, "user_id is required")

        devices = self.db.get_devices_for_user(int(user_id))
        return {"status": "ok", "user_id": int(user_id), "devices": devices}

    # Assigns a device to a user  
    @cherrypy.expose
    @cherrypy.tools.json_in()
    @cherrypy.tools.json_out()
    def assign(self):
        if cherrypy.request.method.upper() != "POST":
            return json_error(405, "Method not allowed")

        data = cherrypy.request.json or {}
        user_id = data.get("user_id")
        device_id = data.get("device_id")
        device_label = data.get("device_label")

        if user_id is None or not device_id:
            return json_error(400, "user_id and device_id are required")

        self.db.upsert_device(device_id=str(device_id), device_label=device_label)
        self.db.assign_device_to_user(int(user_id), str(device_id))

        return {
            "status": "ok",
            "message": "assigned",
            "user_id": int(user_id),
            "device_id": str(device_id),
        }

    # Unassigns a device from a user
    @cherrypy.expose
    @cherrypy.tools.json_in()
    @cherrypy.tools.json_out()
    def unassign(self):
        if cherrypy.request.method.upper() != "POST":
            return json_error(405, "Method not allowed")

        data = cherrypy.request.json or {}
        user_id = data.get("user_id")
        device_id = data.get("device_id")

        if user_id is None or not device_id:
            return json_error(400, "user_id and device_id are required")

        self.db.unassign_device_from_user(int(user_id), str(device_id))
        return {
            "status": "ok",
            "message": "unassigned",
            "user_id": int(user_id),
            "device_id": str(device_id),
        }

    # Authenticates a Telegram user by password and stores the chat_id for future alerts
    @cherrypy.expose
    @cherrypy.tools.json_in()
    @cherrypy.tools.json_out()
    def auth(self):
        if cherrypy.request.method.upper() != "POST":
            return json_error(405, "Method not allowed")

        data = cherrypy.request.json or {}
        password = (data.get("password") or "").strip()
        chat_id = data.get("chat_id")

        if not password or chat_id is None:
            return json_error(400, "password and chat_id are required")

        user = self.db.get_user_by_password(password)
        if not user:
            return json_error(401, "Invalid password")

        self.db.update_chat_id(user["user_id"], str(chat_id))
        devices = self.db.get_devices_for_user(user["user_id"])

        return {
            "status": "ok",
            "user_id": user["user_id"],
            "username": user["username"],
            "devices": devices,
        }

    # Returns all Telegram chat_ids linked to users that are assigned to the given device_id - used by telegram to send msg to all owner 
    @cherrypy.expose
    @cherrypy.tools.json_out()
    def device_chat_ids(self, device_id=None):
        if cherrypy.request.method.upper() != "GET":
            return json_error(405, "Method not allowed")

        device_id = device_id or cherrypy.request.params.get("device_id")
        if not device_id:
            return json_error(400, "device_id is required")

        chat_ids = self.db.get_chat_ids_by_device(str(device_id))
        return {"status": "ok", "device_id": str(device_id), "chat_ids": chat_ids}


 
def main():
    cfg = load_config()

    # Service settings (read only from config.json)
    service_cfg = cfg["service"]
    service_name = service_cfg["name"]
    host = service_cfg["host"]
    port = int(service_cfg["port"])

    # DB settings (read only from config.json)
    db_cfg = cfg["db"]
    db = MariaDB(
        db_cfg["host"],
        int(db_cfg["port"]),
        db_cfg["user"],
        db_cfg["password"],
        db_cfg["name"],
    )

    # Catalogue settings (read only from config.json)
    cat_cfg = cfg["catalog"]
    catalog_host = cat_cfg["host"]
    catalog_port = int(cat_cfg["port"])

    # Registers this service in the Service Catalogue so other components can discover it.
    registry = ServiceRegistry(catalog_host=catalog_host, catalog_port=catalog_port)
    registry.register(name=service_name, host=host, port=port)

    cherrypy.config.update({
        "server.socket_host": host,
        "server.socket_port": port
    })

    api = UserCatalogueAPI(db)
    cherrypy.tree.mount(api, "/")

    cherrypy.engine.start()
    cherrypy.engine.block()


if __name__ == "__main__":
    main()
