from collections import deque
import pandas as pd


class SlidingWindow:
    #Fixed-size window of recent sensor records (dicts) 

    def __init__(self, size):
        self.size = size
        self.values = deque(maxlen=size)

    def add(self, record):
        self.values.append(record)

    def is_full(self):
        return len(self.values) == self.size

    def mean(self):
        #Return the mean of each field using pandas, if window is full 
        if not self.is_full():
            return None

        df = pd.DataFrame(self.values)
        return df.mean().to_dict()


class Preprocessor:
    #Clean raw sensor readings and aggregate them on a sliding window

    def __init__(self, window_size, sensor_limits):
        self.window = SlidingWindow(window_size)
        self.limits = sensor_limits

    def clean_record(self, record):
        # drop record if any value is None or out of  range 
        for key, value in record.items():
            if value is None:
                return None

            lim = self.limits[key]
            min_v = lim["min_valid"]
            max_v = lim["max_valid"]

            if value < min_v or value > max_v:
                return None

        return record

    def process(self, raw_record):
        #Process a raw record:
        #- clean (null/outlier)
        #- append to sliding window
        # - if window full -> return mean, else None
        
        clean = self.clean_record(raw_record)
        if clean is None:
            return None

        self.window.add(clean)

        if self.window.is_full():
            return self.window.mean()

        return None
