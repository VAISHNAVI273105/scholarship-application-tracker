# Student Scholarship Application and Disbursement Tracker

SIH 2026 Internal Practical Assessment &middot; VAISHNAVI M &middot; Reg 411724205053 &middot; PSVPEC &middot; IT &middot; Year III

A tracker that records every scholarship application, the stage it has
reached, surfaces the applications that have been stuck longest, and lets a
student's status be answered instantly.

---

## 1. What's in this repository

```
scholarship-tracker/
├── backend/          Flask API + SQLite database
│   ├── app.py
│   ├── schema.sql
│   ├── ml_infer.py    (loads the trained classifier for document verification)
│   └── requirements.txt
├── frontend/          Plain HTML/CSS/JS screens (no build step needed)
│   ├── index.html      Register a new application (Task 1)
│   ├── list.html        All applications - search, filter, ordering (Task 4)
│   └── status.html       Student status lookup
├── ml/                  Image classifier (Task 3)
│   ├── generate_dataset.py
│   ├── train.py
│   ├── dataset/            80 generated document images (clear/unclear)
│   └── model/                trained document_classifier.pt
├── tests/
│   └── integration_test.py   Task 5 - end-to-end + invalid-insert + classifier tests
├── docs/
│   ├── ER_DIAGRAM.md          schema + design justification
│   ├── er_diagram.png
│   └── presentation.pdf         6-8 slide summary (Task 6)
└── README.md (this file)
```

## 2. How to run everything

### Step 1 - Backend

```bash
cd backend
pip install -r requirements.txt
python app.py
```

This starts the API on `http://127.0.0.1:5000` and creates `scholarship.db`
(SQLite) automatically on first run using `schema.sql`.

### Step 2 - Frontend

In a second terminal:

```bash
cd frontend
python -m http.server 8080
```

Open `http://127.0.0.1:8080/index.html` in a browser. `frontend/config.js`
points the pages at the backend URL - change it there if you deploy the
backend elsewhere.

### Step 3 - (Optional) Regenerate the dataset / retrain the classifier

```bash
cd ml
pip install torch torchvision pillow numpy
python generate_dataset.py   # writes 80 labelled images to ml/dataset/
python train.py               # fine-tunes MobileNetV2, saves ml/model/document_classifier.pt
```

**Note on the classifier:** `train.py` fine-tunes a pretrained MobileNetV2
(ImageNet weights, downloaded automatically by torchvision) - only the final
classification layer is trained, on our 80 generated document images, split
by the underlying document template (`source_id`) so the same document never
appears in both train and test. If you run this in an environment with no
internet access, torchvision cannot download the ImageNet weights and the
script automatically falls back to a randomly-initialised network purely so
the pipeline still runs end-to-end (you'll see a printed warning and a low
test accuracy in that case). On a normal machine with internet, delete
`ml/model/document_classifier.pt` and re-run `train.py` to get the real
pretrained fine-tuned model.

### Step 4 - Run the integration tests (Task 5)

With the backend running:

```bash
pip install requests pillow numpy
python tests/integration_test.py
```

This exercises the full register -> list -> status -> advance-stage flow,
attempts every invalid insert the validation/DB constraints are meant to
stop (and prints the exact error returned), confirms a valid record still
inserts right after, checks the classifier's confidence-threshold logic, and
hand-checks one calculated figure.

---

## 3. What each field means

| Field | Meaning |
|---|---|
| `roll_no` | Student's college roll number, unique per student |
| `family_income` | Annual family income in Rs., used to calculate the suggested sanction |
| `amount_requested` | What the student asked for |
| `amount_sanctioned` (a.k.a. suggested sanction) | **Calculated by the server, not typed by the clerk** - see formula below |
| `current_stage` | One of: Submitted -> Document Verification -> Section Review -> Sanction -> Disbursed (or Rejected at any point) |
| `stage_entered_at` / `days_in_current_stage` | When the application entered its current stage, and how long it's been sitting there - this is what the listing screen sorts by |
| `predicted_label` / `confidence` | Output of the document-image classifier; `predicted_label` is left blank (not forced) when confidence is below 60% |

## 4. How the calculated figure works

`amount_sanctioned` (shown as "suggested sanction amount" right after
registering) is computed **server-side** in `backend/app.py ->
calculate_suggested_sanction()`, using an income slab rule:

| Annual family income | Suggested sanction |
|---|---|
| < Rs. 1,00,000 | 100% of amount requested |
| Rs. 1,00,000 - Rs. 2,49,999 | 75% of amount requested |
| >= Rs. 2,50,000 | 50% of amount requested |

Example (also checked by hand in `tests/integration_test.py`): a student
requesting Rs. 20,000 with a family income of Rs. 80,000 gets a suggested
sanction of **Rs. 20,000** (100% - income is below the first slab).

## 5. What works

- Register screen -> server validation -> server calculation -> stored in
  SQLite -> shown on screen (Task 1), fully working end to end.
- Normalised schema across 4 tables with a proper history table (Task 2).
- Document-image classifier: dataset generation, source-disjoint train/test
  split, transfer learning on a pretrained MobileNetV2, confidence
  thresholding (Task 3).
- Listing screen with search, stage/type filters, "stuck longest first"
  ordering, and a visible result count (Task 4).
- Integration tests covering the main flow, every invalid insert, the
  classifier's confidence behaviour, and a hand-checked figure, plus
  loading/empty/error states on the frontend (Task 5).

## 6. What's unfinished / a next improvement

- Authentication/roles (clerk vs section officer vs student login) are not
  implemented - anyone with the URL can currently do anything. A real
  deployment needs login and role-based permissions before it can go live.
- The classifier's real accuracy depends on training with proper internet
  access to download ImageNet weights (see the note in Section 2) - on this
  submission's build environment that download was blocked, so the shipped
  `document_classifier.pt` was trained from random initialisation as a
  fallback. Retraining with a working internet connection is the single
  most useful next step for this component.
