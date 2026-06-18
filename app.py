"""
MediTrack — Hospital Equipment & Inventory Management System
Capstone project: Python Flask + MySQL (RDS) + Gunicorn + Nginx + EC2

All database credentials are read from environment variables (see .env.example).
Never hardcode credentials here.
"""

import os
from datetime import date

import pymysql
from pymysql.cursors import DictCursor
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-me")

DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "localhost"),
    "user": os.environ.get("DB_USER", "root"),
    "password": os.environ.get("DB_PASSWORD", ""),
    "database": os.environ.get("DB_NAME", "meditrack"),
    "port": int(os.environ.get("DB_PORT", 3306)),
    "cursorclass": DictCursor,
    "autocommit": False,
}

VALID_STATUSES = ["Active", "Under Maintenance", "Decommissioned"]


def get_db_connection():
    """Open a fresh connection for the current request."""
    return pymysql.connect(**DB_CONFIG)


def init_db():
    """
    Create the equipment and maintenance_log tables if they do not already
    exist. Safe to call on every app startup. Equivalent SQL also lives in
    deployment/schema.sql if you prefer to run it manually via the MySQL CLI.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS equipment (
                    equipment_id   INT AUTO_INCREMENT PRIMARY KEY,
                    equipment_name VARCHAR(100) NOT NULL,
                    serial_number  VARCHAR(50)  NOT NULL UNIQUE,
                    department     VARCHAR(100) NOT NULL,
                    purchase_date  DATE NOT NULL,
                    status         ENUM('Active','Under Maintenance','Decommissioned')
                                   NOT NULL DEFAULT 'Active'
                ) ENGINE=InnoDB
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS maintenance_log (
                    log_id            INT AUTO_INCREMENT PRIMARY KEY,
                    equipment_id      INT NOT NULL,
                    maintenance_date  DATE NOT NULL,
                    technician_name   VARCHAR(100) NOT NULL,
                    issue_reported    TEXT,
                    resolution_notes  TEXT,
                    next_due_date     DATE,
                    CONSTRAINT fk_maintenance_equipment
                        FOREIGN KEY (equipment_id) REFERENCES equipment(equipment_id)
                        ON DELETE CASCADE
                ) ENGINE=InnoDB
                """
            )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def home():
    return redirect(url_for("dashboard"))


@app.route("/dashboard")
def dashboard():
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS total FROM equipment")
            total = cur.fetchone()["total"]

            cur.execute("SELECT status, COUNT(*) AS count FROM equipment GROUP BY status")
            status_counts = cur.fetchall()

            # An item is "overdue" when its most recent logged next_due_date
            # has already passed.
            cur.execute(
                """
                SELECT e.equipment_id, e.equipment_name, e.serial_number,
                       e.department, m.next_due_date
                FROM equipment e
                JOIN (
                    SELECT equipment_id, MAX(next_due_date) AS next_due_date
                    FROM maintenance_log
                    WHERE next_due_date IS NOT NULL
                    GROUP BY equipment_id
                ) m ON m.equipment_id = e.equipment_id
                WHERE m.next_due_date < CURDATE()
                ORDER BY m.next_due_date ASC
                """
            )
            overdue = cur.fetchall()
    finally:
        conn.close()

    return render_template(
        "dashboard.html",
        total=total,
        status_counts=status_counts,
        overdue=overdue,
    )


@app.route("/equipment")
def equipment_list():
    department = request.args.get("department", "").strip()
    status = request.args.get("status", "").strip()

    query = "SELECT * FROM equipment WHERE 1=1"
    params = []
    if department:
        query += " AND department = %s"
        params.append(department)
    if status:
        query += " AND status = %s"
        params.append(status)
    query += " ORDER BY equipment_name"

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(query, params)
            equipment = cur.fetchall()

            cur.execute("SELECT DISTINCT department FROM equipment ORDER BY department")
            departments = [row["department"] for row in cur.fetchall()]
    finally:
        conn.close()

    return render_template(
        "index.html",
        equipment=equipment,
        departments=departments,
        statuses=VALID_STATUSES,
        selected_department=department,
        selected_status=status,
    )


