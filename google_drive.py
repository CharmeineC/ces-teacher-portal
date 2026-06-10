"""
google_drive.py — Google Drive photo storage
Organizes photos by grade and section automatically.
"""

import os
import io
import json


def get_drive_service():
    """Create Google Drive service using service account credentials."""
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    if not creds_json:
        return None
    try:
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build
        creds_dict = json.loads(creds_json)
        creds = Credentials.from_service_account_info(
            creds_dict,
            scopes=["https://www.googleapis.com/auth/drive.file"]
        )
        service = build("drive", "v3", credentials=creds)
        return service
    except Exception as e:
        print(f"Google Drive auth error: {e}")
        return None


def is_configured():
    """Check if Google Drive is configured."""
    return bool(os.environ.get("GOOGLE_CREDENTIALS"))


def get_or_create_folder(service, folder_name, parent_id=None):
    """Get a folder by name or create it if it doesn't exist."""
    query = (
        f"name='{folder_name}' and "
        f"mimeType='application/vnd.google-apps.folder' and "
        f"trashed=false"
    )
    if parent_id:
        query += f" and '{parent_id}' in parents"

    results = service.files().list(
        q=query, fields="files(id, name)", spaces="drive"
    ).execute()
    files = results.get("files", [])

    if files:
        return files[0]["id"]

    # Create folder
    metadata = {
        "name": folder_name,
        "mimeType": "application/vnd.google-apps.folder",
    }
    if parent_id:
        metadata["parents"] = [parent_id]

    folder = service.files().create(body=metadata, fields="id").execute()
    folder_id = folder.get("id")

    # Make folder publicly accessible
    _make_public(service, folder_id)
    return folder_id


def _make_public(service, file_id):
    """Make a file or folder publicly readable."""
    try:
        service.permissions().create(
            fileId=file_id,
            body={"type": "anyone", "role": "reader"}
        ).execute()
    except Exception as e:
        print(f"Error making public: {e}")


def upload_photo(file_content, filename, grade, section_name, mime_type="image/jpeg"):
    """
    Upload a photo to Google Drive.
    Organized as: Root Folder / Grade_-_Section / filename.jpg
    Returns public URL or None if failed.
    """
    service = get_drive_service()
    if not service:
        return None

    try:
        from googleapiclient.http import MediaIoBaseUpload

        # Root folder ID from env var
        root_id = os.environ.get("GOOGLE_DRIVE_FOLDER_ID")

        # Clean names for folder
        grade_clean   = (grade or "Unknown").replace(" ", "").replace("/", "-")
        section_clean = (section_name or "Unknown").replace(" ", "").replace("/", "-")
        folder_name   = f"{grade_clean}_-_{section_clean}"

        # Get or create section folder inside root
        section_folder_id = get_or_create_folder(service, folder_name, root_id)

        # Delete old file with same name if exists (update photo)
        old_files = service.files().list(
            q=f"name='{filename}' and '{section_folder_id}' in parents and trashed=false",
            fields="files(id)"
        ).execute().get("files", [])
        for old in old_files:
            try:
                service.files().delete(fileId=old["id"]).execute()
            except Exception:
                pass

        # Upload new file
        file_metadata = {
            "name": filename,
            "parents": [section_folder_id]
        }
        media = MediaIoBaseUpload(
            io.BytesIO(file_content),
            mimetype=mime_type,
            resumable=False
        )
        uploaded = service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id"
        ).execute()
        file_id = uploaded.get("id")

        # Make file public
        _make_public(service, file_id)

        # Return direct view URL
        return f"https://drive.google.com/uc?export=view&id={file_id}"

    except Exception as e:
        print(f"Google Drive upload error: {e}")
        return None


def test_connection():
    """Test Google Drive connection. Returns (success, message)."""
    service = get_drive_service()
    if not service:
        return False, "GOOGLE_CREDENTIALS not configured"
    try:
        about = service.about().get(fields="user").execute()
        email = about.get("user", {}).get("emailAddress", "unknown")
        return True, f"Connected as {email}"
    except Exception as e:
        return False, str(e)
