"""
google_drive.py — Google Drive photo storage
Uses correct multipart/related upload format required by Google Drive API.
"""
import os, io, json, uuid


def get_credentials():
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    if not creds_json:
        return None
    try:
        from google.oauth2.service_account import Credentials
        import google.auth.transport.requests as google_requests
        creds = Credentials.from_service_account_info(
            json.loads(creds_json),
            scopes=["https://www.googleapis.com/auth/drive"]
        )
        google_requests.Request()(creds, None, None)  # refresh token
        return creds
    except Exception as e:
        # Try alternate refresh method
        try:
            from google.oauth2.service_account import Credentials
            import google.auth.transport.requests as gtr
            creds = Credentials.from_service_account_info(
                json.loads(creds_json),
                scopes=["https://www.googleapis.com/auth/drive"]
            )
            req = gtr.Request()
            creds.refresh(req)
            return creds
        except Exception as e2:
            print(f"Google Drive credentials error: {e2}")
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
    except Exception as e:
        print(f"Make public error: {e}")


def get_or_create_folder(service, folder_name, parent_id=None):
    if parent_id and "drive.google.com" in str(parent_id):
        parent_id = parent_id.rstrip("/").split("/")[-1]
    if not parent_id or not str(parent_id).strip():
        parent_id = None

    try:
        q = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
        if parent_id:
            q += f" and '{parent_id}' in parents"
        res = service.files().list(q=q, fields="files(id)").execute()
        files = res.get("files", [])
        if files:
            return files[0]["id"]
    except Exception as e:
        print(f"Folder search error: {e}")

    try:
        meta = {"name": folder_name, "mimeType": "application/vnd.google-apps.folder"}
        if parent_id:
            meta["parents"] = [parent_id]
        f = service.files().create(body=meta, fields="id").execute()
        fid = f.get("id")
        print(f"Created folder '{folder_name}' id={fid}")
        _make_public(service, fid)
        return fid
    except Exception as e:
        print(f"Folder create error: {e}")
        return None


def _multipart_related_upload(token, metadata, file_content, mime_type):
    """
    Correct Google Drive multipart/related upload.
    This is the format Google Drive API actually requires.
    """
    import requests as req

    boundary = uuid.uuid4().hex

    # Build multipart/related body
    body = (
        f"--{boundary}\r\n"
        f"Content-Type: application/json; charset=UTF-8\r\n\r\n"
        f"{json.dumps(metadata)}\r\n"
        f"--{boundary}\r\n"
        f"Content-Type: {mime_type}\r\n\r\n"
    ).encode("utf-8") + file_content + f"\r\n--{boundary}--".encode("utf-8")

    resp = req.post(
        "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&fields=id",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/related; boundary={boundary}",
        },
        data=body,
        timeout=30
    )
    return resp


def upload_photo(file_content, filename, grade, section_name, mime_type="image/jpeg"):
    """Upload photo to Google Drive. Returns public URL or None."""
    if not file_content:
        print("Google Drive: empty file content")
        return None

    creds = get_credentials()
    if not creds:
        print("Google Drive: no credentials")
        return None

    print(f"Google Drive: uploading '{filename}' ({len(file_content)} bytes)")

    try:
        service = get_drive_service(creds)

        # Get root folder
        root_id = os.environ.get("GOOGLE_DRIVE_FOLDER_ID", "").strip()
        if "drive.google.com" in root_id:
            root_id = root_id.rstrip("/").split("/")[-1]
        if not root_id:
            root_id = None

        # Create grade/section folder
        grade_c   = (grade or "Unknown").replace(" ", "").replace("/", "-")
        section_c = (section_name or "Unknown").replace(" ", "").replace("/", "-")
        folder_id = get_or_create_folder(service, f"{grade_c}-{section_c}", root_id)

        if not folder_id:
            print("Google Drive: could not get folder")
            return None

        # Upload using correct multipart/related format
        metadata = {"name": filename, "parents": [folder_id]}
        resp = _multipart_related_upload(creds.token, metadata, file_content, mime_type)

        print(f"Google Drive response: {resp.status_code} — {resp.text[:300]}")

        if resp.status_code in (200, 201):
            file_id = resp.json().get("id")
            if file_id:
                _make_public(service, file_id)
                url = f"https://drive.google.com/uc?export=view&id={file_id}"
                print(f"Google Drive: success! {url}")
                return url
        else:
            print(f"Google Drive upload failed: {resp.status_code} {resp.text}")

    except Exception as e:
        print(f"Google Drive exception: {e}")
        import traceback; traceback.print_exc()

    return None


def test_connection():
    """Test connection and upload capability."""
    import requests as req

    creds = get_credentials()
    if not creds:
        return False, "GOOGLE_CREDENTIALS not set or invalid"

    try:
        service = get_drive_service(creds)
        about = service.about().get(fields="user").execute()
        email = about.get("user", {}).get("emailAddress", "unknown")

        # Test upload with multipart/related
        test_meta = {"name": "_portal_test_.txt"}
        resp = _multipart_related_upload(
            creds.token, test_meta, b"test upload content", "text/plain"
        )

        if resp.status_code in (200, 201):
            fid = resp.json().get("id")
            try: service.files().delete(fileId=fid).execute()
            except: pass
            return True, f"✅ Connected as {email} | Upload test: PASSED"
        else:
            return False, f"Connected as {email} | Upload FAILED: {resp.status_code} — {resp.text[:200]}"

    except Exception as e:
        return False, f"Error: {str(e)}"
