"""
Student Scholarship Application and Disbursement Tracker - Backend
Flask + SQLite

Run:
    pip install -r requirements.txt
    python app.py
Server starts on http://127.0.0.1:5000
"""
import os
import re
import sqlite3
from datetime import datetime

from flask import Flask, request, jsonify, g
from flask_cors import CORS

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "scholarship.db")
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

STAGES = ["Submitted", "Document Verification", "Section Review", "Sanction", "Disbursed", "Rejected"]
SCHOLARSHIP_TYPES = ["Merit", "Means-cum-Merit", "SC/ST", "Minority", "Differently-Abled"]

app = Flask(__name__)
CORS(app)


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    with app.app_context():
        db = get_db()
        with open(os.path.join(BASE_DIR, "schema.sql"), "r") as f:
            db.executescript(f.read())
        db.commit()


# ---------------------------------------------------------------------------
# Server-side calculation (Task 1 requirement: derived figure calculated on
# the server, not the client, so every viewer sees the same number)
# ---------------------------------------------------------------------------
def calculate_suggested_sanction(amount_requested: float, family_income: float) -> float:
    """
    Slab-based suggestion, purely a server-side business rule so every client
    sees the same figure:
      income <  1,00,000  -> 100% of requested amount
      income <  2,50,000  -> 75% of requested amount
      income >= 2,50,000  -> 50% of requested amount
    """
    if family_income < 100000:
        pct = 1.0
    elif family_income < 250000:
        pct = 0.75
    else:
        pct = 0.50
    return round(amount_requested * pct, 2)


# ---------------------------------------------------------------------------
# Validation helpers - every field is validated here, server-side.
# ---------------------------------------------------------------------------
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^[6-9]\d{9}$")  # Indian 10-digit mobile


def validate_registration(data: dict):
    errors = []

    full_name = (data.get("full_name") or "").strip()
    if not full_name or len(full_name) < 3:
        errors.append("full_name is required and must be at least 3 characters")

    roll_no = (data.get("roll_no") or "").strip()
    if not roll_no:
        errors.append("roll_no is required")

    department = (data.get("department") or "").strip()
    if not department:
        errors.append("department is required")

    try:
        year_of_study = int(data.get("year_of_study"))
        if not (1 <= year_of_study <= 5):
            errors.append("year_of_study must be between 1 and 5")
    except (TypeError, ValueError):
        errors.append("year_of_study must be a whole number")

    email = (data.get("email") or "").strip()
    if not EMAIL_RE.match(email):
        errors.append("email is not a valid email address")

    phone = (data.get("phone") or "").strip()
    if not PHONE_RE.match(phone):
        errors.append("phone must be a valid 10-digit mobile number")

    try:
        family_income = float(data.get("family_income"))
        if family_income < 0:
            errors.append("family_income cannot be negative")
    except (TypeError, ValueError):
        errors.append("family_income must be a number")

    scholarship_type = (data.get("scholarship_type") or "").strip()
    if scholarship_type not in SCHOLARSHIP_TYPES:
        errors.append(f"scholarship_type must be one of {SCHOLARSHIP_TYPES}")

    try:
        amount_requested = float(data.get("amount_requested"))
        if amount_requested <= 0:
            errors.append("amount_requested must be greater than 0")
    except (TypeError, ValueError):
        errors.append("amount_requested must be a number")

    return errors


