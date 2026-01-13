# Smart Aquarium IoT Platform

An academic IoT microservices project for **monitoring and controlling smart aquariums**.
The system reads water-quality sensors, publishes data via **MQTT**, stores it in a database, checks thresholds, sends alerts to users (Telegram),
and can remotely control actuators (feeder + water pump). Cloud visualization is supported via **ThingSpeak**.

---

## Architecture (High level)

![Smart Aquarium Architecture](architecture.png)


Core components:
- **Device Connector**: reads sensors, aggregates data (sliding window), publishes MQTT, subscribes to commands.
- **MQTT Broker (Mosquitto)**: message backbone.
- **Service Catalogue (Resource Catalogue)**: service discovery + device/resource registry.
- **Storage Service**: subscribes to sensor data and stores it in **MariaDB**; provides REST endpoint for latest data.
- **Monitoring Service**: subscribes to sensor data; evaluates thresholds; publishes alerts; may publish commands.
- **Prediction Service**: REST service using **KNN** (scikit-learn) for water-quality prediction.
- **ThingSpeak Adapter**: forwards MQTT data to ThingSpeak.
- **User Catalogue**: user management + mapping users to devices (used by Telegram + Admin Dashboard).
- **Admin Dashboard (PHP)**: web UI for user/device management.
- **Telegram Bot**: login, reports, commands, and alert notifications.

---

## MQTT Topics

### Sensor data
**Publisher:** Device Connector  
**Subscribers:** Storage Service, Monitoring Service, ThingSpeak Adapter

```
aquarium/{device_id}/sensors/agg
```

Example payload:
```json
{
  "device_id": "123",
  "temperature": 26.3,
  "nitrate": 14,
  "turbidity": 8,
  "leakage": 0,
  "timestamp": 1700000000
}
```

### Commands (actuators)
**Publishers:** Telegram Bot, Monitoring Service  
**Subscriber:** Device Connector

Feeder:
```
aquarium/{device_id}/cmd/feeder
```

Water pump:
```
aquarium/{device_id}/cmd/water_pump
```

Payload example:
```json
{ "action": "on" }
```

### Alerts
**Publisher:** Monitoring Service  
**Subscriber:** Telegram Bot

```
aquarium/{device_id}/alerts
```

---

## REST APIs (overview)

- **Storage Service**
  - `GET /devices/{device_id}/latest`  → returns latest stored measurements

- **Prediction Service**
  - `POST /predict` with JSON: `{"nitrate": <number>, "turbidity": <number>}`
  - returns: `{"status":"ok","water_quality":"good|bad","ts":...}`

Other services (Catalogue, User Catalogue) expose REST endpoints for discovery and user/device mapping.

---

## Requirements

### System / Services
- **Python 3.10+**
- **MQTT Broker**: Mosquitto
- **MariaDB Server** (or compatible MySQL/MariaDB)
- **PHP 8+** (for Admin Dashboard) + a web server (Apache/Nginx or PHP built-in server)

### Python Libraries
Install from `requirements.txt` (provided in this repo):
- cherrypy
- requests
- telepot
- pandas
- scikit-learn
- mariadb
- paho-mqtt (used by MQTT client wrapper)

---

## How to Run (Local)

> Notes:
> - Each microservice typically has its own `config.json` next to its `main.py`.
> - Start components in this order to avoid service discovery issues.
> - If you use different ports/hosts, update configs accordingly.

### 1) Start MQTT Broker (Mosquitto)
On Linux:
```bash
sudo apt-get install -y mosquitto
sudo systemctl enable --now mosquitto
```


### 2) Start MariaDB
Install (Linux):
```bash
sudo apt-get install -y mariadb-server
sudo systemctl enable --now mariadb
```

Create database + table (example):
```sql
CREATE DATABASE smart_aquariums;
USE smart_aquariums;

CREATE TABLE measurements (
  id INT AUTO_INCREMENT PRIMARY KEY,
  device_id VARCHAR(64) NOT NULL,
  ts BIGINT NOT NULL,
  sensor VARCHAR(64) NOT NULL,
  value DOUBLE NOT NULL
);

CREATE INDEX idx_device_ts ON measurements(device_id, ts);
```

### 3) Create & activate Python venv
From each Python service folder (or a root folder if you keep one venv):
```bash
python -m venv .venv
# Linux/Mac:
source .venv/bin/activate
# Windows:
# .venv\Scripts\activate
pip install -r requirements.txt
```

### 4) Run Service Catalogue
Run the catalogue service (the component that provides service discovery).
Example:
```bash
python main.py
```

### 5) Run Storage Service
Storage subscribes to `aquarium/+/sensors/agg` and stores data in MariaDB:
```bash
python main.py
```

### 6) Run Prediction Service
Prediction service exposes `POST /predict`:
```bash
python main.py
```

### 7) Run Monitoring Service
Monitoring subscribes to sensor data, checks thresholds, and publishes alerts:
```bash
python main.py
```

### 8) Run Device Connector
Device connector reads sensors (or simulated sensors), aggregates using a sliding window, and publishes MQTT:
```bash
python main.py
```

### 9) Run Telegram Bot
Telegram bot discovers services via the catalogue, sends commands, and subscribes to alerts:
```bash
python main.py
```

### 10) Run Admin Dashboard (PHP,jQuery)

