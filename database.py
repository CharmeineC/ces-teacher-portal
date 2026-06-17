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
            section_pin  TEXT DEFAULT '',
            created_at   TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(grade, section_name)
        )
    """)
    # Add section_pin column to existing databases
    try:
        cursor.execute("ALTER TABLE sections ADD COLUMN section_pin TEXT DEFAULT ''")
    except Exception:
        pass

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id                        INTEGER PRIMARY KEY AUTOINCREMENT,
            lrn                       TEXT,
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
    # Add unique index on (lrn, section_name) — same student can be in multiple sections
    try:
        cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_lrn_section 
            ON students(lrn, section_name) 
            WHERE lrn != '' AND lrn IS NOT NULL
        """)
    except Exception:
        pass

    # Teacher profiles table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS teacher_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            last_name TEXT, first_name TEXT, middle_initial TEXT,
            employee_no TEXT, position TEXT, birth_date TEXT, blood_type TEXT,
            address TEXT, prc_number TEXT, tin TEXT, philhealth TEXT,
            gsis TEXT, hdmf TEXT, advisory_class TEXT, photo_url TEXT,
            ec_name TEXT, ec_number TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        )
    """)
    conn.commit()
    conn.close()
    print("✅ Teacher portal database ready.")


# ── SECTIONS ──────────────────────────────────────────────────────────────────

def add_section(grade, section_name, adviser_name="", adviser_signature="", section_pin=""):
    """
    Add or update a section.
    If section already exists, updates adviser name and signature.
    PIN is only set on creation or explicitly updated.
    """
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT id, adviser_signature, section_pin FROM sections WHERE grade=? AND section_name=?",
            (grade, section_name)
        ).fetchone()

        if existing:
            keep_sig = existing["adviser_signature"] if not adviser_signature else adviser_signature
            # Only update PIN if a new one was provided
            keep_pin = existing["section_pin"] if not section_pin else section_pin
            conn.execute("""
                UPDATE sections
                SET adviser_name=?, adviser_signature=?, section_pin=?
                WHERE grade=? AND section_name=?
            """, (adviser_name, keep_sig, keep_pin, grade, section_name))
        else:
            conn.execute("""
                INSERT INTO sections (grade, section_name, adviser_name, adviser_signature, section_pin)
                VALUES (?, ?, ?, ?, ?)
            """, (grade, section_name, adviser_name, adviser_signature, section_pin))

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
    """
    Import a list of student dicts.
    - If LRN exists → UPDATE student info (handles transfers to new section)
    - If LRN not found → INSERT new student
    - Returns (added, updated, errors)
    """
    added = 0; updated = 0; errors = []
    for s in students_list:
        if not s.get("first_name") and not s.get("last_name"):
            continue

        lrn = str(s.get("lrn") or "").strip()
        conn = get_connection()
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            section = s.get("section_name","").strip()

            if lrn:
                # Check if student with this EXACT LRN + section combo exists
                existing = conn.execute(
                    "SELECT id FROM students WHERE lrn=? AND LOWER(section_name)=LOWER(?)",
                    (lrn, section)
                ).fetchone()
            else:
                existing = None

            if existing:
                # UPDATE info for this student in this section
                conn.execute("""
                    UPDATE students SET
                        first_name=?, last_name=?, middle_initial=?,
                        extension=?, adviser_name=?,
                        emergency_contact_name=?, emergency_contact_address=?,
                        emergency_contact_number=?, updated_at=?
                    WHERE lrn=? AND LOWER(section_name)=LOWER(?)
                """, (
                    s.get("first_name","").strip(),
                    s.get("last_name","").strip(),
                    s.get("middle_initial","").strip(),
                    s.get("extension","").strip(),
                    s.get("adviser_name","").strip(),
                    s.get("emergency_contact_name","").strip(),
                    s.get("emergency_contact_address","").strip(),
                    s.get("emergency_contact_number","").strip(),
                    now, lrn, section
                ))
                conn.commit()
                updated += 1
            else:
                # INSERT new student
                conn.execute("""
                    INSERT INTO students (
                        lrn, first_name, last_name, middle_initial, extension,
                        grade, section_name, adviser_name,
                        emergency_contact_name, emergency_contact_address,
                        emergency_contact_number, created_at, updated_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    lrn,
                    s.get("first_name","").strip(),
                    s.get("last_name","").strip(),
                    s.get("middle_initial","").strip(),
                    s.get("extension","").strip(),
                    s.get("grade","").strip(),
                    s.get("section_name","").strip(),
                    s.get("adviser_name","").strip(),
                    s.get("emergency_contact_name","").strip(),
                    s.get("emergency_contact_address","").strip(),
                    s.get("emergency_contact_number","").strip(),
                    now, now
                ))
                conn.commit()
                added += 1
        except Exception as e:
            errors.append(f"{lrn or 'unknown'}: {str(e)}")
        finally:
            conn.close()

    return added, updated, errors


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
    """
    Export students as CSV — includes section PIN and adviser signature URL
    so everything can be fully restored from this one file.
    """
    import csv, io
    conn = get_connection()

    # JOIN students with sections to get PIN and signature
    query = """
        SELECT
            st.lrn, st.last_name, st.first_name, st.middle_initial, st.extension,
            st.grade, st.section_name, st.adviser_name,
            st.emergency_contact_name, st.emergency_contact_address,
            st.emergency_contact_number, st.photo_url,
            st.id_printed, st.id_distributed,
            COALESCE(sec.adviser_signature, '') as adviser_signature,
            COALESCE(sec.section_pin, '')       as section_pin
        FROM students st
        LEFT JOIN sections sec
            ON LOWER(sec.grade)=LOWER(st.grade)
            AND LOWER(sec.section_name)=LOWER(st.section_name)
        WHERE 1=1
    """
    params = []
    if grade:
        query += " AND st.grade=?"; params.append(grade)
    if section_name:
        query += " AND st.section_name=?"; params.append(section_name)
    query += " ORDER BY st.grade, st.section_name, st.last_name, st.first_name"

    students = conn.execute(query, params).fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "lrn", "last_name", "first_name", "middle_initial", "extension",
        "grade", "section_name", "adviser_name",
        "emergency_contact_name", "emergency_contact_address",
        "emergency_contact_number", "photo_url",
        "id_printed", "id_distributed",
        "adviser_signature", "section_pin"
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
            s["adviser_signature"] or "",
            s["section_pin"] or "",
        ])
    return output.getvalue()