# ---------------------------------------------------------------------------
# Task 1: Register endpoint (end to end: form -> validate -> calculate -> store)
# ---------------------------------------------------------------------------
@app.route("/api/register", methods=["POST"])
def register_application():
    data = request.get_json(silent=True) or {}
    errors = validate_registration(data)
    if errors:
        return jsonify({"success": False, "errors": errors}), 400

    db = get_db()
    try:
        cur = db.execute(
            """INSERT INTO students (full_name, roll_no, department, year_of_study, email, phone, family_income)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(roll_no) DO UPDATE SET
                 full_name=excluded.full_name, department=excluded.department,
                 year_of_study=excluded.year_of_study, email=excluded.email,
                 phone=excluded.phone, family_income=excluded.family_income
            """,
            (
                data["full_name"].strip(), data["roll_no"].strip(), data["department"].strip(),
                int(data["year_of_study"]), data["email"].strip(), data["phone"].strip(),
                float(data["family_income"]),
            ),
        )
        student_row = db.execute("SELECT student_id FROM students WHERE roll_no = ?", (data["roll_no"].strip(),)).fetchone()
        student_id = student_row["student_id"]

        amount_requested = float(data["amount_requested"])
        family_income = float(data["family_income"])
        suggested_sanction = calculate_suggested_sanction(amount_requested, family_income)

        cur = db.execute(
            """INSERT INTO scholarship_applications
               (student_id, scholarship_type, amount_requested, amount_sanctioned, current_stage, stage_entered_at)
               VALUES (?, ?, ?, ?, 'Submitted', datetime('now'))""",
            (student_id, data["scholarship_type"].strip(), amount_requested, suggested_sanction),
        )
        application_id = cur.lastrowid

        db.execute(
            """INSERT INTO application_stage_history (application_id, stage_name, entered_at, changed_by)
               VALUES (?, 'Submitted', datetime('now'), 'clerk')""",
            (application_id,),
        )
        db.commit()
    except sqlite3.IntegrityError as e:
        db.rollback()
        return jsonify({"success": False, "errors": [f"database constraint failed: {e}"]}), 400
    except sqlite3.Error as e:
        db.rollback()
        return jsonify({"success": False, "errors": [f"database error: {e}"]}), 500

    return jsonify({
        "success": True,
        "application_id": application_id,
        "student_id": student_id,
        "suggested_sanction_amount": suggested_sanction,
        "current_stage": "Submitted",
    }), 201


# ---------------------------------------------------------------------------
# Task 4: Listing, search, filter, ordering (whatever needs attention first)
# ---------------------------------------------------------------------------
@app.route("/api/applications", methods=["GET"])
def list_applications():
    search = request.args.get("search", "").strip()
    stage_filter = request.args.get("stage", "").strip()
    scholarship_filter = request.args.get("scholarship_type", "").strip()

    query = """
        SELECT a.application_id, s.full_name, s.roll_no, s.department,
               a.scholarship_type, a.amount_requested, a.amount_sanctioned,
               a.current_stage, a.stage_entered_at, a.applied_date,
               CAST((julianday('now') - julianday(a.stage_entered_at)) AS INTEGER) AS days_in_current_stage
        FROM scholarship_applications a
        JOIN students s ON s.student_id = a.student_id
        WHERE 1=1
    """
    params = []
    if search:
        query += " AND (s.full_name LIKE ? OR s.roll_no LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%"])
    if stage_filter:
        query += " AND a.current_stage = ?"
        params.append(stage_filter)
    if scholarship_filter:
        query += " AND a.scholarship_type = ?"
        params.append(scholarship_filter)

    # Ordering: whatever needs attention first = applications stuck longest
    # in a non-terminal stage rise to the top.
    query += """
        ORDER BY
          CASE WHEN a.current_stage IN ('Disbursed','Rejected') THEN 1 ELSE 0 END,
          days_in_current_stage DESC
    """

    db = get_db()
    rows = db.execute(query, params).fetchall()
    results = [dict(r) for r in rows]
    return jsonify({"count": len(results), "results": results})


# ---------------------------------------------------------------------------
# Student status lookup - answer "where has my application reached" instantly
# ---------------------------------------------------------------------------
@app.route("/api/status/<roll_no>", methods=["GET"])
def get_status(roll_no):
    db = get_db()
    rows = db.execute(
        """SELECT a.application_id, a.scholarship_type, a.current_stage, a.stage_entered_at,
                  a.amount_requested, a.amount_sanctioned,
                  CAST((julianday('now') - julianday(a.stage_entered_at)) AS INTEGER) AS days_in_current_stage
           FROM scholarship_applications a
           JOIN students s ON s.student_id = a.student_id
           WHERE s.roll_no = ?
           ORDER BY a.applied_date DESC""",
        (roll_no,),
    ).fetchall()
    if not rows:
        return jsonify({"success": False, "message": "No application found for this roll number"}), 404
    return jsonify({"success": True, "applications": [dict(r) for r in rows]})


