import json
import time

import cherrypy
from sklearn.neighbors import KNeighborsClassifier

from service_registry import ServiceRegistry


def now_ts(): 
    return int(time.time())


class PredictionService:
    
  
    
   #   POST /predict
   #     input:  {"nitrate": number, "turbidity": number}
   #     output: {"status":"ok","water_quality":"good|bad","ts":...}
 
     

    def __init__(self, k, nitrate_scale, turbidity_scale):
        self.k = int(k)
        self.nitrate_scale = float(nitrate_scale)
        self.turbidity_scale = float(turbidity_scale)

        self.model = KNeighborsClassifier(n_neighbors=self.k)
        self._fit_demo_model()

    def _norm(self, nitrate, turbidity):
        #  normalization: put both features on comparable numeric scales
        return [float(nitrate) / self.nitrate_scale, float(turbidity) / self.turbidity_scale]

    def _fit_demo_model(self):
        
        
        X = [
            # GOOD region (lower nitrate and lower turbidity)
            [0.05, 0.05], [0.10, 0.08], [0.20, 0.10], [0.30, 0.15], [0.35, 0.20], [0.40, 0.25],
            # BAD region (higher nitrate and/or higher turbidity)
            [0.50, 0.30], [0.60, 0.40], [0.70, 0.50], [0.80, 0.60], [0.90, 0.70], [1.00, 0.80],
            [0.30, 0.60], [0.40, 0.70], [0.20, 0.80],
        ]
        y = [
            "good","good","good","good","good","good",
            "bad","bad","bad","bad","bad","bad",
            "bad","bad","bad",
        ]
        self.model.fit(X, y)

    @cherrypy.expose
    @cherrypy.tools.json_in()
    @cherrypy.tools.json_out()
    def predict(self):
        data = cherrypy.request.json or {}

        nitrate = data.get("nitrate")
        turbidity = data.get("turbidity")

        if not isinstance(nitrate, (int, float)) or not isinstance(turbidity, (int, float)):
            cherrypy.response.status = 400
            return {"status": "error", "message": "nitrate and turbidity must be numbers"}

         
        x = self._norm(nitrate, turbidity)

        label = self.model.predict([x])[0]

        return {
            "status": "ok",
            "water_quality": label,
            "ts": now_ts()
        }


def load_config():
    with open("config.json", "r") as f:
        return json.load(f)


def main():
    cfg = load_config()

    name = cfg.get("service_name", "prediction_service")
    host = cfg.get("host", "localhost")
    port = int(cfg.get("port", 8092))

    
    catalog_host = cfg.get("catalog_host", "localhost")
    catalog_port = int(cfg.get("catalog_port", 8080))

    # Normalization scales
    nitrate_scale = cfg.get("nitrate_scale", 100)
    turbidity_scale = cfg.get("turbidity_scale", 100)

    # Register in Service Catalogue
    registry = ServiceRegistry(catalog_host=catalog_host, catalog_port=catalog_port)
    registry.register(name, host, port)

    app = PredictionService(
        k=cfg.get("k", 3),
        nitrate_scale=nitrate_scale,
        turbidity_scale=turbidity_scale
    )

    cherrypy.config.update({
        "server.socket_host": host,
        "server.socket_port": port,
    })

    cherrypy.quickstart(app, "/")


if __name__ == "__main__":
    main()
