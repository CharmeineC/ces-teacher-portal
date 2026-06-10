"""
app.py — Teacher Portal
Separate website for teachers to submit student enrollment data.
Hosted on Railway.app for free public access.

Admin credentials: admin / CES@2026
"""

from flask import (
    Flask, render_template, request, jsonify,
    redirect, url_for, session, Response
)
from werkzeug.utils import secure_filename
import os, csv, io, base64
from database import (
    setup_database, add_section, get_all_sections, get_section,
    update_section_adviser, get_all_grades, add_student, update_student,
    update_student_photo, update_id_status, get_students,
    get_student_by_id, bulk_import_students, get_stats,
    export_students_csv
)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "teacher_portal_ces_2026")

# Initialize database on startup
setup_database()

# ── Config ────────────────────────────────────────────────────────────────────
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "CES@2026")
SCHOOL_NAME    = os.environ.get("SCHOOL_NAME", "Communal Elementary School")

# For photo uploads — use local storage (Railway persistent disk)
# or set CLOUDINARY_URL env var to use Cloudinary
UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", "static/uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5MB


def allowed_image(filename):
    return "." in filename and \
           filename.rsplit(".", 1)[1].lower() in {"jpg", "jpeg", "png", "gif", "webp"}


def upload_photo(file):
    """Save photo and return URL. Uses Cloudinary if configured, else local."""
    cloudinary_url = os.environ.get("CLOUDINARY_URL")
    if cloudinary_url:
        try:
            import cloudinary
            import cloudinary.uploader
            result = cloudinary.uploader.upload(file, folder="teacher_portal")
            return result.get("secure_url", "")
        except Exception as e:
            print(f"Cloudinary error: {e}")

    # Local storage fallback
    if file and file.filename:
        filename = secure_filename(file.filename)
        import time
        filename = f"{int(time.time())}_{filename}"
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)
        return f"/static/uploads/{filename}"
    return ""


def is_admin():
    return session.get("admin_logged_in") is True


# ── PUBLIC ROUTES ─────────────────────────────────────────────────────────────

@app.route("/")
def index():
    """Main teacher portal page."""
    grade   = request.args.get("grade", "")
    section = request.args.get("section", "")
    search  = request.args.get("search", "")
    students = get_students(grade or None, section or None, search or None)
    sections = get_all_sections()
    grades   = get_all_grades()
    from database import get_dashboard_stats
    stats    = get_dashboard_stats()
    return render_template("index.html",
                           students=students,
                           sections=sections,
                           grades=grades,
                           stats=stats,
                           school_name=SCHOOL_NAME,
                           selected_grade=grade,
                           selected_section=section,
                           search=search,
                           is_admin=is_admin())


@app.route("/add_section", methods=["POST"])
def route_add_section():
    grade        = request.form.get("grade", "").strip()
    section_name = request.form.get("section_name", "").strip()
    adviser_name = request.form.get("adviser_name", "").strip()

    # Handle signature upload
    sig_url = ""
    if "signature" in request.files:
        sig_file = request.files["signature"]
        if sig_file and sig_file.filename and allowed_image(sig_file.filename):
            sig_url = upload_photo(sig_file)

    if grade and section_name:
        add_section(grade, section_name, adviser_name, sig_url)

        # Handle optional CSV upload
        if "csv_file" in request.files:
            csv_file = request.files["csv_file"]
            if csv_file and csv_file.filename and csv_file.filename.endswith(".csv"):
                try:
                    import io, csv as csv_mod
                    stream  = io.StringIO(csv_file.stream.read().decode("utf-8-sig"))
                    reader  = csv_mod.DictReader(stream)
                    students = []
                    for row in reader:
                        s = {
                            "lrn":           str(row.get("lrn") or row.get("LRN") or "").strip(),
                            "first_name":    str(row.get("first_name") or row.get("First Name") or "").strip(),
                            "last_name":     str(row.get("last_name") or row.get("Last Name") or "").strip(),
                            "middle_initial":str(row.get("middle_initial") or row.get("MI") or "").strip(),
                            "extension":     str(row.get("extension") or row.get("Extension") or "").strip(),
                            "grade":         str(row.get("grade") or row.get("Grade") or grade).strip(),
                            "section_name":  str(row.get("section_name") or row.get("Section") or section_name).strip(),
                            "adviser_name":  str(row.get("adviser_name") or row.get("Adviser") or adviser_name).strip(),
                            "emergency_contact_name":    str(row.get("emergency_contact_name") or "").strip(),
                            "emergency_contact_address": str(row.get("emergency_contact_address") or "").strip(),
                            "emergency_contact_number":  str(row.get("emergency_contact_number") or "").strip(),
                        }
                        if s["first_name"] or s["last_name"]:
                            students.append(s)
                    added, skipped, errors = bulk_import_students(students)
                    from database import auto_create_sections_from_students
                    auto_create_sections_from_students()
                except Exception as e:
                    print(f"CSV import error: {e}")

    return redirect(url_for("section_detail", grade=grade, section_name=section_name))


