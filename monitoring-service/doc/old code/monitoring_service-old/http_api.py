import cherrypy
import json

class HttpAPI:
    exposed = True

    def __init__(self, db):
        self.db = db

    @cherrypy.tools.json_out()
    def GET(self, *uri, **params):
        device_id = params.get("device_id")
        if not device_id:
            raise cherrypy.HTTPError(400,"device_id required")

        row = self.db.get_last(device_id)
        if row is None:
            return {"error":"no data"}

        return row
