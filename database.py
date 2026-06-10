"""
database.py — Teacher Portal
Handles all data storage for student enrollment data collection.
"""

import sqlite3
import os
from datetime import datetime

DB_FILE = os.environ.get("DB_PATH", "teacher_portal.db")


def get_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def setup_database():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sections (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            grade        TEXT NOT NULL,
            section_name TEXT NOT NULL,
            adviser_name TEXT,
            adviser_signature TEXT,
            created_at   TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(grade, section_name)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id                        INTEGER PRIMARY KEY AUTOINCREMENT,
            lrn                       TEXT UNIQUE,
            first_name                TEXT NOT NULL,
            last_name                 TEXT NOT NULL,
            middle_initial            TEXT,
            extension                 TEXT,
            grade                     TEXT,
            section_name              TEXT,
            adviser_name              TEXT,
            emergency_contact_name    TEXT,
            emergency_contact_address TEXT,
            emergency_contact_number  TEXT,
            photo_url                 TEXT,
            id_printed                INTEGER DEFAULT 0,
            id_distributed            INTEGER DEFAULT 0,
            created_at                TEXT DEFAULT (datetime('now','localtime')),
            updated_at                TEXT DEFAULT (datetime('now','localtime'))
        )
    """)

    conn.commit()
    conn.close()
    print("✅ Teacher portal database ready.")


# ── SECTIONS ──────────────────────────────────────────────────────────────────

def add_section(grade, section_name, adviser_name="", adviser_signature=""):
    """
    Add or update a section.
    If section already exists, updates adviser name and signature.
    If new signature is empty, keeps the existing one.
    """
    conn = get_connection()
    try:
        # Check if section already exists
        existing = conn.execute(
            "SELECT id, adviser_signature FROM sections WHERE grade=? AND section_name=?",
            (grade, section_name)
        ).fetchone()

        if existing:
            # Update — keep existing signature if no new one provided
            keep_sig = existing["adviser_signature"] if not adviser_signature else adviser_signature
            conn.execute("""
                UPDATE sections
                SET adviser_name=?, adviser_signature=?
                WHERE grade=? AND section_name=?
            """, (adviser_name, keep_sig, grade, section_name))
        else:
            # Insert new
            conn.execute("""
                INSERT INTO sections (grade, section_name, adviser_name, adviser_signature)
                VALUES (?, ?, ?, ?)
            """, (grade, section_name, adviser_name, adviser_signature))

        conn.commit()
        return True
    except Exception as e:
        print(f"Error adding section: {e}")
        return False
    finally:
        conn.close()


def get_all_sections():
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM sections ORDER BY grade, section_name"
    ).fetchall()
    conn.close()
    return rows


def get_section(grade, section_name):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM sections WHERE grade=? AND section_name=?",
        (grade, section_name)
    ).fetchone()
    conn.close()
    return row


def update_section_adviser(grade, section_name, adviser_name, adviser_signature=""):
    conn = get_connection()
    conn.execute("""
        UPDATE sections SET adviser_name=?, adviser_signature=?
        WHERE grade=? AND section_name=?
    """, (adviser_name, adviser_signature, grade, section_name))
    conn.commit()
    conn.close()


def get_all_grades():
    conn = get_connection()
    rows = conn.execute(
        "SELECT DISTINCT grade FROM sections ORDER BY grade"
    ).fetchall()
    conn.close()
    return [r["grade"] for r in rows]


# ── STUDENTS ──────────────────────────────────────────────────────────────────

def add_student(data):
    """Add a single student. Returns (success, message)."""
    conn = get_connection()
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("""
            INSERT INTO students (
                lrn, first_name, last_name, middle_initial, extension,
                grade, section_name, adviser_name,
                emergency_contact_name, emergency_contact_address,
                emergency_contact_number, photo_url, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            data.get("lrn", "").strip(),
            data.get("first_name", "").strip(),
            data.get("last_name", "").strip(),
            data.get("middle_initial", "").strip(),
            data.get("extension", "").strip(),
            data.get("grade", "").strip(),
            data.get("section_name", "").strip(),
            data.get("adviser_name", "").strip(),
            data.get("emergency_contact_name", "").strip(),
            data.get("emergency_contact_address", "").strip(),
            data.get("emergency_contact_number", "").strip(),
            data.get("photo_url", ""),
            now, now
        ))
        conn.commit()
        return True, "Student added successfully"
    except sqlite3.IntegrityError:
        return False, f"LRN {data.get('lrn')} already exists"
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()