@app.route("/add_student", methods=["POST"])
def route_add_student():
    grade   = request.form.get("grade", "")
    section = request.form.get("section_name", "")

    data = {
        "lrn":                       request.form.get("lrn", "").strip(),
        "first_name":                request.form.get("first_name", "").strip(),
        "last_name":                 request.form.get("last_name", "").strip(),
        "middle_initial":            request.form.get("middle_initial", "").strip(),
        "extension":                 request.form.get("extension", "").strip(),
        "grade":                     grade,
        "section_name":              section,
        "adviser_name":              request.form.get("adviser_name", "").strip(),
        "emergency_contact_name":    request.form.get("emergency_contact_name", "").strip(),
        "emergency_contact_address": request.form.get("emergency_contact_address", "").strip(),
        "emergency_contact_number":  request.form.get("emergency_contact_number", "").strip(),
    }

    # Handle photo
    if "photo" in request.files:
        photo_file = request.files["photo"]
        if photo_file and photo_file.filename and allowed_image(photo_file.filename):
            data["photo_url"] = upload_photo(photo_file)

    success, msg = add_student(data)
    return redirect(url_for("index", grade=grade, section=section,
                            msg=msg, success="1" if success else "0"))


@app.route("/edit_student/<int:student_id>", methods=["POST"])
def route_edit_student(student_id):
    student = get_student_by_id(student_id)
    if not student:
        return redirect(url_for("index"))

    data = {
        "lrn":                       request.form.get("lrn", "").strip(),
        "first_name":                request.form.get("first_name", "").strip(),
        "last_name":                 request.form.get("last_name", "").strip(),
        "middle_initial":            request.form.get("middle_initial", "").strip(),
        "extension":                 request.form.get("extension", "").strip(),
        "grade":                     request.form.get("grade", "").strip(),
        "section_name":              request.form.get("section_name", "").strip(),
        "adviser_name":              request.form.get("adviser_name", "").strip(),
        "emergency_contact_name":    request.form.get("emergency_contact_name", "").strip(),
        "emergency_contact_address": request.form.get("emergency_contact_address", "").strip(),
        "emergency_contact_number":  request.form.get("emergency_contact_number", "").strip(),
    }

    success, msg = update_student(student_id, data)

    # Handle new photo
    if success and "photo" in request.files:
        photo_file = request.files["photo"]
        if photo_file and photo_file.filename and allowed_image(photo_file.filename):
            photo_url = upload_photo(photo_file)
            update_student_photo(student_id, photo_url)

    return redirect(url_for("index",
                            grade=data["grade"],
                            section=data["section_name"],
                            msg=msg,
                            success="1" if success else "0"))


@app.route("/upload_photo/<int:student_id>", methods=["POST"])
def route_upload_photo(student_id):
    """Upload or update a student's photo."""
    student = get_student_by_id(student_id)
    if not student:
        return jsonify({"success": False, "message": "Student not found"})

    if "photo" not in request.files:
        return jsonify({"success": False, "message": "No file provided"})

    photo_file = request.files["photo"]
    if not photo_file or not photo_file.filename:
        return jsonify({"success": False, "message": "No file selected"})

    if not allowed_image(photo_file.filename):
        return jsonify({"success": False, "message": "Invalid file type"})

    photo_url = upload_photo(photo_file)
    update_student_photo(student_id, photo_url)
    return jsonify({"success": True, "photo_url": photo_url})


