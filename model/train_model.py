import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
import joblib

print("Training started...")

df = pd.read_csv("data/train.csv").sample(n=50000, random_state=42)

features = [
    "Transaction Amount",
    "Quantity",
    "Customer Age",
    "Account Age Days",
    "Transaction Hour"
]

X = df[features]
y = df["Is Fraudulent"]

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2
)

model = RandomForestClassifier(n_estimators=50)
model.fit(X_train, y_train)

joblib.dump(model, "model/model.pkl")

print("Model saved ✔")