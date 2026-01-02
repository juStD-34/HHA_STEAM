import os
import pandas as pd
from sklearn.tree import DecisionTreeClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score

from .constants import DATA_FILE

_model = None
_model_accuracy = 0.0


def train_model():
    global _model, _model_accuracy
    if not os.path.exists(DATA_FILE):
        return "Data file not found."

    df = pd.read_csv(DATA_FILE)
    X = df[['Time', 'Errors', 'Score']]
    y = df['Group']

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    clf = DecisionTreeClassifier()
    clf.fit(X_train, y_train)

    y_pred = clf.predict(X_test)
    _model_accuracy = accuracy_score(y_test, y_pred)

    _model = clf
    return "Model trained successfully."


def ensure_model():
    if _model is None:
        train_model()
    return _model


def get_accuracy():
    return _model_accuracy


def is_model_loaded():
    return _model is not None