@app.route("/bulk_import", methods=["POST"])
def route_bulk_import():
    """Import students from CSV file."""
    grade   = request.form.get("grade", "")
    section = request.form.get("section_name", "")
    adviser = request.form.get("adviser_name", "")

    if "file" not in request.files:
        return redirect(url_for("index", msg="No file selected", success="0"))

    file = request.files["file"]
    if not file or not file.filename:
        return redirect(url_for("index", msg="No file selected", success="0"))

    # Parse CSV
    try:
        stream    = io.StringIO(file.stream.read().decode("utf-8-sig"))
        reader    = csv.DictReader(stream)
        students  = []
        for row in reader:
            # Flexible column matching
            s = {
                "lrn":           str(row.get("lrn") or row.get("LRN") or "").strip(),
                "first_name":    str(row.get("first_name") or row.get("First Name") or row.get("FIRST NAME") or "").strip(),
                "last_name":     str(row.get("last_name") or row.get("Last Name") or row.get("LAST NAME") or "").strip(),
                "middle_initial":str(row.get("middle_initial") or row.get("MI") or row.get("Middle Initial") or "").strip(),
                "extension":     str(row.get("extension") or row.get("Extension") or row.get("EXT") or "").strip(),
                "grade":         str(row.get("grade") or row.get("Grade") or grade).strip(),
                "section_name":  str(row.get("section") or row.get("Section") or row.get("section_name") or section).strip(),
                "adviser_name":  str(row.get("adviser") or row.get("Adviser") or row.get("adviser_name") or adviser).strip(),
                "emergency_contact_name":    str(row.get("emergency_contact_name") or row.get("Emergency Contact") or "").strip(),
                "emergency_contact_address": str(row.get("emergency_contact_address") or row.get("Address") or "").strip(),
                "emergency_contact_number":  str(row.get("emergency_contact_number") or row.get("Contact Number") or "").strip(),
            }
            if s["first_name"] or s["last_name"]:
                students.append(s)

        added, skipped, errors = bulk_import_students(students)
        # Auto-create any new sections found in the CSV
        from database import auto_create_sections_from_students
        auto_create_sections_from_students()
        msg = f"Imported {added} students. Skipped {skipped}."
        if errors:
            msg += f" Errors: {'; '.join(errors[:3])}"
        return redirect(url_for("index", grade=grade, section=section,
                                msg=msg, success="1"))
    except Exception as e:
        return redirect(url_for("index", msg=f"Import error: {str(e)}", success="0"))


@app.route("/download_csv")
def route_download_csv():
    """Download student data as CSV for import into attendance system."""
    grade   = request.args.get("grade", "") or None
    section = request.args.get("section", "") or None
    csv_data = export_students_csv(grade, section)
    filename = f"students_{grade or 'all'}_{section or 'all'}.csv"
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# ── ADMIN ROUTES ──────────────────────────────────────────────────────────────

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session["admin_logged_in"] = True
            return redirect(url_for("index"))
        return render_template("admin_login.html",
                               error="Invalid username or password",
                               school_name=SCHOOL_NAME)
    return render_template("admin_login.html", school_name=SCHOOL_NAME)


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    return redirect(url_for("index"))


@app.route("/admin/update_status/<int:student_id>", methods=["POST"])
def admin_update_status(student_id):
    if not is_admin():
        return jsonify({"success": False, "message": "Not authorized"})
    field = request.form.get("field")
    value = request.form.get("value") == "1"
    success = update_id_status(student_id, field, value)
    return jsonify({"success": success})


@app.route("/api/student/<int:student_id>")
def api_student(student_id):
    """Return student data as JSON for edit modal."""
    student = get_student_by_id(student_id)
    if not student:
        return jsonify({"error": "Not found"})
    return jsonify(dict(student))


@app.route("/api/stats")
def api_stats():
    return jsonify(get_stats())



@app.route("/section/<grade>/<section_name>")
def section_detail(grade, section_name):
    """Section detail page — shows adviser info, signature, and all students."""
    from database import get_section_detail, get_dashboard_stats
    section, students = get_section_detail(grade, section_name)
    stats = get_dashboard_stats()
    sections = get_all_sections()
    grades = get_all_grades()
    return render_template("section_detail.html",
                           section=section,
                           students=students,
                           school_name=SCHOOL_NAME,
                           stats=stats,
                           sections=sections,
                           grades=grades,
                           is_admin=is_admin())


