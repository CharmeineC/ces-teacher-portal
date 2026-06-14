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


def upload_photo(file, grade="", section_name="", student_name=""):
    """
    Save photo and return URL.
    Priority: Google Drive → local storage fallback
    """
    if not file or not file.filename:
        return ""

    import time
    from google_drive import is_configured, upload_photo as gd_upload

    # Build clean filename
    if student_name:
        clean_name = student_name.upper().replace(" ", "_").replace(",", "")
    else:
        clean_name = str(int(time.time()))

    safe_name = secure_filename(file.filename)
    ext = safe_name.rsplit(".", 1)[-1].lower() if "." in safe_name else "jpg"
    if ext not in ["jpg","jpeg","png","gif","webp"]:
        ext = "jpg"
    filename = f"{clean_name}.{ext}"

    # Read file content ONCE at the very start
    try:
        file_content = file.read()
    except Exception as e:
        print(f"Error reading file: {e}")
        return ""

    if not file_content:
        print("File content is empty!")
        return ""

    mime_type = getattr(file, "content_type", None) or "image/jpeg"
    print(f"Upload: {filename}, size={len(file_content)} bytes, type={mime_type}, grade={grade}, section={section_name}")

    # Try Google Drive first
    if is_configured():
        try:
            url = gd_upload(file_content, filename, grade, section_name, mime_type)
            if url:
                print(f"Google Drive upload success: {url}")
                return url
            else:
                print("Google Drive upload returned None — falling back to local")
        except Exception as e:
            print(f"Google Drive upload error: {e}")

    # Local storage fallback
    try:
        filename_local = f"{int(time.time())}_{filename}"
        filepath = os.path.join(UPLOAD_FOLDER, filename_local)
        with open(filepath, "wb") as f_out:
            f_out.write(file_content)
        print(f"Saved locally: {filepath}")
        return f"/static/uploads/{filename_local}"
    except Exception as e:
        print(f"Local upload failed: {e}")
        return ""


def is_admin():
    return session.get("admin_logged_in") is True


# ── PUBLIC ROUTES ─────────────────────────────────────────────────────────────

@app.route("/")
def index():
    """Main teacher portal page."""
    from database import get_dashboard_stats, auto_create_sections_from_students
    # Auto-create sections from any imported students
    auto_create_sections_from_students()
    grade   = request.args.get("grade", "")
    section = request.args.get("section", "")
    search  = request.args.get("search", "")
    students = get_students(grade or None, section or None, search or None)
    sections = get_all_sections()
    grades   = get_all_grades()
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
            sig_url = upload_photo(
                sig_file,
                grade=grade,
                section_name=section_name,
                student_name=f"SIGNATURE_{adviser_name.replace(' ','_')}"
            )

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

    if grade and section_name:
        return redirect(url_for("index",
                                msg=f"Class {grade} - {section_name} saved successfully!",
                                success="1"))
    return redirect(url_for("index", msg="Section saved!", success="1"))


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
            student_name = f"{data.get('last_name','')}_{data.get('first_name','')}"
            data["photo_url"] = upload_photo(
                photo_file,
                grade=data.get("grade",""),
                section_name=data.get("section_name",""),
                student_name=student_name
            )

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
            student_name = f"{data.get('last_name','')}_{data.get('first_name','')}"
            photo_url = upload_photo(
                photo_file,
                grade=data.get("grade",""),
                section_name=data.get("section_name",""),
                student_name=student_name
            )
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

    student = get_student_by_id(student_id)
    student_name = f"{student['last_name']}_{student['first_name']}" if student else ""
    photo_url = upload_photo(
        photo_file,
        grade=student["grade"] if student else "",
        section_name=student["section_name"] if student else "",
        student_name=student_name
    )
    update_student_photo(student_id, photo_url)
    return jsonify({"success": True, "photo_url": photo_url})


@app.route("/bulk_import", methods=["POST"])
def route_bulk_import():
    """Import students from CSV file."""
    grade   = request.form.get("grade", "").strip()
    section = request.form.get("section_name", "").strip()
    adviser = request.form.get("adviser_name", "").strip()

    if "file" not in request.files:
        return redirect(url_for("index", msg="No file selected", success="0"))

    file = request.files["file"]
    if not file or not file.filename:
        return redirect(url_for("index", msg="No file selected", success="0"))

    # Grade and section MUST come from the form — not from CSV
    if not grade or not section:
        return redirect(url_for("index",
            msg="Please select your grade and section before importing.",
            success="0"))

    # Get adviser info from the section record
    from database import get_section
    sec_info = get_section(grade, section)
    adviser = sec_info["adviser_name"] if sec_info else adviser

    try:
        stream  = io.StringIO(file.stream.read().decode("utf-8-sig"))
        reader  = csv.DictReader(stream)
        students = []
        for row in reader:
            s = {
                "lrn":           str(row.get("lrn") or row.get("LRN") or "").strip(),
                "first_name":    str(row.get("first_name") or row.get("First Name") or row.get("FIRST NAME") or "").strip(),
                "last_name":     str(row.get("last_name") or row.get("Last Name") or row.get("LAST NAME") or "").strip(),
                "middle_initial":str(row.get("middle_initial") or row.get("MI") or row.get("Middle Initial") or "").strip(),
                "extension":     str(row.get("extension") or row.get("Extension") or row.get("EXT") or "").strip(),
                # Always use grade/section from form — never from CSV
                "grade":         grade,
                "section_name":  section,
                "adviser_name":  adviser,
                "emergency_contact_name":    str(row.get("emergency_contact_name") or row.get("Emergency Contact") or "").strip(),
                "emergency_contact_address": str(row.get("emergency_contact_address") or row.get("Address") or "").strip(),
                "emergency_contact_number":  str(row.get("emergency_contact_number") or row.get("Contact Number") or "").strip(),
            }
            if s["first_name"] or s["last_name"]:
                students.append(s)

        added, updated, errors = bulk_import_students(students)
        msg = f"Done! {added} new students added, {updated} existing students updated in {grade} - {section}."
        if errors:
            msg += f" Issues: {'; '.join(errors[:3])}"
        return redirect(url_for("section_detail",
                                grade=grade,
                                section_name=section,
                                msg=msg,
                                success="1"))
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
    from database import get_section_detail, get_dashboard_stats, auto_create_sections_from_students
    # Auto-create section if it came from CSV but not manually added
    auto_create_sections_from_students()
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
                           selected_grade=grade,
                           selected_section=section_name,
                           is_admin=is_admin())