def get_dashboard_stats():
    """Comprehensive stats for the dashboard — JOINs sections table for correct adviser/signature."""
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

    # Per section breakdown — LEFT JOIN sections to get adviser/signature
    section_stats = conn.execute("""
        SELECT 
            st.grade, 
            st.section_name,
            COUNT(*) as total,
            SUM(CASE WHEN st.photo_url != '' AND st.photo_url IS NOT NULL THEN 1 ELSE 0 END) as with_photo,
            SUM(CASE WHEN st.id_printed=1 THEN 1 ELSE 0 END) as printed,
            SUM(CASE WHEN st.lrn != '' AND st.lrn IS NOT NULL THEN 1 ELSE 0 END) as with_lrn,
            COALESCE(sec.adviser_name, st.adviser_name, '') as adviser_name,
            COALESCE(sec.adviser_signature, '') as adviser_signature
        FROM students st
        LEFT JOIN sections sec 
            ON LOWER(sec.grade) = LOWER(st.grade) 
            AND LOWER(sec.section_name) = LOWER(st.section_name)
        GROUP BY st.grade, st.section_name
        ORDER BY st.grade, st.section_name
    """).fetchall()

    # Also include sections that have no students yet
    empty_sections = conn.execute("""
        SELECT 
            sec.grade,
            sec.section_name,
            0 as total,
            0 as with_photo,
            0 as printed,
            0 as with_lrn,
            sec.adviser_name,
            COALESCE(sec.adviser_signature, '') as adviser_signature
        FROM sections sec
        WHERE NOT EXISTS (
            SELECT 1 FROM students st 
            WHERE LOWER(st.grade)=LOWER(sec.grade) 
            AND LOWER(st.section_name)=LOWER(sec.section_name)
        )
        ORDER BY sec.grade, sec.section_name
    """).fetchall()

    all_sections = [dict(r) for r in section_stats] + [dict(r) for r in empty_sections]
    all_sections.sort(key=lambda x: (x['grade'], x['section_name']))

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
        "section_stats":    all_sections,
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


