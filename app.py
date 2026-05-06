from flask import Flask, render_template, request, redirect, session
from datetime import date
import sqlite3  # ← built into Python, no install needed
import os

app = Flask(__name__)
app.secret_key = "clinic_secret_key"

USERS = {
    "receptionist1": {"password": "rec123", "role": "receptionist"},
    "doctor1":        {"password": "doc123", "role": "doctor"},
    "medstaff1":      {"password": "med123", "role": "medical_staff"},
}

DATABASE = "clinic.db"  # ← new database file 

# ── DATABASE HELPER ───────────────────────────────────────────────────────────
# This function opens a connection to the database
def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row  # access columns by name (like a dict)
    return conn

# ── CREATE TABLES (runs once) ─────────────────────────────────
# This creates the tables if they don't exist yet
# Like setting up the structure of data.json for the first time
def init_db():
    conn = get_db()

    # CREATE TABLE = define the structure of each table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS patients (
            id        TEXT PRIMARY KEY,   -- unique patient ID (e.g. P001)
            name      TEXT NOT NULL,      -- full name
            age       TEXT NOT NULL,      -- age
            gender    TEXT NOT NULL,      -- Male/Female/Other
            contact   TEXT NOT NULL,      -- phone number
            condition TEXT NOT NULL       -- Urgent/Priority/General
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS appointments (
            appointment_id TEXT PRIMARY KEY,  -- e.g. A001
            patient_id     TEXT NOT NULL,     -- links to patients table
            doctor         TEXT NOT NULL,
            date           TEXT NOT NULL,
            time           TEXT NOT NULL,
            reason         TEXT NOT NULL,
            status         TEXT NOT NULL,
            FOREIGN KEY (patient_id) REFERENCES patients(id)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS history (
            id         INTEGER PRIMARY KEY AUTOINCREMENT, -- auto number
            patient_id TEXT NOT NULL,   -- links to patients table
            date       TEXT NOT NULL,
            diagnosis  TEXT NOT NULL,
            medication TEXT NOT NULL,
            notes      TEXT,
            FOREIGN KEY (patient_id) REFERENCES patients(id)
        )
    """)

    conn.commit()   # ← save the changes (like save_data() before)
    conn.close()    # ← close the connection (like closing the file)

# ── ROUTES ────────────────────────────────────────────────────────────────────
@app.route("/")
def home():
    return redirect("/login")

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        if username in USERS and USERS[username]["password"] == password:
            session["username"] = username
            session["role"]     = USERS[username]["role"]
            return redirect("/dashboard")
        else:
            error = "Invalid username or password."
    return render_template("login.html", error=error)

# ── DASHBOARD ─────────────────────────────────────────────────────────────────
@app.route("/dashboard")
def dashboard():
    if "username" not in session:
        return redirect("/login")

    conn  = get_db()
    today = date.today().isoformat()

    # SELECT = read from the database (replaces load_data())
    # COUNT(*) = count how many rows match
    stats = {
        "total_patients":     conn.execute("SELECT COUNT(*) FROM patients").fetchone()[0],
        "total_appointments": conn.execute("SELECT COUNT(*) FROM appointments").fetchone()[0],
        "appointments_today": conn.execute("SELECT COUNT(*) FROM appointments WHERE date = ?", (today,)).fetchone()[0],
        "urgent":   conn.execute("SELECT COUNT(*) FROM patients WHERE condition = 'Urgent'").fetchone()[0],
        "priority": conn.execute("SELECT COUNT(*) FROM patients WHERE condition = 'Priority'").fetchone()[0],
        "general":  conn.execute("SELECT COUNT(*) FROM patients WHERE condition = 'General'").fetchone()[0],
    }

    # Get last 5 patients added (ORDER BY rowid DESC = newest first)
    recent_patients = conn.execute(
        "SELECT * FROM patients ORDER BY rowid DESC LIMIT 5"
    ).fetchall()

    # Get appointments per doctor for the bar chart
    doctor_rows = conn.execute(
        "SELECT doctor, COUNT(*) as cnt FROM appointments GROUP BY doctor"
    ).fetchall()
    doctor_labels = [r["doctor"] for r in doctor_rows]
    doctor_counts = [r["cnt"]    for r in doctor_rows]

    conn.close()

    return render_template("dashboard.html",
                           role=session["role"],
                           username=session["username"],
                           stats=stats,
                           recent_patients=recent_patients,
                           doctor_labels=doctor_labels,
                           doctor_counts=doctor_counts)

# ── ADD PATIENT ───────────────────────────────────────────────────────────────
@app.route("/add_patient", methods=["GET", "POST"])
def add_patient():
    if "username" not in session:
        return redirect("/login")
    if session["role"] != "receptionist":
        return redirect("/dashboard")

    message = None

    if request.method == "POST":
        pid       = request.form["patient_id"].strip()
        name      = request.form["name"].strip()
        age       = request.form["age"].strip()
        gender    = request.form["gender"]
        contact   = request.form["contact"].strip()
        condition = request.form["condition"]

        conn = get_db()

        # Check if patient ID already exists
        # SELECT = search, fetchone() = get one result
        existing = conn.execute(
            "SELECT id FROM patients WHERE id = ?", (pid,)
        ).fetchone()

        if existing:
            message = {"type": "error", "text": f"Patient ID {pid} already exists!"}
        else:
            # INSERT = add a new row to the table (replaces appending to list)
            conn.execute(
                "INSERT INTO patients (id, name, age, gender, contact, condition) VALUES (?, ?, ?, ?, ?, ?)",
                (pid, name, age, gender, contact, condition)
            )
            conn.commit()  # save the change!
            message = {"type": "success", "text": f"Patient {name} added successfully!"}

        conn.close()

    return render_template("add_patient.html", message=message)

# ── VIEW PATIENTS ─────────────────────────────────────────────────────────────
@app.route("/view_patients")
def view_patients():
    if "username" not in session:
        return redirect("/login")
    conn     = get_db()
    patients = conn.execute("SELECT * FROM patients").fetchall()
    conn.close()
    # Add role and username here so the sidebar works!
    return render_template("view_patients.html", 
                           patients=patients, 
                           role=session["role"], 
                           username=session["username"])

# ── SCHEDULE APPOINTMENT ──────────────────────────────────────────────────────
@app.route("/schedule_appointment", methods=["GET", "POST"])
def schedule_appointment():
    if "username" not in session:
        return redirect("/login")
    if session["role"] != "receptionist":
        return redirect("/dashboard")

    message  = None
    conn     = get_db()
    patients = conn.execute("SELECT * FROM patients").fetchall()

    if request.method == "POST":
        patient_id = request.form["patient_id"].strip()
        doctor     = request.form["doctor"].strip()
        appt_date  = request.form["date"].strip()
        appt_time  = request.form["time"].strip()
        reason     = request.form["reason"].strip()

        # Check patient exists
        existing_patient = conn.execute(
            "SELECT id FROM patients WHERE id = ?", (patient_id,)
        ).fetchone()

        if not existing_patient:
            message = {"type": "error", "text": f"Patient ID '{patient_id}' not found."}
        else:
            # Check for conflicts — same doctor, same date, same time
            conflict = conn.execute(
                "SELECT * FROM appointments WHERE doctor = ? AND date = ? AND time = ?",
                (doctor, appt_date, appt_time)
            ).fetchone()

            if conflict:
                message = {"type": "error", "text": f"⚠️ Conflict Detected! {doctor} already has an appointment on {appt_date} at {appt_time}."}
            else:
                # Generate appointment ID
                count = conn.execute("SELECT COUNT(*) FROM appointments").fetchone()[0]
                appt_id = f"A{count + 1:03d}"

                conn.execute(
                    "INSERT INTO appointments (appointment_id, patient_id, doctor, date, time, reason, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (appt_id, patient_id, doctor, appt_date, appt_time, reason, "Scheduled")
                )
                conn.commit()
                message = {"type": "success", "text": f"✅ Appointment {appt_id} scheduled successfully!"}

    conn.close()
    return render_template("schedule_appointment.html", message=message, patients=patients)

# ── VIEW APPOINTMENTS ─────────────────────────────────────────────────────────
@app.route("/view_appointments")
def view_appointments():
    if "username" not in session:
        return redirect("/login")

    conn = get_db()
    # JOIN = combine appointments + patients tables to get patient name
    appointments = conn.execute("""
        SELECT a.*, p.name as patient_name
        FROM appointments a
        JOIN patients p ON a.patient_id = p.id
        ORDER BY a.date, a.time
    """).fetchall()
    conn.close()

    # CRITICAL FIX: Pass role and username so the sidebar can render!
    return render_template("view_appointments.html", 
                           appointments=appointments,
                           role=session["role"],
                           username=session["username"])

# ── TRIAGE ────────────────────────────────────────────────────────────────────
@app.route("/triage", methods=["GET", "POST"])
def triage():
    if "username" not in session:
        return redirect("/login")
    if session["role"] != "medical_staff":
        return redirect("/dashboard")

    conn    = get_db()
    message = None

    if request.method == "POST":
        patient_id = request.form["patient_id"].strip()
        condition  = request.form["condition"]

        # UPDATE = change an existing row (replaces editing the dict and save_data())
        result = conn.execute(
            "UPDATE patients SET condition = ? WHERE id = ?",
            (condition, patient_id)
        )
        conn.commit()

        if result.rowcount > 0:   # rowcount = how many rows were updated
            message = {"type": "success", "text": f"✅ Patient {patient_id} priority updated to {condition}!"}
        else:
            message = {"type": "error", "text": f"❌ Patient ID '{patient_id}' not found."}

    patients = conn.execute("SELECT * FROM patients").fetchall()
    conn.close()
    return render_template("triage.html", message=message, patients=patients)

# ── PRIORITY QUEUE ────────────────────────────────────────────────────────────
@app.route("/priority_queue")
def priority_queue():
    if "username" not in session:
        return redirect("/login")

    conn = get_db()
    # CASE WHEN = sort Urgent first, Priority second, General third
    patients = conn.execute("""
        SELECT * FROM patients
        ORDER BY CASE condition
            WHEN 'Urgent'   THEN 1
            WHEN 'Priority' THEN 2
            WHEN 'General'  THEN 3
            ELSE 4
        END
    """).fetchall()
    conn.close()
    return render_template("priority_queue.html", patients=patients)

# ── ADD HISTORY ───────────────────────────────────────────────────────────────
@app.route("/add_history", methods=["GET", "POST"])
def add_history():
    if "username" not in session:
        return redirect("/login")
    if session["role"] != "doctor":
        return redirect("/dashboard")

    conn    = get_db()
    message = None

    if request.method == "POST":
        patient_id = request.form["patient_id"].strip()
        hist_date  = request.form["date"].strip()
        diagnosis  = request.form["diagnosis"].strip()
        medication = request.form["medication"].strip()
        notes      = request.form["notes"].strip()

        # Check patient exists first
        existing = conn.execute(
            "SELECT id FROM patients WHERE id = ?", (patient_id,)
        ).fetchone()

        if not existing:
            message = {"type": "error", "text": f"❌ Patient ID '{patient_id}' not found."}
        else:
            conn.execute(
                "INSERT INTO history (patient_id, date, diagnosis, medication, notes) VALUES (?, ?, ?, ?, ?)",
                (patient_id, hist_date, diagnosis, medication, notes)
            )
            conn.commit()
            message = {"type": "success", "text": f"✅ History added for patient {patient_id}!"}

    patients = conn.execute("SELECT * FROM patients").fetchall()
    conn.close()
    return render_template("add_history.html", message=message, patients=patients)

# ── SEARCH HISTORY ────────────────────────────────────────────────────────────
@app.route("/search_history", methods=["GET", "POST"])
def search_history():
    if "username" not in session:
        return redirect("/login")
    if session["role"] != "doctor":
        return redirect("/dashboard")

    conn      = get_db()
    result    = None
    history   = []
    search_id = ""

    if request.method == "POST":
        search_id = request.form["patient_id"].strip()

        # Recursive search function (same logic, now searches DB result)
        result = conn.execute(
            "SELECT * FROM patients WHERE id = ?", (search_id,)
        ).fetchone()

        if result is None:
            result = {"error": f"❌ Patient ID '{search_id}' not found."}
        else:
            # Get their history from the history table
            history = conn.execute(
                "SELECT * FROM history WHERE patient_id = ? ORDER BY date DESC",
                (search_id,)
            ).fetchall()

    patients = conn.execute("SELECT * FROM patients").fetchall()
    conn.close()
    return render_template("search_history.html",
                           result=result,
                           history=history,
                           search_id=search_id,
                           patients=patients)

# ── LOGOUT ────────────────────────────────────────────────────────────────────
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# ── RUN ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    init_db()       # ← create tables when app first starts
    app.run(debug=True)