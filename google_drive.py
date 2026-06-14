"""
google_drive.py — Google Drive photo storage
Organizes photos by grade and section automatically.
Uses simple multipart upload instead of MediaIoBaseUpload.
"""

import os
import io
import json


def get_drive_service():
    """Create Google Drive service using service account credentials."""
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    if not creds_json:
        print("Google Drive: GOOGLE_CREDENTIALS not set")
        return None
    try:
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build
        creds_dict = json.loads(creds_json)
        creds = Credentials.from_service_account_info(
            creds_dict,
            scopes=["https://www.googleapis.com/auth/drive"]
        )
        service = build("drive", "v3", credentials=creds, cache_discovery=False)
        return service
    except Exception as e:
        print(f"Google Drive auth error: {e}")
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
        print(f"Google Drive: make public error: {e}")


def get_or_create_folder(service, folder_name, parent_id=None):
    """Get folder by name or create it."""
    if parent_id and "drive.google.com" in str(parent_id):
        parent_id = parent_id.rstrip("/").split("/")[-1]
    if not parent_id or not parent_id.strip():
        parent_id = None

    print(f"Google Drive: folder lookup '{folder_name}' parent='{parent_id}'")

    try:
        query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
        if parent_id:
            query += f" and '{parent_id}' in parents"
        results = service.files().list(q=query, fields="files(id,name)", spaces="drive").execute()
        files = results.get("files", [])
        if files:
            print(f"Google Drive: found folder '{folder_name}' id={files[0]['id']}")
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
    Upload photo to Google Drive organized by grade/section.
    Returns public URL or None if failed.
    """
    service = get_drive_service()
    if not service:
        return None

    if not file_content:
        print("Google Drive: file_content is empty!")
        return None

    print(f"Google Drive: uploading '{filename}' size={len(file_content)} bytes mime={mime_type}")

    try:
        from googleapiclient.http import MediaIoBaseUpload

        # Get root folder
        root_id = os.environ.get("GOOGLE_DRIVE_FOLDER_ID", "").strip()
        if "drive.google.com" in root_id:
            root_id = root_id.rstrip("/").split("/")[-1]
        if not root_id:
            root_id = None
        print(f"Google Drive: root folder id='{root_id}'")

        # Create grade/section subfolder
        grade_clean = (grade or "Unknown").replace(" ", "").replace("/", "-")
        section_clean = (section_name or "Unknown").replace(" ", "").replace("/", "-")
        folder_name = f"{grade_clean}-{section_clean}"
        folder_id = get_or_create_folder(service, folder_name, root_id)

        if not folder_id:
            print("Google Drive: could not get/create folder!")
            return None

        print(f"Google Drive: uploading to folder_id={folder_id}")

        # Upload file using MediaIoBaseUpload
        file_metadata = {"name": filename, "parents": [folder_id]}
        media = MediaIoBaseUpload(
            io.BytesIO(file_content),
            mimetype=mime_type,
            resumable=False
        )

        uploaded = service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id,name,size"
        ).execute()

        file_id = uploaded.get("id")
        if not file_id:
            print(f"Google Drive: upload returned no ID! Response: {uploaded}")
            return None

        print(f"Google Drive: uploaded successfully! id={file_id} name={uploaded.get('name')}")

        # Make public
        _make_public(service, file_id)

        url = f"https://drive.google.com/uc?export=view&id={file_id}"
        print(f"Google Drive: public URL = {url}")
        return url

    except Exception as e:
        print(f"Google Drive: upload exception: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_connection():
    """Test Google Drive connection and upload capability."""
    service = get_drive_service()
    if not service:
        return False, "GOOGLE_CREDENTIALS not configured"
    try:
        about = service.about().get(fields="user,storageQuota").execute()
        email = about.get("user", {}).get("emailAddress", "unknown")
        quota = about.get("storageQuota", {})
        used = int(quota.get("usage", 0)) // (1024*1024)
        total = int(quota.get("limit", 0)) // (1024*1024*1024)

        # Try a test upload
        from googleapiclient.http import MediaIoBaseUpload
        test_content = b"test"
        test_media = MediaIoBaseUpload(io.BytesIO(test_content), mimetype="text/plain", resumable=False)
        root_id = os.environ.get("GOOGLE_DRIVE_FOLDER_ID", "").strip()
        if "drive.google.com" in root_id:
            root_id = root_id.rstrip("/").split("/")[-1]

        test_meta = {"name": "_test_upload.txt"}
        if root_id:
            test_meta["parents"] = [root_id]

        test_file = service.files().create(
            body=test_meta, media_body=test_media, fields="id"
        ).execute()
        test_id = test_file.get("id")

        # Delete test file
        if test_id:
            try:
                service.files().delete(fileId=test_id).execute()
            except Exception:
                pass
            return True, f"✅ Connected as {email} | Storage: {used}MB used | Upload test: PASSED"
        else:
            return False, f"Connected as {email} but upload test FAILED — no file ID returned"

    except Exception as e:
        return False, f"Error: {str(e)}"
