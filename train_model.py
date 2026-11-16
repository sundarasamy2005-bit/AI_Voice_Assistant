
import csv
import os
import joblib

from sklearn.pipeline import Pipeline
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.svm import LinearSVC

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE_DIR, "intants.csv")
MODEL_DIR = os.path.join(BASE_DIR, "models")
MODEL_PATH = os.path.join(MODEL_DIR, "voice_intant_model.joblib")

texts = []
labels = []

with open(CSV_PATH, "r", newline="", encoding="utf-8-sig") as file:
    reader = csv.DictReader(file)

    print("CSV columns:", reader.fieldnames)

    if reader.fieldnames != ["text", "intant"]:
        raise ValueError("CSV header must be exactly: text,intant")

    for row in reader:
        text = row["text"].strip()
        intant = row["intant"].strip()

        if text and intant:
            texts.append(text)
            labels.append(intant)

if not texts:
    raise ValueError("Dataset is empty.")

if len(set(labels)) < 2:
    raise ValueError("At least two intants are required.")

model = Pipeline([
    ("tfidf", TfidfVectorizer(ngram_range=(1, 2))),
    ("classifier", LinearSVC(C=1.0))
])

model.fit(texts, labels)

os.makedirs(MODEL_DIR, exist_ok=True)
joblib.dump(model, MODEL_PATH)

print("\nTraining successful!")
print("Examples:", len(texts))
print("Intants:", sorted(set(labels)))
print("Saved:", MODEL_PATH)
print("File size:", os.path.getsize(MODEL_PATH), "bytes")
