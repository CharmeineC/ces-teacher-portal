"""
google_drive.py — Google Drive photo storage
Uses correct multipart/related upload (required by Google Drive API).
"""
import os, io, json, uuid


def get_credentials():
    """Get refreshed service account credentials."""
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    if not creds_json:
        print("Google Drive: GOOGLE_CREDENTIALS not set")
        return None
    try:
        from google.oauth2.service_account import Credentials
        import google.auth.transport.requests as gtr
        creds = Credentials.from_service_account_info(
            json.loads(creds_json),
            scopes=["https://www.googleapis.com/auth/drive"]
        )
        # Properly refresh the token
        request = gtr.Request()
        creds.refresh(request)
        print(f"Google Drive: token refreshed, expires={creds.expiry}")
        return creds
    except Exception as e:
        print(f"Google Drive credentials error: {e}")
        import traceback; traceback.print_exc()
        return None


def get_drive_service(creds=None):
    if creds is None:
        creds = get_credentials()
    if not creds:
        return None
    try:
        from googleapiclient.discovery import build
        return build("drive", "v3", credentials=creds, cache_discovery=False)
    except Exception as e:
        print(f"Google Drive service error: {e}")
        return None


def is_configured():
    return bool(os.environ.get("GOOGLE_CREDENTIALS"))


def _make_public(service, file_id):
    try:
        service.permissions().create(
            fileId=file_id,
            body={"type": "anyone", "role": "reader"}
        ).execute()
        print(f"Google Drive: made {file_id} public")
    except Exception as e:
        print(f"Google Drive make public error: {e}")


def get_or_create_folder(service, folder_name, parent_id=None):
    """Get or create a folder in Drive."""
    if parent_id and "drive.google.com" in str(parent_id):
        parent_id = parent_id.rstrip("/").split("/")[-1]
    if not parent_id or not str(parent_id).strip():
        parent_id = None

    print(f"Google Drive: looking for folder '{folder_name}' parent='{parent_id}'")
    try:
        q = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
        if parent_id:
            q += f" and '{parent_id}' in parents"
        res = service.files().list(q=q, fields="files(id)").execute()
        files = res.get("files", [])
        if files:
            print(f"Google Drive: found folder id={files[0]['id']}")
            return files[0]["id"]
    except Exception as e:
        print(f"Google Drive folder search error: {e}")

    try:
        meta = {"name": folder_name, "mimeType": "application/vnd.google-apps.folder"}
        if parent_id:
            meta["parents"] = [parent_id]
        f = service.files().create(body=meta, fields="id").execute()
        fid = f.get("id")
        print(f"Google Drive: created folder '{folder_name}' id={fid}")
        _make_public(service, fid)
        return fid
    except Exception as e:
        print(f"Google Drive folder create error: {e}")
        return None


def _upload_multipart_related(token, metadata, file_content, mime_type):
    """
    Upload file using multipart/related format.
    This is the CORRECT format for Google Drive API file uploads.
    """
    import requests as req

    boundary = "boundary_" + uuid.uuid4().hex

    # Build the multipart/related body
    part1 = (
        f"--{boundary}\r\n"
        f"Content-Type: application/json; charset=UTF-8\r\n"
        f"\r\n"
        f"{json.dumps(metadata)}\r\n"
    ).encode("utf-8")

    part2 = (
        f"--{boundary}\r\n"
        f"Content-Type: {mime_type}\r\n"
        f"\r\n"
    ).encode("utf-8")

    end = f"\r\n--{boundary}--".encode("utf-8")

    body = part1 + part2 + file_content + end

    print(f"Google Drive: sending {len(body)} bytes multipart/related upload")

    resp = req.post(
        "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&fields=id,name",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/related; boundary={boundary}",
            "Content-Length": str(len(body)),
        },
        data=body,
        timeout=60
    )
    return resp


def upload_photo(file_content, filename, grade, section_name, mime_type="image/jpeg"):
    """Upload photo to Google Drive. Returns public URL or None."""
    if not file_content:
        print("Google Drive: empty file content!")
        return None

    print(f"Google Drive: uploading '{filename}' ({len(file_content)} bytes) grade={grade} section={section_name}")

    creds = get_credentials()
    if not creds:
        print("Google Drive: no credentials available")
        return None

    if not creds.token:
        print("Google Drive: token is empty after refresh!")
        return None

    print(f"Google Drive: using token starting with {creds.token[:20]}...")

    try:
        service = get_drive_service(creds)
        if not service:
            return None

        # Get/create section folder
        root_id = os.environ.get("GOOGLE_DRIVE_FOLDER_ID", "").strip()
        if "drive.google.com" in root_id:
            root_id = root_id.rstrip("/").split("/")[-1]
        if not root_id:
            root_id = None

        grade_c   = (grade or "Unknown").replace(" ", "").replace("/", "-")
        section_c = (section_name or "Unknown").replace(" ", "").replace("/", "-")
        folder_id = get_or_create_folder(service, f"{grade_c}-{section_c}", root_id)

        if not folder_id:
            print("Google Drive: could not get/create folder!")
            return None

        # Upload file
        metadata = {"name": filename, "parents": [folder_id]}
        resp = _upload_multipart_related(creds.token, metadata, file_content, mime_type)

        print(f"Google Drive upload response: {resp.status_code}")
        print(f"Google Drive response body: {resp.text[:500]}")

        if resp.status_code in (200, 201):
            data = resp.json()
            file_id = data.get("id")
            if file_id:
                _make_public(service, file_id)
                url = f"https://drive.google.com/uc?export=view&id={file_id}"
                print(f"Google Drive: SUCCESS! URL={url}")
                return url
            else:
                print(f"Google Drive: no file ID in response: {data}")
        else:
            print(f"Google Drive upload FAILED: {resp.status_code} — {resp.text}")

    except Exception as e:
        print(f"Google Drive exception: {e}")
        import traceback; traceback.print_exc()

    return None


def test_connection():
    """Full test — connection + actual file upload."""
    import requests as req

    creds = get_credentials()
    if not creds:
        return False, "GOOGLE_CREDENTIALS not set or invalid"

    try:
        service = get_drive_service(creds)
        about = service.about().get(fields="user").execute()
        email = about.get("user", {}).get("emailAddress", "unknown")
        print(f"Google Drive: connected as {email}")

        # Test actual upload
        test_content = b"CES Teacher Portal test file"
        resp = _upload_multipart_related(
            creds.token,
            {"name": "_ces_portal_test_.txt"},
            test_content,
            "text/plain"
        )

        print(f"Test upload response: {resp.status_code} — {resp.text[:300]}")

        if resp.status_code in (200, 201):
            fid = resp.json().get("id")
            if fid:
                try: service.files().delete(fileId=fid).execute()
                except: pass
            return True, f"✅ Connected as {email} | Upload test: PASSED"
        else:
            return False, f"Connected as {email} | Upload FAILED: {resp.status_code} — {resp.text[:300]}"

    except Exception as e:
        import traceback; traceback.print_exc()
        return False, f"Error: {str(e)}"
