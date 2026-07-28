"""
Loads the fine-tuned document-quality classifier (see ml/train.py) and
exposes predict_document_image() for app.py.

If no trained model file is found, falls back to a classic OpenCV
blur-detection heuristic (variance of the Laplacian) so the API endpoint
still returns a sensible answer instead of crashing.
"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, "..", "ml", "model", "document_classifier.pt")

_model = None
_labels = None


def _load_model():
    global _model, _labels
    if _model is not None:
        return
    import torch
    import torch.nn as nn
    from torchvision import models

    checkpoint = torch.load(MODEL_PATH, map_location="cpu", weights_only=False)
    _labels = checkpoint["labels"]
    model = models.mobilenet_v2(weights=None)
    model.classifier[1] = nn.Linear(model.last_channel, len(_labels))
    model.load_state_dict(checkpoint["model_state"])
    model.eval()
    _model = model


def predict_document_image(image_path: str):
    """Returns (label:str, confidence:float in [0,1]) or (None, None) on failure."""
    if os.path.exists(MODEL_PATH):
        try:
            _load_model()
            import torch
            from torchvision import transforms
            from PIL import Image

            transform = transforms.Compose([
                transforms.Resize((224, 224)),
                transforms.ToTensor(),
                transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
            ])
            img = Image.open(image_path).convert("RGB")
            x = transform(img).unsqueeze(0)
            with torch.no_grad():
                out = _model(x)
                probs = torch.softmax(out, dim=1)[0]
                idx = int(probs.argmax())
                return _labels[idx], float(probs[idx])
        except Exception as e:
            print(f"[ml_infer] trained model inference failed, falling back: {e}")

    # Fallback: classic blur detection heuristic (variance of Laplacian)
    try:
        import cv2
        img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
        if img is None:
            return None, None
        variance = cv2.Laplacian(img, cv2.CV_64F).var()
        # Higher variance = sharper image. Threshold picked empirically.
        if variance > 120:
            return "clear", min(0.99, variance / 400)
        else:
            return "unclear", min(0.99, (120 - variance) / 120 + 0.5)
    except Exception as e:
        print(f"[ml_infer] fallback heuristic failed: {e}")
        return None, None
