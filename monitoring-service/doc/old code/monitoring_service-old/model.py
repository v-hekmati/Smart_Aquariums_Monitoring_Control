import pickle

class KNNModel:
    def __init__(self, path="knn_model.pkl"):
        with open(path,"rb") as f:
            self.model = pickle.load(f)

    def predict(self, X):
        return self.model.predict(X)
