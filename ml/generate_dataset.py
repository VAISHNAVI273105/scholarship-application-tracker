"""
Generates a small labelled image dataset for the document-quality classifier
(Task 3). The problem statement allows generated images ("you may photograph
or generate them"), so this script synthesises certificate-like document
photos in two classes:

    clear    -> sharp, well-lit, readable document photo
    unclear  -> blurred / dark / noisy photo a clerk would reject

IMPORTANT for the train/test split (Task 3 requirement - "the same source or
object never appears in both training and test"): every image is generated
from one of 10 underlying document TEMPLATES (source_id 0-9), each rendered
several times with different quality conditions. train.py splits by
source_id, not by individual image, so the same underlying document never
leaks across the split.
"""
import os
import random
from PIL import Image, ImageDraw, ImageFont, ImageFilter

random.seed(42)

OUT_DIR = os.path.join(os.path.dirname(__file__), "dataset")
CLEAR_DIR = os.path.join(OUT_DIR, "clear")
UNCLEAR_DIR = os.path.join(OUT_DIR, "unclear")
os.makedirs(CLEAR_DIR, exist_ok=True)
os.makedirs(UNCLEAR_DIR, exist_ok=True)

NAMES = ["Arun Kumar", "Vaishnavi M", "Deepak R", "Priya S", "Karthik V",
         "Meena L", "Ravi Shankar", "Divya P", "Suresh Babu", "Anitha K"]
DEPTS = ["IT", "CSE", "ECE", "MECH", "EEE", "CIVIL"]

N_TEMPLATES = 10          # 10 distinct "documents" (source_id)
VARIANTS_PER_TEMPLATE = 8  # clear + unclear variants of each -> 80 images total


def render_certificate(name, dept, roll):
    img = Image.new("RGB", (600, 400), color=(250, 248, 240))
    draw = ImageDraw.Draw(img)
    draw.rectangle([10, 10, 589, 389], outline=(30, 30, 30), width=3)
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None
    draw.text((150, 40), "INCOME / BONAFIDE CERTIFICATE", fill=(10, 10, 10), font=font)
    draw.text((60, 120), f"Name: {name}", fill=(10, 10, 10), font=font)
    draw.text((60, 160), f"Department: {dept}", fill=(10, 10, 10), font=font)
    draw.text((60, 200), f"Roll No: {roll}", fill=(10, 10, 10), font=font)
    draw.text((60, 240), "This is to certify that the above student", fill=(10, 10, 10), font=font)
    draw.text((60, 270), "belongs to the stated category.", fill=(10, 10, 10), font=font)
    draw.text((350, 340), "Signature: ____________", fill=(10, 10, 10), font=font)
    return img


def degrade(img, level):
    """Turn a clean render into a realistic 'bad photo' of varying severity."""
    out = img.filter(ImageFilter.GaussianBlur(radius=level["blur"]))
    # darken / wash out
    out = Image.eval(out, lambda p: max(0, min(255, int(p * level["brightness"]))))
    # add noise
    import numpy as np
    arr = np.array(out).astype("int16")
    noise = (np.random.randn(*arr.shape) * level["noise"]).astype("int16")
    arr = arr + noise
    arr = arr.clip(0, 255).astype("uint8")
    return Image.fromarray(arr)


def main():
    manifest = []
    for source_id in range(N_TEMPLATES):
        name = NAMES[source_id]
        dept = random.choice(DEPTS)
        roll = f"41172420{5050 + source_id}"
        base = render_certificate(name, dept, roll)

        for v in range(VARIANTS_PER_TEMPLATE):
            is_clear = v < VARIANTS_PER_TEMPLATE // 2
            if is_clear:
                # mild, still-readable variation (different lighting only)
                level = {"blur": random.uniform(0, 0.4), "brightness": random.uniform(0.9, 1.05), "noise": random.uniform(1, 4)}
                img = degrade(base, level)
                label = "clear"
                out_dir = CLEAR_DIR
            else:
                level = {"blur": random.uniform(2.5, 5.0), "brightness": random.uniform(0.4, 0.7), "noise": random.uniform(15, 30)}
                img = degrade(base, level)
                label = "unclear"
                out_dir = UNCLEAR_DIR

            fname = f"src{source_id:02d}_v{v}.png"
            img.save(os.path.join(out_dir, fname))
            manifest.append((fname, label, source_id))

    with open(os.path.join(OUT_DIR, "manifest.csv"), "w") as f:
        f.write("filename,label,source_id\n")
        for fname, label, source_id in manifest:
            f.write(f"{fname},{label},{source_id}\n")

    n_clear = sum(1 for _, l, _ in manifest if l == "clear")
    n_unclear = sum(1 for _, l, _ in manifest if l == "unclear")
    print(f"Generated {len(manifest)} images -> clear: {n_clear}, unclear: {n_unclear}")
    print(f"Saved to {OUT_DIR} (manifest.csv records filename,label,source_id)")


if __name__ == "__main__":
    main()