def update_student(student_id, data):
    """Update student details (only if not printed)."""
    conn = get_connection()
    try:
        # Check if printed
        row = conn.execute(
            "SELECT id_printed FROM students WHERE id=?", (student_id,)
        ).fetchone()
        if not row:
            return False, "Student not found"
        if row["id_printed"]:
            return False, "Cannot edit — ID has already been printed"

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("""
            UPDATE students SET
                lrn=?, first_name=?, last_name=?, middle_initial=?, extension=?,
                grade=?, section_name=?, adviser_name=?,
                emergency_contact_name=?, emergency_contact_address=?,
                emergency_contact_number=?, updated_at=?
            WHERE id=?
        """, (
            data.get("lrn", "").strip(),
            data.get("first_name", "").strip(),
            data.get("last_name", "").strip(),
            data.get("middle_initial", "").strip(),
            data.get("extension", "").strip(),
            data.get("grade", "").strip(),
            data.get("section_name", "").strip(),
            data.get("adviser_name", "").strip(),
            data.get("emergency_contact_name", "").strip(),
            data.get("emergency_contact_address", "").strip(),
            data.get("emergency_contact_number", "").strip(),
            now, student_id
        ))
        conn.commit()
        return True, "Student updated"
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()


def update_student_photo(student_id, photo_url):
    conn = get_connection()
    conn.execute(
        "UPDATE students SET photo_url=?, updated_at=? WHERE id=?",
        (photo_url, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), student_id)
    )
    conn.commit()
    conn.close()


def update_id_status(student_id, field, value):
    """Admin only — mark id_printed or id_distributed."""
    if field not in ("id_printed", "id_distributed"):
        return False
    conn = get_connection()
    conn.execute(
        f"UPDATE students SET {field}=? WHERE id=?",
        (1 if value else 0, student_id)
    )
    conn.commit()
    conn.close()
    return True


def get_students(grade=None, section_name=None, search=None):
    conn = get_connection()
    query = "SELECT * FROM students WHERE 1=1"
    params = []
    if grade:
        query += " AND grade=?"
        params.append(grade)
    if section_name:
        query += " AND section_name=?"
        params.append(section_name)
    if search:
        query += " AND (first_name LIKE ? OR last_name LIKE ? OR lrn LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])
    query += " ORDER BY last_name, first_name"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return rows


def get_student_by_id(student_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM students WHERE id=?", (student_id,)).fetchone()
    conn.close()
    return row


def bulk_import_students(students_list):
    """Import a list of student dicts. Returns (added, skipped, errors)."""
    added = 0; skipped = 0; errors = []
    for s in students_list:
        if not s.get("first_name") and not s.get("last_name"):
            continue
        success, msg = add_student(s)
        if success:
            added += 1
        else:
            skipped += 1
            errors.append(f"{s.get('lrn','?')}: {msg}")
    return added, skipped, errors


def get_stats():
    conn = get_connection()
    total   = conn.execute("SELECT COUNT(*) FROM students").fetchone()[0]
    printed = conn.execute("SELECT COUNT(*) FROM students WHERE id_printed=1").fetchone()[0]
    distributed = conn.execute("SELECT COUNT(*) FROM students WHERE id_distributed=1").fetchone()[0]
    with_photo = conn.execute("SELECT COUNT(*) FROM students WHERE photo_url != '' AND photo_url IS NOT NULL").fetchone()[0]
    conn.close()
    return {
        "total": total,
        "printed": printed,
        "distributed": distributed,
        "with_photo": with_photo,
        "pending_print": total - printed,
    }


def export_students_csv(grade=None, section_name=None):
    """Export students as CSV string for download."""
    import csv, io
    students = get_students(grade, section_name)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "lrn", "last_name", "first_name", "middle_initial", "extension",
        "grade", "section_name", "adviser_name",
        "emergency_contact_name", "emergency_contact_address",
        "emergency_contact_number", "photo_url",
        "id_printed", "id_distributed"
    ])
    for s in students:
        writer.writerow([
            s["lrn"], s["last_name"], s["first_name"],
            s["middle_initial"], s["extension"],
            s["grade"], s["section_name"], s["adviser_name"],
            s["emergency_contact_name"], s["emergency_contact_address"],
            s["emergency_contact_number"], s["photo_url"] or "",
            "Yes" if s["id_printed"] else "No",
            "Yes" if s["id_distributed"] else "No",
        ])
    return output.getvalue()


