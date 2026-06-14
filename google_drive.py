"""
google_drive.py — Google Drive photo storage
Uses raw HTTP multipart upload (bypasses googleapiclient MediaIoBaseUpload issues).
"""
import os
import io
import json


def get_credentials():
    """Get service account credentials."""
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    if not creds_json:
        return None
    try:
        from google.oauth2.service_account import Credentials
        import google.auth.transport.requests as google_requests
        creds_dict = json.loads(creds_json)
        creds = Credentials.from_service_account_info(
            creds_dict,
            scopes=["https://www.googleapis.com/auth/drive"]
        )
        # Refresh to get access token
        request = google_requests.Request()
        creds.refresh(request)
        return creds
    except Exception as e:
        print(f"Google Drive credentials error: {e}")
        return None


def get_drive_service():
    """Get Drive service for folder operations."""
    creds = get_credentials()
    if not creds:
        return None
    try:
        from googleapiclient.discovery import build
        service = build("drive", "v3", credentials=creds, cache_discovery=False)
        return service
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
        print(f"Google Drive: make public error: {e}")


def get_or_create_folder(service, folder_name, parent_id=None):
    """Get or create a folder in Drive."""
    if parent_id and "drive.google.com" in str(parent_id):
        parent_id = parent_id.rstrip("/").split("/")[-1]
    if not parent_id or not str(parent_id).strip():
        parent_id = None

    try:
        query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
        if parent_id:
            query += f" and '{parent_id}' in parents"
        results = service.files().list(q=query, fields="files(id,name)").execute()
        files = results.get("files", [])
        if files:
            return files[0]["id"]
    except Exception as e:
        print(f"Google Drive: folder search error: {e}")

    try:
        metadata = {"name": folder_name, "mimeType": "application/vnd.google-apps.folder"}
        if parent_id:
            metadata["parents"] = [parent_id]
        folder = service.files().create(body=metadata, fields="id").execute()
        folder_id = folder.get("id")
        print(f"Google Drive: created folder '{folder_name}' id={folder_id}")
        _make_public(service, folder_id)
        return folder_id
    except Exception as e:
        print(f"Google Drive: folder create error: {e}")
        return None


def upload_photo(file_content, filename, grade, section_name, mime_type="image/jpeg"):
    """
    Upload photo using raw HTTP multipart — bypasses MediaIoBaseUpload issues.
    """
    import requests as req

    creds = get_credentials()
    if not creds:
        return None

    if not file_content:
        print("Google Drive: empty file content")
        return None

    print(f"Google Drive: uploading '{filename}' {len(file_content)} bytes")

    try:
        # Get folder
        service = get_drive_service()
        root_id = os.environ.get("GOOGLE_DRIVE_FOLDER_ID", "").strip()
        if "drive.google.com" in root_id:
            root_id = root_id.rstrip("/").split("/")[-1]
        if not root_id:
            root_id = None

        grade_clean   = (grade or "Unknown").replace(" ", "").replace("/", "-")
        section_clean = (section_name or "Unknown").replace(" ", "").replace("/", "-")
        folder_name   = f"{grade_clean}-{section_clean}"
        folder_id     = get_or_create_folder(service, folder_name, root_id)

        if not folder_id:
            print("Google Drive: no folder ID!")
            return None

        # Use RAW HTTP multipart upload
        token = creds.token
        metadata = json.dumps({"name": filename, "parents": [folder_id]})

        response = req.post(
            "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&fields=id",
            headers={"Authorization": f"Bearer {token}"},
            files={
                "metadata": ("metadata", metadata, "application/json; charset=UTF-8"),
                "file":     (filename, file_content, mime_type)
            },
            timeout=30
        )

        print(f"Google Drive upload response: {response.status_code} — {response.text[:200]}")

        if response.status_code in (200, 201):
            file_id = response.json().get("id")
            if file_id:
                _make_public(service, file_id)
                url = f"https://drive.google.com/uc?export=view&id={file_id}"
                print(f"Google Drive: success! URL={url}")
                return url
            else:
                print("Google Drive: no file ID in response")
        else:
            print(f"Google Drive: upload failed {response.status_code}: {response.text}")

    except Exception as e:
        print(f"Google Drive: upload exception: {e}")
        import traceback
        traceback.print_exc()

    return None


def test_connection():
    """Test connection AND actual file upload."""
    import requests as req

    creds = get_credentials()
    if not creds:
        return False, "GOOGLE_CREDENTIALS not set or invalid"

    try:
        from googleapiclient.discovery import build
        service = build("drive", "v3", credentials=creds, cache_discovery=False)
        about   = service.about().get(fields="user").execute()
        email   = about.get("user", {}).get("emailAddress", "unknown")

        # Test actual file upload
        token    = creds.token
        test_content = b"test upload"
        metadata = json.dumps({"name": "_portal_test.txt"})
        response = req.post(
            "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&fields=id",
            headers={"Authorization": f"Bearer {token}"},
            files={
                "metadata": ("metadata", metadata, "application/json; charset=UTF-8"),
                "file":     ("_portal_test.txt", test_content, "text/plain")
            },
            timeout=15
        )

        if response.status_code in (200, 201):
            file_id = response.json().get("id")
            # Delete test file
            try:
                service.files().delete(fileId=file_id).execute()
            except Exception:
                pass
            return True, f"✅ Connected as {email} | Upload test: PASSED"
        else:
            return False, f"Connected as {email} but upload FAILED: {response.status_code} {response.text[:100]}"

    except Exception as e:
        return False, f"Error: {str(e)}"
