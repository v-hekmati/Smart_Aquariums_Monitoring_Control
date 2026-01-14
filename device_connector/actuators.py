import time


class Feeder:
    def activate(self):
        print("[ACTUATOR] Feeder activated.")


class WaterPump:
    def __init__(self):
        self.is_on = False
        self.off_time = 0

    def on(self, duration_sec):
        self.is_on = True
        self.off_time = time.time() + int(duration_sec)
        print(f"[ACTUATOR] Water pump ON for {duration_sec} seconds.")

    def off(self):
        self.is_on = False
        print("[ACTUATOR] Water pump OFF.")

    def update(self):
        # turn OFF automatically after duration
        if self.is_on and time.time() >= self.off_time:
            self.off()
