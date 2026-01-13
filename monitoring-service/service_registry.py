import requests

class ServiceRegistry:
    
    def __init__(self, catalog_host="localhost", catalog_port=8080):
        self.base_url = f"http://{catalog_host}:{catalog_port}"

    def register(self, name, host, port):
        url = f"{self.base_url}/services/register"
        payload = {
            "name": name,
            "host": host,
            "port": port
        }

        try:
            r = requests.post(url, json=payload, timeout=4)
            print(f"[CATALOGUE] register -> {r.status_code} {r.text}")
            return r.status_code == 200
        except Exception as e:
            print(f"[CATALOGUE] register failed -> {e}")
            return False