# ---------------------------------------------------------------------------
# Advance stage (writes history correctly: close old row, open new row)
# ---------------------------------------------------------------------------
@app.route("/api/applications/<int:application_id>/advance", methods=["POST"])
def advance_stage(application_id):
    data = request.get_json(silent=True) or {}
    next_stage = (data.get("next_stage") or "").strip()
    remarks = (data.get("remarks") or "").strip()
    changed_by = (data.get("changed_by") or "section_officer").strip()

    if next_stage not in STAGES:
        return jsonify({"success": False, "errors": [f"next_stage must be one of {STAGES}"]}), 400

    db = get_db()
    app_row = db.execute("SELECT * FROM scholarship_applications WHERE application_id = ?", (application_id,)).fetchone()
    if app_row is None:
        return jsonify({"success": False, "errors": ["application not found"]}), 404

    try:
        db.execute(
            """UPDATE application_stage_history SET exited_at = datetime('now')
               WHERE application_id = ? AND exited_at IS NULL""",
            (application_id,),
        )
        db.execute(
            """UPDATE scholarship_applications
               SET current_stage = ?, stage_entered_at = datetime('now'), last_updated = datetime('now')
               WHERE application_id = ?""",
            (next_stage, application_id),
        )
        db.execute(
            """INSERT INTO application_stage_history (application_id, stage_name, entered_at, remarks, changed_by)
               VALUES (?, ?, datetime('now'), ?, ?)""",
            (application_id, next_stage, remarks, changed_by),
        )
        db.commit()
    except sqlite3.Error as e:
        db.rollback()
        return jsonify({"success": False, "errors": [f"database error: {e}"]}), 500

    return jsonify({"success": True, "application_id": application_id, "current_stage": next_stage})


# ---------------------------------------------------------------------------
# Task 3/5: Document image verification using the fine-tuned classifier
# ---------------------------------------------------------------------------
@app.route("/api/applications/<int:application_id>/verify-document", methods=["POST"])
def verify_document(application_id):
    if "image" not in request.files:
        return jsonify({"success": False, "errors": ["image file is required (multipart field 'image')"]}), 400

    file = request.files["image"]
    filename = f"app{application_id}_{int(datetime.now().timestamp())}_{file.filename}"
    save_path = os.path.join(UPLOAD_DIR, filename)
    file.save(save_path)

    from ml_infer import predict_document_image
    label, confidence = predict_document_image(save_path)

    CONFIDENCE_THRESHOLD = 0.60
    final_label = label if confidence is not None and confidence >= CONFIDENCE_THRESHOLD else None

    db = get_db()
    db.execute(
        """INSERT INTO document_verifications (application_id, image_filename, predicted_label, confidence)
           VALUES (?, ?, ?, ?)""",
        (application_id, filename, final_label, confidence),
    )
    db.commit()

    return jsonify({
        "success": True,
        "predicted_label": final_label,
        "confidence": confidence,
        "note": None if final_label else "confidence below threshold - no forced prediction, needs manual review",
    })


# ---------------------------------------------------------------------------
# Change 1 (8 marks): grouped count of applications per stage, most to least
# ---------------------------------------------------------------------------
@app.route("/api/reports/stage-counts", methods=["GET"])
def stage_counts():
    db = get_db()
    rows = db.execute(
        """SELECT current_stage, COUNT(*) AS total_applications
           FROM scholarship_applications
           GROUP BY current_stage
           ORDER BY total_applications DESC"""
    ).fetchall()
    return jsonify([dict(r) for r in rows])


# ---------------------------------------------------------------------------
# Change 2 (12 marks): students who registered but never submitted an
# application - LEFT JOIN ... IS NULL finds rows with no matching child row
# ---------------------------------------------------------------------------
@app.route("/api/reports/students-without-application", methods=["GET"])
def students_without_application():
    db = get_db()
    rows = db.execute(
        """SELECT s.student_id, s.full_name, s.roll_no, s.department
           FROM students s
           LEFT JOIN scholarship_applications a ON a.student_id = s.student_id
           WHERE a.application_id IS NULL"""
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    if not os.path.exists(DB_PATH):
        init_db()
        print("Database initialised at", DB_PATH)
    app.run(debug=False, port=5000)
