"""
Task 3 - Fine-tune a small pretrained model for document-quality classification
(clear vs unclear), instead of training a CNN from scratch.

Base model : MobileNetV2 (torchvision, ImageNet-pretrained)
Strategy   : freeze the convolutional feature extractor, replace and train
             only the final classification head on our 80 images.
Split      : GROUPED by source_id (the same underlying document template
             never appears in both train and test - see generate_dataset.py)

NOTE ON RUNNING THIS IN A NETWORK-RESTRICTED SANDBOX:
torchvision downloads ImageNet weights from download.pytorch.org the first
time this runs. If that host is unreachable (e.g. a locked-down sandbox),
this script prints a warning and falls back to random-initialised weights
purely so the rest of the pipeline (loading, splitting, training loop,
evaluation, saving) can still be demonstrated end-to-end. On a normal
laptop/Colab with internet access this will download the real pretrained
weights automatically and give meaningfully better accuracy - no code
change needed.
"""
import os
import csv
import random
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from torchvision import models, transforms
from PIL import Image

random.seed(42)
torch.manual_seed(42)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATASET_DIR = os.path.join(BASE_DIR, "dataset")
MODEL_DIR = os.path.join(BASE_DIR, "model")
os.makedirs(MODEL_DIR, exist_ok=True)

LABELS = ["clear", "unclear"]
LABEL2IDX = {l: i for i, l in enumerate(LABELS)}

transform = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
])


class DocDataset(Dataset):
    def __init__(self, rows):
        self.rows = rows

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, idx):
        fname, label, _source = self.rows[idx]
        path = os.path.join(DATASET_DIR, label, fname)
        img = Image.open(path).convert("RGB")
        return transform(img), LABEL2IDX[label]


def load_manifest():
    rows = []
    with open(os.path.join(DATASET_DIR, "manifest.csv")) as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append((r["filename"], r["label"], int(r["source_id"])))
    return rows


def group_split(rows, test_fraction=0.25):
    """Split by source_id so the same document template never appears in
    both train and test."""
    source_ids = sorted(set(r[2] for r in rows))
    random.shuffle(source_ids)
    n_test_sources = max(1, int(len(source_ids) * test_fraction))
    test_sources = set(source_ids[:n_test_sources])
    train_rows = [r for r in rows if r[2] not in test_sources]
    test_rows = [r for r in rows if r[2] in test_sources]
    return train_rows, test_rows


def build_model(pretrained=True):
    try:
        weights = models.MobileNet_V2_Weights.IMAGENET1K_V1 if pretrained else None
        model = models.mobilenet_v2(weights=weights)
        used_pretrained = pretrained
    except Exception as e:
        print(f"[warn] could not download ImageNet weights ({e}); "
              f"falling back to random init so the pipeline still runs.")
        model = models.mobilenet_v2(weights=None)
        used_pretrained = False

    # Freeze feature extractor, fine-tune only the classifier head
    for param in model.features.parameters():
        param.requires_grad = False
    model.classifier[1] = nn.Linear(model.last_channel, len(LABELS))
    return model, used_pretrained


def main():
    rows = load_manifest()
    train_rows, test_rows = group_split(rows)
    print(f"Total images: {len(rows)} | train: {len(train_rows)} | test: {len(test_rows)}")
    train_sources = set(r[2] for r in train_rows)
    test_sources = set(r[2] for r in test_rows)
    assert train_sources.isdisjoint(test_sources), "LEAK: a source_id appears in both train and test!"
    print(f"train source_ids: {sorted(train_sources)}")
    print(f"test  source_ids: {sorted(test_sources)}  (disjoint from train - confirmed)")

    train_loader = DataLoader(DocDataset(train_rows), batch_size=8, shuffle=True)
    test_loader = DataLoader(DocDataset(test_rows), batch_size=8, shuffle=False)

    model, used_pretrained = build_model(pretrained=True)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model.to(device)

    optimizer = torch.optim.Adam(model.classifier.parameters(), lr=1e-3)
    criterion = nn.CrossEntropyLoss()

    EPOCHS = 6
    model.train()
    for epoch in range(EPOCHS):
        total_loss = 0.0
        for x, y in train_loader:
            x, y = x.to(device), y.to(device)
            optimizer.zero_grad()
            out = model(x)
            loss = criterion(out, y)
            loss.backward()
            optimizer.step()
            total_loss += loss.item() * x.size(0)
        print(f"epoch {epoch+1}/{EPOCHS} - loss: {total_loss/len(train_rows):.4f}")

    # Evaluation
    model.eval()
    correct, total = 0, 0
    with torch.no_grad():
        for x, y in test_loader:
            x, y = x.to(device), y.to(device)
            out = model(x)
            preds = out.argmax(dim=1)
            correct += (preds == y).sum().item()
            total += y.size(0)
    accuracy = correct / total if total else 0.0
    print(f"Test accuracy (held-out, disjoint source_ids): {accuracy*100:.1f}% ({correct}/{total})")
    print(f"Pretrained ImageNet weights used: {used_pretrained}")

    torch.save({
        "model_state": model.state_dict(),
        "labels": LABELS,
        "used_pretrained": used_pretrained,
        "test_accuracy": accuracy,
    }, os.path.join(MODEL_DIR, "document_classifier.pt"))
    print(f"Saved model to {os.path.join(MODEL_DIR, 'document_classifier.pt')}")


if __name__ == "__main__":
    main()
