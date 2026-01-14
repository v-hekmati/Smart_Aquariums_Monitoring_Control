import random


class BaseSensor:
    # Base class for fake sensors with null + outlier generation 

    def __init__(self, name, min_valid, max_valid):
        self.name = name
        self.min_valid = min_valid
        self.max_valid = max_valid
        self.null_prob = 0.05
        self.outlier_prob = 0.1

    def read(self):
        
        # 1) chance of null
        if random.random() < self.null_prob:
            return None

        # 2) normal reading
        value = self._read_normal()

        # 3) chance of outlier
        if random.random() < self.outlier_prob:
            return self._make_outlier(value)

        return value

    def _read_normal(self):
        # generate a normal reading within [min_valid, max_valid]."""
        return random.uniform(self.min_valid, self.max_valid)

    def _make_outlier(self, value):
        # generate a value clearly outside the [min_valid, max_valid] range 
        span = abs(self.max_valid - self.min_valid)
        if random.random() < 0.5:
            # low outlier
            return self.min_valid - span
        # high outlier
        return self.max_valid + span


class TemperatureSensor(BaseSensor):
    pass


class NitrateSensor(BaseSensor):
    pass


class TurbiditySensor(BaseSensor):
    pass


class LeakageSensor(BaseSensor):
    def _read_normal(self):
        return float(random.choice([0, 0, 0, 0, 1]))