@app.route("/download_photo/<int:student_id>")
def download_photo(student_id):
    """Download a single student photo with proper filename."""
    import requests as req
    student = get_student_by_id(student_id)
    if not student or not student["photo_url"]:
        return "No photo found", 404

    # Build clean filename
    last  = (student["last_name"] or "").upper().replace(" ", "")
    first = (student["first_name"] or "").upper().replace(" ", "")
    grade = (student["grade"] or "").upper().replace(" ", "")
    sec   = (student["section_name"] or "").upper().replace(" ", "")
    ext   = student["photo_url"].split(".")[-1].lower()
    if ext not in ["jpg","jpeg","png","gif","webp"]:
        ext = "jpg"
    filename = f"{last}_{first}_{grade}_{sec}.{ext}"

    photo_url = student["photo_url"]

    # If it's a local file
    if photo_url.startswith("/static/"):
        filepath = os.path.join(os.getcwd(), photo_url.lstrip("/"))
        if os.path.exists(filepath):
            from flask import send_file
            return send_file(filepath, as_attachment=True, download_name=filename)

    # If it's a remote URL (Cloudinary etc.)
    try:
        resp = req.get(photo_url, timeout=10)
        if resp.status_code == 200:
            from flask import Response
            return Response(
                resp.content,
                mimetype=resp.headers.get("content-type", "image/jpeg"),
                headers={"Content-Disposition": f"attachment; filename={filename}"}
            )
    except Exception as e:
        return f"Error downloading photo: {e}", 500

    return "Photo not found", 404


@app.route("/download_photos_zip/<grade>/<section_name>")
def download_photos_zip(grade, section_name):
    """Download all photos for a section as a ZIP file."""
    import zipfile, io, requests as req
    from database import get_section_detail

    _, students = get_section_detail(grade, section_name)

    zip_buffer = io.BytesIO()
    count = 0

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for student in students:
            if not student["photo_url"]:
                continue

            last  = (student["last_name"] or "").upper().replace(" ", "")
            first = (student["first_name"] or "").upper().replace(" ", "")
            g     = (student["grade"] or "").upper().replace(" ", "")
            sec   = (student["section_name"] or "").upper().replace(" ", "")
            ext   = student["photo_url"].split(".")[-1].lower()
            if ext not in ["jpg","jpeg","png","gif","webp"]:
                ext = "jpg"
            filename = f"{last}_{first}_{g}_{sec}.{ext}"

            photo_url = student["photo_url"]
            try:
                if photo_url.startswith("/static/"):
                    filepath = os.path.join(os.getcwd(), photo_url.lstrip("/"))
                    if os.path.exists(filepath):
                        with open(filepath, "rb") as f:
                            zf.writestr(filename, f.read())
                            count += 1
                else:
                    resp = req.get(photo_url, timeout=10)
                    if resp.status_code == 200:
                        zf.writestr(filename, resp.content)
                        count += 1
            except Exception:
                continue

    if count == 0:
        return "No photos found for this section", 404

    zip_buffer.seek(0)
    zip_name = f"photos_{grade}_{section_name}.zip".replace(" ", "_")
    from flask import Response
    return Response(
        zip_buffer.getvalue(),
        mimetype="application/zip",
        headers={"Content-Disposition": f"attachment; filename={zip_name}"}
    )


@app.route("/download_template_csv")
def download_template_csv():
    """Download the CSV template for teachers."""
    template = (
        "lrn,last_name,first_name,middle_initial,extension,"
        "grade,section_name,adviser_name,"
        "emergency_contact_name,emergency_contact_address,emergency_contact_number\n"
        "123456789001,dela Cruz,Juan,A,,Grade 1,Sampaguita,Maria Santos,"
        "Rosa dela Cruz,123 Rizal St Davao City,09284553934\n"
        "123456789002,Reyes,Maria,B,,Grade 1,Sampaguita,Maria Santos,"
        "Pedro Reyes,456 Mabini St Davao City,09171234567\n"
    )
    from flask import Response
    return Response(
        template,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=CES_Student_Template.csv"}
    )

# ── ENTRY POINT ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    setup_database()
    port = int(os.environ.get("PORT", 8080))
    print(f"\n{'='*50}")
    print(f"  Teacher Portal — {SCHOOL_NAME}")
    print(f"{'='*50}")
    print(f"  URL: http://localhost:{port}")
    print(f"  Admin: http://localhost:{port}/admin/login")
    print(f"{'='*50}\n")
    app.run(host="0.0.0.0", port=port, debug=False)
