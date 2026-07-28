-- Student Scholarship Application and Disbursement Tracker
-- Database Schema (SQLite)
--
-- Design decision (see docs/ER_DIAGRAM.md for the full justification):
-- The application's CURRENT stage lives as a column on scholarship_applications
-- (fast to read for the list screen), but every stage TRANSITION is written
-- into its own history table, application_stage_history, and never overwritten.
-- A single "current_stage" column can only ever answer "where is it now?".
-- A separate append-only history table can additionally answer "how long did
-- it sit at each stage?", "has it happened more than once?", and "who moved
-- it and when?" -- which is exactly what the problem statement asks for
-- (find applications stuck the longest, and answer a student's status
-- instantly).

PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS document_verifications;
DROP TABLE IF EXISTS application_stage_history;
DROP TABLE IF EXISTS scholarship_applications;
DROP TABLE IF EXISTS students;

-- Entity 1: Students
CREATE TABLE students (
    student_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name       TEXT NOT NULL,
    roll_no         TEXT NOT NULL UNIQUE,
    department      TEXT NOT NULL,
    year_of_study   INTEGER NOT NULL CHECK (year_of_study BETWEEN 1 AND 5),
    email           TEXT NOT NULL UNIQUE,
    phone           TEXT NOT NULL,
    family_income   REAL NOT NULL CHECK (family_income >= 0),
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Entity 2: Scholarship Applications (one row per application, current state only)
CREATE TABLE scholarship_applications (
    application_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id           INTEGER NOT NULL,
    scholarship_type     TEXT NOT NULL CHECK (scholarship_type IN ('Merit','Means-cum-Merit','SC/ST','Minority','Differently-Abled')),
    amount_requested      REAL NOT NULL CHECK (amount_requested > 0),
    amount_sanctioned     REAL,                       -- calculated server-side once sanctioned
    current_stage         TEXT NOT NULL DEFAULT 'Submitted'
                           CHECK (current_stage IN ('Submitted','Document Verification','Section Review','Sanction','Disbursed','Rejected')),
    stage_entered_at       TEXT NOT NULL DEFAULT (datetime('now')),  -- when it entered current_stage
    applied_date            TEXT NOT NULL DEFAULT (datetime('now')),
    last_updated             TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (student_id) REFERENCES students(student_id)
);

-- Entity 3: Application Stage History (append-only; one row per transition)
CREATE TABLE application_stage_history (
    history_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    application_id   INTEGER NOT NULL,
    stage_name        TEXT NOT NULL,
    entered_at         TEXT NOT NULL DEFAULT (datetime('now')),
    exited_at           TEXT,                          -- NULL while it is the current stage
    remarks              TEXT,
    changed_by            TEXT NOT NULL DEFAULT 'system',
    FOREIGN KEY (application_id) REFERENCES scholarship_applications(application_id)
);

-- Entity 4: Document Verifications (one row per uploaded document image + model result)
CREATE TABLE document_verifications (
    verification_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    application_id     INTEGER NOT NULL,
    image_filename       TEXT NOT NULL,
    predicted_label        TEXT,                        -- 'clear' / 'unclear' / NULL if below confidence threshold
    confidence               REAL,
    verified_at                TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (application_id) REFERENCES scholarship_applications(application_id)
);

CREATE INDEX idx_app_student ON scholarship_applications(student_id);
CREATE INDEX idx_app_stage ON scholarship_applications(current_stage);
CREATE INDEX idx_history_app ON application_stage_history(application_id);
CREATE INDEX idx_docver_app ON document_verifications(application_id);