def delete_section(grade, section_name):
    """Delete a section and all its students."""
    conn = get_connection()
    try:
        # Delete students first
        conn.execute(
            "DELETE FROM students WHERE LOWER(grade)=LOWER(?) AND LOWER(section_name)=LOWER(?)",
            (grade, section_name)
        )
        # Delete section
        conn.execute(
            "DELETE FROM sections WHERE LOWER(grade)=LOWER(?) AND LOWER(section_name)=LOWER(?)",
            (grade, section_name)
        )
        conn.commit()
        return True
    except Exception as e:
        print(f"Error deleting section: {e}")
        return False
    finally:
        conn.close()


def delete_student(student_id):
    """Delete a single student."""
    conn = get_connection()
    try:
        conn.execute("DELETE FROM students WHERE id=?", (student_id,))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error deleting student: {e}")
        return False
    finally:
        conn.close()


def get_students_filtered(filter_type=None, grade=None, section_name=None):
    """Get students by filter type for dashboard stat cards."""
    conn = get_connection()
    query = "SELECT * FROM students WHERE 1=1"
    params = []

    if filter_type == "missing_photo":
        query += " AND (photo_url IS NULL OR photo_url = '')"
    elif filter_type == "with_photo":
        query += " AND photo_url IS NOT NULL AND photo_url != ''"
    elif filter_type == "id_printed":
        query += " AND id_printed = 1"
    elif filter_type == "id_distributed":
        query += " AND id_distributed = 1"
    elif filter_type == "incomplete":
        query += """ AND (
            lrn IS NULL OR lrn = '' OR
            emergency_contact_number IS NULL OR emergency_contact_number = '' OR
            photo_url IS NULL OR photo_url = ''
        )"""
    elif filter_type == "complete":
        query += """ AND lrn != '' AND lrn IS NOT NULL
            AND emergency_contact_number != '' AND emergency_contact_number IS NOT NULL
            AND photo_url != '' AND photo_url IS NOT NULL"""

    if grade:
        query += " AND grade = ?"
        params.append(grade)
    if section_name:
        query += " AND section_name = ?"
        params.append(section_name)

    query += " ORDER BY grade, section_name, last_name, first_name"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return rows


