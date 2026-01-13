import pandas as pd
import pickle
from sklearn.neighbors import KNeighborsClassifier

def main():
    # Load training data
    df = pd.read_csv("knn_training_data.csv")

    # Features (X) and labels (y)
    X = df[["turbidity", "nitrate"]].values
    y = df["service_needed"].values

    # Create and train KNN model
    model = KNeighborsClassifier(n_neighbors=3)
    model.fit(X, y)

    # Save trained model
    with open("knn_model.pkl", "wb") as f:
        pickle.dump(model, f)

    print("KNN model trained and saved to knn_model.pkl")

if __name__ == "__main__":
    main()