@app.route("/equipment/add", methods=["GET", "POST"])
def add_equipment():
    if request.method == "POST":
        equipment_name = request.form["equipment_name"].strip()
        serial_number = request.form["serial_number"].strip()
        department = request.form["department"].strip()
        purchase_date = request.form["purchase_date"]
        status = request.form.get("status", "Active")

        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO equipment
                        (equipment_name, serial_number, department, purchase_date, status)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (equipment_name, serial_number, department, purchase_date, status),
                )
            conn.commit()
            flash(f"Equipment '{equipment_name}' added successfully.", "success")
            return redirect(url_for("equipment_list"))
        except pymysql.err.IntegrityError:
            conn.rollback()
            flash(f"Serial number '{serial_number}' is already in use.", "error")
        finally:
            conn.close()

    return render_template("add_equipment.html", statuses=VALID_STATUSES)


@app.route("/equipment/<int:equipment_id>")
def equipment_detail(equipment_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM equipment WHERE equipment_id = %s", (equipment_id,))
            equipment = cur.fetchone()

            if not equipment:
                flash("That equipment record could not be found.", "error")
                return redirect(url_for("equipment_list"))

            cur.execute(
                "SELECT * FROM maintenance_log WHERE equipment_id = %s ORDER BY maintenance_date DESC",
                (equipment_id,),
            )
            logs = cur.fetchall()
    finally:
        conn.close()

    return render_template(
        "equipment_detail.html",
        equipment=equipment,
        logs=logs,
        today=date.today(),
    )


@app.route("/equipment/<int:equipment_id>/edit", methods=["GET", "POST"])
def edit_equipment(equipment_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM equipment WHERE equipment_id = %s", (equipment_id,))
            equipment = cur.fetchone()

        if not equipment:
            flash("That equipment record could not be found.", "error")
            return redirect(url_for("equipment_list"))

        if request.method == "POST":
            equipment_name = request.form["equipment_name"].strip()
            department = request.form["department"].strip()
            status = request.form["status"]

            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE equipment
                    SET equipment_name = %s, department = %s, status = %s
                    WHERE equipment_id = %s
                    """,
                    (equipment_name, department, status, equipment_id),
                )
            conn.commit()
            flash("Equipment record updated.", "success")
            return redirect(url_for("equipment_detail", equipment_id=equipment_id))
    finally:
        conn.close()

    return render_template("edit_equipment.html", equipment=equipment, statuses=VALID_STATUSES)


@app.route("/equipment/<int:equipment_id>/maintenance/add", methods=["GET", "POST"])
def add_maintenance(equipment_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM equipment WHERE equipment_id = %s", (equipment_id,))
            equipment = cur.fetchone()

        if not equipment:
            flash("That equipment record could not be found.", "error")
            return redirect(url_for("equipment_list"))

        if request.method == "POST":
            maintenance_date = request.form["maintenance_date"]
            technician_name = request.form["technician_name"].strip()
            issue_reported = request.form.get("issue_reported", "").strip()
            resolution_notes = request.form.get("resolution_notes", "").strip()
            next_due_date = request.form.get("next_due_date") or None

            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO maintenance_log
                        (equipment_id, maintenance_date, technician_name,
                         issue_reported, resolution_notes, next_due_date)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        equipment_id,
                        maintenance_date,
                        technician_name,
                        issue_reported,
                        resolution_notes,
                        next_due_date,
                    ),
                )
            conn.commit()
            flash("Maintenance log entry added.", "success")
            return redirect(url_for("equipment_detail", equipment_id=equipment_id))
    finally:
        conn.close()

    return render_template("add_maintenance.html", equipment=equipment)


@app.route("/api/overdue")
def api_overdue():
    """
    Stretch goal: returns overdue maintenance items as JSON so a separate
    alerting service could consume this feed.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT e.equipment_id, e.equipment_name, e.serial_number,
                       e.department, m.next_due_date
                FROM equipment e
                JOIN (
                    SELECT equipment_id, MAX(next_due_date) AS next_due_date
                    FROM maintenance_log
                    WHERE next_due_date IS NOT NULL
                    GROUP BY equipment_id
                ) m ON m.equipment_id = e.equipment_id
                WHERE m.next_due_date < CURDATE()
                ORDER BY m.next_due_date ASC
                """
            )
            overdue = cur.fetchall()
    finally:
        conn.close()

    for row in overdue:
        row["next_due_date"] = row["next_due_date"].isoformat()

    return jsonify(overdue)


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=os.environ.get("FLASK_DEBUG", "False") == "True")
