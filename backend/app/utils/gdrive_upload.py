"""
Utility functions for uploading processed images to Google Drive
"""
import os
import io
from pathlib import Path
from googleapiclient.http import MediaFileUpload, MediaIoBaseUpload
from google.oauth2 import service_account
from googleapiclient.discovery import build


def get_drive_service():
    """Create Google Drive API service"""
    from app.config import settings
    
    creds_dict = settings.google_service_account_credentials
    if not creds_dict:
        raise Exception("Google Drive credentials not configured")
    
    credentials = service_account.Credentials.from_service_account_info(
        creds_dict,
        scopes=['https://www.googleapis.com/auth/drive']
    )
    
    return build('drive', 'v3', credentials=credentials)


def upload_image_to_drive(file_path: str, folder_id: str, filename: str = None) -> dict:
    """
    Upload an image file to Google Drive
    
    Args:
        file_path: Local path to the image file
        folder_id: Google Drive folder ID to upload to
        filename: Optional custom filename (defaults to basename)
    
    Returns:
        dict with 'id' and 'url' of uploaded file
    """
    service = get_drive_service()
    
    if filename is None:
        filename = Path(file_path).name
    
    # Determine mime type
    ext = Path(file_path).suffix.lower()
    mime_map = {
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
        '.gif': 'image/gif',
        '.webp': 'image/webp',
    }
    mime_type = mime_map.get(ext, 'image/jpeg')
    
    # File metadata
    file_metadata = {
        'name': filename,
        'parents': [folder_id]
    }
    
    # Upload file
    media = MediaFileUpload(file_path, mimetype=mime_type, resumable=True)
    file = service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id, webViewLink'
    ).execute()
    
    file_id = file.get('id')
    
    # Make file publicly readable
    service.permissions().create(
        fileId=file_id,
        body={'type': 'anyone', 'role': 'reader'}
    ).execute()
    
    # Return Google Drive URL
    url = f"https://drive.google.com/uc?export=view&id={file_id}"
    
    return {
        'id': file_id,
        'url': url,
        'web_view_link': file.get('webViewLink')
    }


def upload_image_bytes_to_drive(image_bytes: bytes, folder_id: str, filename: str, mime_type: str = 'image/jpeg') -> dict:
    """
    Upload image bytes to Google Drive
    
    Args:
        image_bytes: Image data as bytes
        folder_id: Google Drive folder ID to upload to
        filename: Filename for the uploaded file
        mime_type: MIME type of the image
    
    Returns:
        dict with 'id' and 'url' of uploaded file
    """
    service = get_drive_service()
    
    # File metadata
    file_metadata = {
        'name': filename,
        'parents': [folder_id]
    }
    
    # Upload from memory
    media = MediaIoBaseUpload(io.BytesIO(image_bytes), mimetype=mime_type, resumable=True)
    file = service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id, webViewLink'
    ).execute()
    
    file_id = file.get('id')
    
    # Make file publicly readable
    service.permissions().create(
        fileId=file_id,
        body={'type': 'anyone', 'role': 'reader'}
    ).execute()
    
    # Return Google Drive URL
    url = f"https://drive.google.com/uc?export=view&id={file_id}"
    
    return {
        'id': file_id,
        'url': url,
        'web_view_link': file.get('webViewLink')
    }


def create_folder_in_drive(folder_name: str, parent_folder_id: str) -> str:
    """
    Create a folder in Google Drive
    
    Args:
        folder_name: Name of the folder to create
        parent_folder_id: Parent folder ID
    
    Returns:
        ID of the created folder
    """
    service = get_drive_service()
    
    file_metadata = {
        'name': folder_name,
        'mimeType': 'application/vnd.google-apps.folder',
        'parents': [parent_folder_id]
    }
    
    file = service.files().create(body=file_metadata, fields='id').execute()
    return file.get('id')


def find_or_create_folder(folder_name: str, parent_folder_id: str) -> str:
    """
    Find existing folder or create new one
    
    Args:
        folder_name: Name of the folder
        parent_folder_id: Parent folder ID
    
    Returns:
        ID of the folder (existing or newly created)
    """
    service = get_drive_service()
    
    # Search for existing folder
    query = f"name='{folder_name}' and '{parent_folder_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
    results = service.files().list(q=query, fields='files(id, name)').execute()
    files = results.get('files', [])
    
    if files:
        return files[0]['id']
    else:
        return create_folder_in_drive(folder_name, parent_folder_id)