def verify_section_pin(grade, section_name, pin_input):
    """Verify the PIN for a section. Returns (valid, message)."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT section_pin FROM sections WHERE LOWER(grade)=LOWER(?) AND LOWER(section_name)=LOWER(?)",
            (grade, section_name)
        ).fetchone()
        if not row:
            return False, "Section not found"
        stored_pin = row["section_pin"] or ""
        if not stored_pin:
            return False, "This section has no PIN set. Only admin can delete."
        if str(pin_input).strip() == str(stored_pin).strip():
            return True, "PIN correct"
        return False, "Incorrect PIN"
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()


# ── TEACHER PROFILES ──────────────────────────────────────────────────────────

def setup_teacher_profiles():
    """Create teacher_profiles table if it doesn't exist."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS teacher_profiles (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            last_name       TEXT,
            first_name      TEXT,
            middle_initial  TEXT,
            employee_no     TEXT,
            position        TEXT,
            birth_date      TEXT,
            blood_type      TEXT,
            address         TEXT,
            prc_number      TEXT,
            tin             TEXT,
            philhealth      TEXT,
            gsis            TEXT,
            hdmf            TEXT,
            advisory_class  TEXT,
            photo_url       TEXT,
            ec_name         TEXT,
            ec_number       TEXT,
            created_at      TEXT DEFAULT (datetime('now','localtime')),
            updated_at      TEXT DEFAULT (datetime('now','localtime'))
        )
    """)
    conn.commit()
    conn.close()


def get_all_teachers(search=None):
    conn = get_connection()
    query = "SELECT * FROM teacher_profiles WHERE 1=1"
    params = []
    if search:
        query += " AND (first_name LIKE ? OR last_name LIKE ? OR employee_no LIKE ? OR position LIKE ?)"
        params.extend([f"%{search}%"]*4)
    query += " ORDER BY last_name, first_name"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return rows


def get_teacher_by_id(teacher_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM teacher_profiles WHERE id=?", (teacher_id,)).fetchone()
    conn.close()
    return row


def get_teacher_by_employee_no(employee_no):
    conn = get_connection()
    row = conn.execute("SELECT * FROM teacher_profiles WHERE employee_no=?", (employee_no,)).fetchone()
    conn.close()
    return row


def add_teacher(data):
    """Add or update teacher by employee_no."""
    conn = get_connection()
    try:
        now = __import__('datetime').datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        emp = str(data.get("employee_no","")).strip()

        existing = None
        if emp:
            existing = conn.execute(
                "SELECT id FROM teacher_profiles WHERE employee_no=?", (emp,)
            ).fetchone()

        if existing:
            conn.execute("""
                UPDATE teacher_profiles SET
                    last_name=?, first_name=?, middle_initial=?, employee_no=?,
                    position=?, birth_date=?, blood_type=?, address=?,
                    prc_number=?, tin=?, philhealth=?, gsis=?, hdmf=?,
                    advisory_class=?, ec_name=?, ec_number=?, updated_at=?
                WHERE id=?
            """, (
                data.get("last_name","").strip(), data.get("first_name","").strip(),
                data.get("middle_initial","").strip(), emp,
                data.get("position","").strip(), data.get("birth_date","").strip(),
                data.get("blood_type","").strip(), data.get("address","").strip(),
                data.get("prc_number","").strip(), data.get("tin","").strip(),
                data.get("philhealth","").strip(), data.get("gsis","").strip(),
                data.get("hdmf","").strip(), data.get("advisory_class","").strip(),
                data.get("ec_name","").strip(), data.get("ec_number","").strip(),
                now, existing["id"]
            ))
            conn.commit()
            return True, "updated", existing["id"]
        else:
            cur = conn.execute("""
                INSERT INTO teacher_profiles (
                    last_name, first_name, middle_initial, employee_no,
                    position, birth_date, blood_type, address,
                    prc_number, tin, philhealth, gsis, hdmf,
                    advisory_class, ec_name, ec_number,
                    created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                data.get("last_name","").strip(), data.get("first_name","").strip(),
                data.get("middle_initial","").strip(), emp,
                data.get("position","").strip(), data.get("birth_date","").strip(),
                data.get("blood_type","").strip(), data.get("address","").strip(),
                data.get("prc_number","").strip(), data.get("tin","").strip(),
                data.get("philhealth","").strip(), data.get("gsis","").strip(),
                data.get("hdmf","").strip(), data.get("advisory_class","").strip(),
                data.get("ec_name","").strip(), data.get("ec_number","").strip(),
                now, now
            ))
            conn.commit()
            return True, "added", cur.lastrowid
    except Exception as e:
        print(f"add_teacher error: {e}")
        return False, str(e), None
    finally:
        conn.close()


def update_teacher_photo(teacher_id, photo_url):
    conn = get_connection()
    conn.execute("UPDATE teacher_profiles SET photo_url=? WHERE id=?", (photo_url, teacher_id))
    conn.commit()
    conn.close()


def delete_teacher(teacher_id):
    conn = get_connection()
    conn.execute("DELETE FROM teacher_profiles WHERE id=?", (teacher_id,))
    conn.commit()
    conn.close()


def bulk_import_teachers(rows):
    """Import list of teacher dicts. Returns (added, updated, errors)."""
    added = 0; updated = 0; errors = []
    for r in rows:
        ok, status, _ = add_teacher(r)
        if ok:
            if status == "added": added += 1
            else: updated += 1
        else:
            errors.append(f"{r.get('last_name','?')}: {status}")
    return added, updated, errors


def export_teachers_csv():
    import csv, io
    conn = get_connection()
    rows = conn.execute("SELECT * FROM teacher_profiles ORDER BY last_name, first_name").fetchall()
    conn.close()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "last_name","first_name","middle_initial","employee_no","position",
        "birth_date","blood_type","address","prc_number","tin",
        "philhealth","gsis","hdmf","advisory_class","photo_url",
        "ec_name","ec_number"
    ])
    for r in rows:
        writer.writerow([
            r["last_name"] or "", r["first_name"] or "", r["middle_initial"] or "",
            r["employee_no"] or "", r["position"] or "",
            r["birth_date"] or "", r["blood_type"] or "", r["address"] or "",
            r["prc_number"] or "", r["tin"] or "",
            r["philhealth"] or "", r["gsis"] or "", r["hdmf"] or "",
            r["advisory_class"] or "", r["photo_url"] or "",
            r["ec_name"] or "", r["ec_number"] or ""
        ])
    return output.getvalue()