@app.route("/download_photo/<int:student_id>")
def download_photo(student_id):
    """Download a single student photo with proper filename."""
    try:
        student = get_student_by_id(student_id)
        if not student or not student["photo_url"]:
            return "No photo found for this student", 404

        # Build clean filename
        last  = (student["last_name"]    or "UNKNOWN").upper().replace(" ", "")
        first = (student["first_name"]   or "UNKNOWN").upper().replace(" ", "")
        grade = (student["grade"]        or "").upper().replace(" ", "").replace("-","")
        sec   = (student["section_name"] or "").upper().replace(" ", "")
        
        photo_url = student["photo_url"]
        
        # Get file extension
        url_path = photo_url.split("?")[0]  # remove query params
        ext = url_path.split(".")[-1].lower() if "." in url_path else "jpg"
        if ext not in ["jpg","jpeg","png","gif","webp"]:
            ext = "jpg"
        
        filename = f"{last}_{first}_{grade}_{sec}.{ext}"

        # Local file (saved in static/uploads)
        if photo_url.startswith("/static/"):
            # Try multiple base paths
            for base in [os.getcwd(), "/app", os.path.dirname(__file__)]:
                filepath = os.path.join(base, photo_url.lstrip("/"))
                if os.path.exists(filepath):
                    from flask import send_file
                    return send_file(
                        filepath,
                        as_attachment=True,
                        download_name=filename
                    )
            return "Photo file not found on server", 404

        # Remote URL (Cloudinary, etc.)
        import requests as rq
        resp = rq.get(photo_url, timeout=15)
        if resp.status_code == 200:
            from flask import Response
            ctype = resp.headers.get("content-type", "image/jpeg")
            return Response(
                resp.content,
                mimetype=ctype,
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"',
                    "Content-Length": str(len(resp.content))
                }
            )
        return f"Could not fetch photo (status {resp.status_code})", 404

    except Exception as e:
        print(f"Download photo error: {e}")
        return f"Error: {str(e)}", 500


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
                    found = False
                    for base in [os.getcwd(), "/app", os.path.dirname(__file__)]:
                        filepath = os.path.join(base, photo_url.lstrip("/"))
                        if os.path.exists(filepath):
                            with open(filepath, "rb") as f:
                                zf.writestr(filename, f.read())
                                count += 1
                                found = True
                                break
                    if not found:
                        continue
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
    """Download the simplified CSV template for teachers.
    No grade/section needed — those come from the form."""
    template = (
        "lrn,last_name,first_name,middle_initial,extension,"
        "emergency_contact_name,emergency_contact_address,emergency_contact_number\n"
        "123456789001,dela Cruz,Juan,A,,"
        "Rosa dela Cruz,123 Rizal St Davao City,09284553934\n"
        "123456789002,Reyes,Maria,B,,"
        "Pedro Reyes,456 Mabini St Davao City,09171234567\n"
        "123456789003,Santos,Jose,C,Jr.,"
        "Ana Santos,789 Bonifacio St Davao City,09281234567\n"
    )
    from flask import Response
    return Response(
        template,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=CES_Student_Template.csv"}
    )


@app.route("/api/test_drive")
def api_test_drive():
    """Test Google Drive connection."""
    from google_drive import test_connection
    success, message = test_connection()
    return jsonify({"success": success, "message": message})


@app.route("/delete_section/<grade>/<section_name>", methods=["POST"])
def route_delete_section(grade, section_name):
    """Delete a section and all its students."""
    from database import delete_section
    delete_section(grade, section_name)
    return redirect(url_for("index",
                            msg=f"Section {grade} - {section_name} and all its students deleted.",
                            success="1"))


@app.route("/delete_student/<int:student_id>", methods=["POST"])
def route_delete_student(student_id):
    """Delete a single student."""
    from database import delete_student, get_student_by_id
    student = get_student_by_id(student_id)
    if student:
        grade = student["grade"]
        section = student["section_name"]
        delete_student(student_id)
        return redirect(url_for("section_detail",
                                grade=grade,
                                section_name=section,
                                msg="Student deleted.",
                                success="1"))
    return redirect(url_for("index"))

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