def get_dashboard_stats():
    """Comprehensive stats for the dashboard."""
    conn = get_connection()

    total = conn.execute("SELECT COUNT(*) FROM students").fetchone()[0]
    with_photo = conn.execute(
        "SELECT COUNT(*) FROM students WHERE photo_url != '' AND photo_url IS NOT NULL"
    ).fetchone()[0]
    id_printed = conn.execute(
        "SELECT COUNT(*) FROM students WHERE id_printed=1"
    ).fetchone()[0]
    id_distributed = conn.execute(
        "SELECT COUNT(*) FROM students WHERE id_distributed=1"
    ).fetchone()[0]

    # Complete info = has LRN, first_name, last_name, emergency_contact_number
    complete = conn.execute("""
        SELECT COUNT(*) FROM students
        WHERE lrn != '' AND lrn IS NOT NULL
        AND first_name != '' AND first_name IS NOT NULL
        AND last_name != '' AND last_name IS NOT NULL
        AND emergency_contact_number != '' AND emergency_contact_number IS NOT NULL
    """).fetchone()[0]

    # Per grade breakdown
    grade_stats = conn.execute("""
        SELECT grade,
               COUNT(*) as total,
               SUM(CASE WHEN photo_url != '' AND photo_url IS NOT NULL THEN 1 ELSE 0 END) as with_photo,
               SUM(CASE WHEN id_printed=1 THEN 1 ELSE 0 END) as printed
        FROM students
        GROUP BY grade
        ORDER BY grade
    """).fetchall()

    # Per section breakdown
    section_stats = conn.execute("""
        SELECT grade, section_name,
               COUNT(*) as total,
               SUM(CASE WHEN photo_url != '' AND photo_url IS NOT NULL THEN 1 ELSE 0 END) as with_photo,
               SUM(CASE WHEN id_printed=1 THEN 1 ELSE 0 END) as printed,
               SUM(CASE WHEN lrn != '' AND lrn IS NOT NULL THEN 1 ELSE 0 END) as with_lrn
        FROM students
        GROUP BY grade, section_name
        ORDER BY grade, section_name
    """).fetchall()

    conn.close()
    return {
        "total":            total,
        "with_photo":       with_photo,
        "missing_photo":    total - with_photo,
        "complete":         complete,
        "incomplete":       total - complete,
        "id_printed":       id_printed,
        "id_distributed":   id_distributed,
        "pending_print":    total - id_printed,
        "grade_stats":      [dict(r) for r in grade_stats],
        "section_stats":    [dict(r) for r in section_stats],
    }


def get_section_detail(grade, section_name):
    """Get section info including adviser signature and students."""
    conn = get_connection()

    # Get section info — try exact match first, then case-insensitive
    section = conn.execute(
        "SELECT * FROM sections WHERE grade=? AND section_name=?",
        (grade, section_name)
    ).fetchone()

    if not section:
        section = conn.execute(
            "SELECT * FROM sections WHERE LOWER(grade)=LOWER(?) AND LOWER(section_name)=LOWER(?)",
            (grade, section_name)
        ).fetchone()

    # Get students — match on section name, flexible grade matching
    students = conn.execute("""
        SELECT *,
          CASE WHEN (lrn != '' AND lrn IS NOT NULL
               AND emergency_contact_number != '' AND emergency_contact_number IS NOT NULL
               AND photo_url != '' AND photo_url IS NOT NULL)
          THEN 1 ELSE 0 END as is_complete
        FROM students
        WHERE LOWER(section_name)=LOWER(?)
        AND (LOWER(grade)=LOWER(?) OR grade=? OR ? IS NULL)
        ORDER BY last_name, first_name
    """, (section_name, grade, grade, grade)).fetchall()

    conn.close()
    return section, students


def auto_create_sections_from_students():
    """
    Scan students table and auto-create any sections
    that don't exist yet in the sections table.
    """
    conn = get_connection()
    # Get unique grade+section combos from students
    combos = conn.execute("""
        SELECT DISTINCT grade, section_name, adviser_name
        FROM students
        WHERE grade != '' AND grade IS NOT NULL
        AND section_name != '' AND section_name IS NOT NULL
    """).fetchall()

    for row in combos:
        conn.execute("""
            INSERT OR IGNORE INTO sections (grade, section_name, adviser_name)
            VALUES (?, ?, ?)
        """, (row["grade"], row["section_name"], row["adviser_name"] or ""))

    conn.commit()
    conn.close()
