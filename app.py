"""
LAN File-Sharing Platform - Flask Backend
A lightweight, self-hosted file sharing solution for local networks.
"""

import os
import uuid
import json
import shutil
import socket
import mimetypes
from datetime import datetime, timezone
from pathlib import Path
from functools import wraps
from io import BytesIO
import zipfile

from flask import (
    Flask, request, jsonify, send_file, render_template,
    Response, stream_with_context
)
from werkzeug.utils import secure_filename

try:
    from PIL import Image
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False

try:
    from PyPDF2 import PdfReader, PdfWriter
    PYPDF2_AVAILABLE = True
except ImportError:
    PYPDF2_AVAILABLE = False

# Initialize Flask app
app = Flask(__name__)

# Configuration
UPLOAD_DIR = os.environ.get('UPLOAD_DIR', './uploads')
MAX_FILE_SIZE = int(os.environ.get('MAX_FILE_SIZE', 536870912))  # 500MB default
ALLOWED_EXTENSIONS = os.environ.get(
    'ALLOWED_EXTENSIONS',
    'pdf,png,jpg,jpeg,gif,txt,md,json,csv,doc,docx,xlsx,xls,ppt,pptx,zip,tar,gz,mp3,mp4,wav,avi,mov'
).split(',')

# Ensure upload directory exists
Path(UPLOAD_DIR).mkdir(parents=True, exist_ok=True)

# In-memory file metadata store (in production, use SQLite or similar)
METADATA_FILE = os.path.join(UPLOAD_DIR, '.metadata.json')
SETTINGS_FILE = os.path.join(UPLOAD_DIR, '.settings.json')
TRASH_FILE = os.path.join(UPLOAD_DIR, '.trash.json')
TRASH_EXPIRY = 86400  # 24 hours in seconds

# Default settings
DEFAULT_SETTINGS = {
    'upload_dir': UPLOAD_DIR,
    'download_dir': '',
    'theme': 'dark',
    'max_file_size': MAX_FILE_SIZE
}


def load_settings():
    """Load application settings from disk."""
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r') as f:
                settings = json.load(f)
                return {**DEFAULT_SETTINGS, **settings}
        except (json.JSONDecodeError, IOError):
            return DEFAULT_SETTINGS.copy()
    return DEFAULT_SETTINGS.copy()


def save_settings(settings):
    """Save application settings to disk."""
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(settings, f, indent=2)


def load_metadata():
    """Load file metadata from disk."""
    if os.path.exists(METADATA_FILE):
        try:
            with open(METADATA_FILE, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {'files': {}, 'folders': ['root']}
    return {'files': {}, 'folders': ['root']}


def save_metadata(metadata):
    """Save file metadata to disk."""
    with open(METADATA_FILE, 'w') as f:
        json.dump(metadata, f, indent=2)


def load_trash():
    """Load deleted files from trash."""
    if os.path.exists(TRASH_FILE):
        try:
            with open(TRASH_FILE, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {'deleted_files': {}}
    return {'deleted_files': {}}


def save_trash(trash):
    """Save deleted files to trash."""
    with open(TRASH_FILE, 'w') as f:
        json.dump(trash, f, indent=2)


def move_to_trash(file_id, file_info):
    """Move a deleted file to trash for potential recovery."""
    trash = load_trash()
    if 'deleted_files' not in trash:
        trash['deleted_files'] = {}
    
    trash['deleted_files'][file_id] = {
        'file_info': file_info,
        'deleted_at': datetime.now(timezone.utc).isoformat(),
        'expires_at': (datetime.now(timezone.utc) + 
                      __import__('datetime').timedelta(seconds=TRASH_EXPIRY)).isoformat()
    }
    save_trash(trash)


def restore_from_trash(file_id):
    """Restore a file from trash."""
    trash = load_trash()
    
    if file_id not in trash.get('deleted_files', {}):
        return False
    
    trash_entry = trash['deleted_files'][file_id]
    file_info = trash_entry['file_info']
    
    # Check if trash entry has expired
    expires_at = datetime.fromisoformat(trash_entry['expires_at'])
    if datetime.now(timezone.utc) > expires_at:
        # Trash expired, file can't be recovered
        del trash['deleted_files'][file_id]
        save_trash(trash)
        return False
    
    # Restore file to metadata
    metadata = load_metadata()
    metadata['files'][file_id] = file_info
    
    # Ensure folder exists
    if file_info.get('folder_path') not in metadata.get('folders', []):
        metadata['folders'].append(file_info.get('folder_path', 'root'))
    
    save_metadata(metadata)
    
    # Remove from trash
    del trash['deleted_files'][file_id]
    save_trash(trash)
    
    return True


def get_file_icon(mime_type, filename):
    """Return appropriate icon class based on file type."""
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    
    icon_map = {
        'pdf': 'file-text',
        'doc': 'file-text',
        'docx': 'file-text',
        'txt': 'file-text',
        'md': 'file-text',
        'json': 'code',
        'csv': 'table',
        'xlsx': 'table',
        'xls': 'table',
        'png': 'image',
        'jpg': 'image',
        'jpeg': 'image',
        'gif': 'image',
        'mp3': 'music',
        'wav': 'music',
        'mp4': 'video',
        'avi': 'video',
        'mov': 'video',
        'zip': 'archive',
        'tar': 'archive',
        'gz': 'archive',
    }
    
    return icon_map.get(ext, 'file')


def allowed_file(filename):
    """Check if file extension is allowed."""
    if '.' not in filename:
        return False
    ext = filename.rsplit('.', 1)[1].lower()
    return ext in ALLOWED_EXTENSIONS


def format_file_size(size_bytes):
    """Format file size in human-readable format."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def get_disk_usage():
    """Get disk usage statistics."""
    try:
        total, used, free = shutil.disk_usage(UPLOAD_DIR)
        return {
            'total_gb': round(total / (1024**3), 2),
            'used_gb': round(used / (1024**3), 2),
            'free_gb': round(free / (1024**3), 2)
        }
    except Exception:
        return {'total_gb': 0, 'used_gb': 0, 'free_gb': 0}


# ============== Routes ==============

@app.route('/')
def index():
    """Serve the main web interface."""
    return render_template('index.html')


def get_local_ip():
    """Get the local IP address of the host machine."""
    # Check for HOST_IP environment variable (used in Docker deployments)
    host_ip = os.environ.get('HOST_IP')
    if host_ip:
        return host_ip
    
    try:
        # Create a socket to determine the local IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0)
        # Connect to a public DNS (doesn't actually send data)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        try:
            # Fallback: get hostname-based IP
            hostname = socket.gethostname()
            ip = socket.gethostbyname(hostname)
            if ip.startswith('127.'):
                # Try to get non-loopback address
                for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
                    if not info[4][0].startswith('127.'):
                        return info[4][0]
            return ip
        except Exception:
            return '127.0.0.1'


@app.route('/health')
def health_check():
    """Health check endpoint for monitoring."""
    metadata = load_metadata()
    uptime = datetime.now(timezone.utc).isoformat()
    
    return jsonify({
        'status': 'healthy',
        'version': '1.0.0',
        'timestamp': uptime,
        'file_count': len(metadata.get('files', {})),
        'disk_space': get_disk_usage()
    })


@app.route('/api/v1/connection')
def get_connection_info():
    """Get connection information including host IP and port."""
    host_ip = get_local_ip()
    port = int(os.environ.get('SERVER_PORT', 8000))
    
    return jsonify({
        'ip': host_ip,
        'port': port,
        'url': f'http://{host_ip}:{port}',
        'hostname': socket.gethostname()
    })


@app.route('/api/v1/upload', methods=['POST'])
def upload_file():
    """Handle file upload with support for multiple files and folder structure."""
    if 'files' not in request.files:
        return jsonify({
            'error': 'NO_FILE',
            'message': 'No files provided in request'
        }), 400
    
    files = request.files.getlist('files')
    base_folder = request.form.get('folder_path', 'root')
    
    if not files or (len(files) == 1 and files[0].filename == ''):
        return jsonify({
            'error': 'EMPTY_FILENAME',
            'message': 'No files selected'
        }), 400
    
    metadata = load_metadata()
    uploaded_files = []
    errors = []
    
    for file in files:
        if file.filename == '':
            continue
        
        # Get relative path for nested folders
        file_path_str = file.filename
        # Support folder structure from webkitdirectory
        path_parts = file_path_str.split('/')
        
        if len(path_parts) > 1:
            # File is in a subdirectory
            relative_path = '/'.join(path_parts[:-1])
            folder_path = f"{base_folder}/{relative_path}" if base_folder != 'root' else relative_path
            filename = path_parts[-1]
        else:
            # File is in root folder
            folder_path = base_folder
            filename = file_path_str
        
        if not allowed_file(filename):
            errors.append({
                'filename': filename,
                'error': 'INVALID_TYPE',
                'message': f'File type not allowed'
            })
            continue
        
        # Generate unique file ID
        file_id = str(uuid.uuid4())
        
        # Secure the filename
        original_filename = filename
        safe_filename = secure_filename(original_filename)
        
        # Handle duplicate filenames
        existing_files = [f['filename'] for f in metadata['files'].values() 
                          if f.get('folder_path') == folder_path]
        
        if safe_filename in existing_files:
            name, ext = os.path.splitext(safe_filename)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            safe_filename = f"{name}_{timestamp}{ext}"
        
        # Create folder structure if needed
        folder_dir = os.path.join(UPLOAD_DIR, folder_path.replace('/', os.sep)) if folder_path != 'root' else UPLOAD_DIR
        try:
            Path(folder_dir).mkdir(parents=True, exist_ok=True)
        except Exception as e:
            errors.append({
                'filename': filename,
                'error': 'FOLDER_CREATE_ERROR',
                'message': str(e)
            })
            continue
        
        # Save file
        file_path = os.path.join(folder_dir, f"{file_id}_{safe_filename}")
        try:
            file.save(file_path)
        except Exception as e:
            errors.append({
                'filename': filename,
                'error': 'SAVE_ERROR',
                'message': str(e)
            })
            continue
        
        # Get file info
        try:
            file_size = os.path.getsize(file_path)
        except Exception as e:
            os.remove(file_path)
            errors.append({
                'filename': filename,
                'error': 'SIZE_CHECK_ERROR',
                'message': str(e)
            })
            continue
        
        mime_type, _ = mimetypes.guess_type(safe_filename)
        
        # Check file size
        if file_size > MAX_FILE_SIZE:
            os.remove(file_path)
            errors.append({
                'filename': filename,
                'error': 'FILE_TOO_LARGE',
                'message': f'Exceeds {format_file_size(MAX_FILE_SIZE)}'
            })
            continue
        
        # Store metadata
        file_metadata = {
            'id': file_id,
            'filename': safe_filename,
            'original_filename': original_filename,
            'size': file_size,
            'size_formatted': format_file_size(file_size),
            'type': mime_type or 'application/octet-stream',
            'icon': get_file_icon(mime_type, safe_filename),
            'upload_date': datetime.now(timezone.utc).isoformat(),
            'folder_path': folder_path,
            'file_path': file_path
        }
        
        metadata['files'][file_id] = file_metadata
        
        # Add folder if new
        if folder_path not in metadata['folders']:
            metadata['folders'].append(folder_path)
        
        uploaded_files.append({
            'id': file_id,
            'filename': safe_filename,
            'size': file_size,
            'size_formatted': format_file_size(file_size),
            'type': mime_type,
            'icon': file_metadata['icon'],
            'upload_date': file_metadata['upload_date'],
            'url': f'/api/v1/files/{file_id}/download'
        })
    
    save_metadata(metadata)
    
    return jsonify({
        'uploaded': uploaded_files,
        'errors': errors,
        'total_uploaded': len(uploaded_files),
        'total_errors': len(errors)
    }), 201 if uploaded_files else 400


@app.route('/api/v1/files', methods=['GET'])
def list_files():
    """List all files with optional filtering."""
    folder_path = request.args.get('folder_path', 'root')
    sort_by = request.args.get('sort', 'date')
    order = request.args.get('order', 'desc')
    file_type = request.args.get('type', None)
    
    metadata = load_metadata()
    files = list(metadata.get('files', {}).values())
    
    # Filter by folder
    files = [f for f in files if f.get('folder_path', 'root') == folder_path]
    
    # Filter by type
    if file_type:
        type_map = {
            'images': ['image/png', 'image/jpeg', 'image/gif', 'image/webp'],
            'documents': ['application/pdf', 'application/msword', 
                         'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                         'text/plain', 'text/markdown'],
            'text': ['text/plain', 'text/markdown', 'application/json', 'text/csv'],
            'videos': ['video/mp4', 'video/avi', 'video/mov', 'video/webm', 'video/mkv', 'video/quicktime'],
            'media': ['audio/mpeg', 'audio/wav', 'video/mp4', 'video/avi']
        }
        allowed_types = type_map.get(file_type, [])
        if allowed_types:
            files = [f for f in files if f.get('type') in allowed_types]
    
    # Sort files
    if sort_by == 'name':
        files.sort(key=lambda x: x.get('filename', '').lower(), reverse=(order == 'desc'))
    elif sort_by == 'size':
        files.sort(key=lambda x: x.get('size', 0), reverse=(order == 'desc'))
    else:  # date
        files.sort(key=lambda x: x.get('upload_date', ''), reverse=(order == 'desc'))
    
    # Get subfolders
    all_folders = metadata.get('folders', ['root'])
    subfolders = []
    for folder in all_folders:
        if folder.startswith(folder_path + '/') if folder_path != 'root' else '/' not in folder:
            if folder != folder_path:
                subfolders.append(folder)
    
    return jsonify({
        'files': files,
        'total': len(files),
        'folders': subfolders,
        'current_folder': folder_path
    })


@app.route('/api/v1/files/<file_id>/download', methods=['GET'])
def download_file(file_id):
    """Download a specific file."""
    metadata = load_metadata()
    
    if file_id not in metadata.get('files', {}):
        return jsonify({
            'error': 'NOT_FOUND',
            'message': 'File not found'
        }), 404
    
    file_info = metadata['files'][file_id]
    file_path = file_info['file_path']
    
    if not os.path.exists(file_path):
        return jsonify({
            'error': 'FILE_MISSING',
            'message': 'File no longer exists on disk'
        }), 404
    
    return send_file(
        file_path,
        as_attachment=True,
        download_name=file_info['filename'],
        mimetype=file_info.get('type', 'application/octet-stream')
    )


@app.route('/api/v1/files/<file_id>/preview', methods=['GET'])
def preview_file(file_id):
    """Get file preview (for images and text files)."""
    metadata = load_metadata()
    
    if file_id not in metadata.get('files', {}):
        return jsonify({
            'error': 'NOT_FOUND',
            'message': 'File not found'
        }), 404
    
    file_info = metadata['files'][file_id]
    file_path = file_info['file_path']
    mime_type = file_info.get('type', '')
    
    if not os.path.exists(file_path):
        return jsonify({
            'error': 'FILE_MISSING',
            'message': 'File no longer exists on disk'
        }), 404
    
    # For images, serve directly
    if mime_type.startswith('image/'):
        return send_file(file_path, mimetype=mime_type)
    
    # For text files, return content
    if mime_type.startswith('text/') or mime_type in ['application/json']:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read(50000)  # Limit preview to 50KB
                return jsonify({
                    'type': 'text',
                    'content': content,
                    'truncated': len(content) >= 50000
                })
        except UnicodeDecodeError:
            return jsonify({
                'error': 'BINARY_FILE',
                'message': 'Cannot preview binary file'
            }), 400
    
    # For PDFs, serve for browser preview
    if mime_type == 'application/pdf':
        return send_file(file_path, mimetype=mime_type)
    
    return jsonify({
        'error': 'UNSUPPORTED',
        'message': 'Preview not supported for this file type'
    }), 400


@app.route('/api/v1/files/<file_id>', methods=['DELETE'])
def delete_file(file_id):
    """Delete a specific file (moves to trash for recovery)."""
    metadata = load_metadata()
    
    if file_id not in metadata.get('files', {}):
        return jsonify({
            'error': 'NOT_FOUND',
            'message': 'File not found'
        }), 404
    
    file_info = metadata['files'][file_id]
    file_path = file_info['file_path']
    
    # Delete physical file
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
        except Exception as e:
            return jsonify({
                'error': 'DELETE_ERROR',
                'message': str(e)
            }), 500
    
    # Move to trash for recovery
    move_to_trash(file_id, file_info)
    
    # Remove from metadata
    del metadata['files'][file_id]
    save_metadata(metadata)
    
    return jsonify({
        'id': file_id,
        'filename': file_info['filename'],
        'message': 'File deleted. Click "Undo" to recover.'
    }), 200


@app.route('/api/v1/files/<file_id>/rename', methods=['PATCH'])
def rename_file(file_id):
    """Rename a file."""
    metadata = load_metadata()
    
    if file_id not in metadata.get('files', {}):
        return jsonify({
            'error': 'NOT_FOUND',
            'message': 'File not found'
        }), 404
    
    data = request.get_json()
    new_name = data.get('filename')
    
    if not new_name:
        return jsonify({
            'error': 'INVALID_NAME',
            'message': 'New filename is required'
        }), 400
    
    new_name = secure_filename(new_name)
    
    file_info = metadata['files'][file_id]
    old_path = file_info['file_path']
    folder_dir = os.path.dirname(old_path)
    new_path = os.path.join(folder_dir, f"{file_id}_{new_name}")
    
    if os.path.exists(old_path):
        os.rename(old_path, new_path)
    
    file_info['filename'] = new_name
    file_info['file_path'] = new_path
    file_info['icon'] = get_file_icon(file_info.get('type'), new_name)
    
    save_metadata(metadata)
    
    return jsonify(file_info)


@app.route('/api/v1/search', methods=['GET'])
def search_files():
    """Search files by name."""
    query = request.args.get('query', '').lower()
    file_type = request.args.get('type', None)
    
    if not query:
        return jsonify({
            'error': 'EMPTY_QUERY',
            'message': 'Search query is required'
        }), 400
    
    metadata = load_metadata()
    files = list(metadata.get('files', {}).values())
    
    # Search by filename
    results = []
    for f in files:
        filename = f.get('filename', '').lower()
        if query in filename:
            score = 1.0 if filename.startswith(query) else 0.5
            f['relevance_score'] = score
            results.append(f)
    
    # Filter by type if specified
    if file_type:
        type_map = {
            'images': ['image/'],
            'documents': ['application/pdf', 'application/msword', 'text/'],
            'text': ['text/'],
            'videos': ['video/'],
        }
        prefixes = type_map.get(file_type, [])
        if prefixes:
            results = [f for f in results 
                      if any(f.get('type', '').startswith(p) for p in prefixes)]
    
    # Sort by relevance
    results.sort(key=lambda x: x.get('relevance_score', 0), reverse=True)
    
    return jsonify({
        'results': results,
        'total': len(results),
        'query': query
    })


@app.route('/api/v1/folders', methods=['POST'])
def create_folder():
    """Create a new folder."""
    data = request.get_json()
    folder_name = data.get('name', '').strip()
    parent_path = data.get('parent_path', 'root')
    
    if not folder_name:
        return jsonify({
            'error': 'INVALID_NAME',
            'message': 'Folder name is required'
        }), 400
    
    folder_name = secure_filename(folder_name)
    
    if parent_path == 'root':
        full_path = folder_name
    else:
        full_path = f"{parent_path}/{folder_name}"
    
    metadata = load_metadata()
    
    if full_path in metadata['folders']:
        return jsonify({
            'error': 'EXISTS',
            'message': 'Folder already exists'
        }), 409
    
    # Create physical directory
    folder_dir = os.path.join(UPLOAD_DIR, full_path)
    Path(folder_dir).mkdir(parents=True, exist_ok=True)
    
    metadata['folders'].append(full_path)
    save_metadata(metadata)
    
    return jsonify({
        'name': folder_name,
        'path': full_path
    }), 201


@app.route('/api/v1/batch/download', methods=['POST'])
def batch_download():
    """Download multiple files as ZIP archive."""
    data = request.get_json()
    file_ids = data.get('file_ids', [])
    
    if not file_ids:
        return jsonify({
            'error': 'NO_FILES',
            'message': 'No files selected for download'
        }), 400
    
    if len(file_ids) > 100:
        return jsonify({
            'error': 'TOO_MANY_FILES',
            'message': 'Maximum 100 files per batch download'
        }), 400
    
    metadata = load_metadata()
    
    # Create ZIP in memory
    memory_file = BytesIO()
    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
        total_size = 0
        for file_id in file_ids:
            if file_id in metadata.get('files', {}):
                file_info = metadata['files'][file_id]
                file_path = file_info['file_path']
                
                if os.path.exists(file_path):
                    total_size += file_info.get('size', 0)
                    
                    # Check size limit (1GB)
                    if total_size > 1024 * 1024 * 1024:
                        return jsonify({
                            'error': 'SIZE_LIMIT',
                            'message': 'Total size exceeds 1GB limit'
                        }), 400
                    
                    zf.write(file_path, file_info['filename'])
    
    memory_file.seek(0)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    return send_file(
        memory_file,
        mimetype='application/zip',
        as_attachment=True,
        download_name=f'files_{timestamp}.zip'
    )


@app.route('/api/v1/batch/delete', methods=['POST'])
def batch_delete():
    """Delete multiple files at once (moves to trash for recovery)."""
    data = request.get_json()
    file_ids = data.get('file_ids', [])
    
    if not file_ids:
        return jsonify({
            'error': 'NO_FILES',
            'message': 'No files selected for deletion'
        }), 400
    
    metadata = load_metadata()
    deleted = []
    errors = []
    
    for file_id in file_ids:
        if file_id in metadata.get('files', {}):
            file_info = metadata['files'][file_id]
            file_path = file_info['file_path']
            
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                
                # Move to trash for recovery
                move_to_trash(file_id, file_info)
                
                del metadata['files'][file_id]
                deleted.append(file_id)
            except Exception as e:
                errors.append({'id': file_id, 'error': str(e)})
        else:
            errors.append({'id': file_id, 'error': 'Not found'})
    
    save_metadata(metadata)
    
    return jsonify({
        'deleted': deleted,
        'errors': errors,
        'total_deleted': len(deleted),
        'message': f'{len(deleted)} file(s) deleted. Click "Undo" to recover.'
    })


@app.route('/api/v1/files/<file_id>/restore', methods=['POST'])
def restore_file(file_id):
    """Restore a deleted file from trash."""
    success = restore_from_trash(file_id)
    
    if not success:
        trash = load_trash()
        if file_id in trash.get('deleted_files', {}):
            return jsonify({
                'error': 'TRASH_EXPIRED',
                'message': 'File recovery period expired (24 hours). File permanently deleted.'
            }), 410
        else:
            return jsonify({
                'error': 'NOT_IN_TRASH',
                'message': 'File not found in trash'
            }), 404
    
    return jsonify({
        'id': file_id,
        'message': 'File restored successfully'
    }), 200


@app.route('/api/v1/batch/restore', methods=['POST'])
def batch_restore():
    """Restore multiple deleted files from trash."""
    data = request.get_json()
    file_ids = data.get('file_ids', [])
    
    if not file_ids:
        return jsonify({
            'error': 'NO_FILES',
            'message': 'No files selected for recovery'
        }), 400
    
    restored = []
    errors = []
    
    for file_id in file_ids:
        success = restore_from_trash(file_id)
        if success:
            restored.append(file_id)
        else:
            trash = load_trash()
            if file_id in trash.get('deleted_files', {}):
                errors.append({
                    'id': file_id,
                    'error': 'TRASH_EXPIRED',
                    'message': 'Recovery period expired'
                })
            else:
                errors.append({
                    'id': file_id,
                    'error': 'NOT_IN_TRASH',
                    'message': 'File not found in trash'
                })
    
    return jsonify({
        'restored': restored,
        'errors': errors,
        'total_restored': len(restored)
    }), 200


@app.route('/api/v1/trash', methods=['GET'])
def get_trash():
    """Get list of deleted files in trash."""
    trash = load_trash()
    deleted_files = trash.get('deleted_files', {})
    
    # Filter out expired entries and format response
    now = datetime.now(timezone.utc)
    files = []
    expired_ids = []
    
    for file_id, entry in deleted_files.items():
        expires_at = datetime.fromisoformat(entry['expires_at'])
        if now > expires_at:
            expired_ids.append(file_id)
            continue
        
        file_info = entry['file_info']
        files.append({
            'id': file_id,
            'filename': file_info.get('filename', 'Unknown'),
            'size': file_info.get('size', 0),
            'size_formatted': file_info.get('size_formatted', '0 B'),
            'type': file_info.get('type', ''),
            'icon': file_info.get('icon', 'file'),
            'deleted_at': entry['deleted_at'],
            'expires_at': entry['expires_at']
        })
    
    # Clean up expired entries
    if expired_ids:
        for file_id in expired_ids:
            del deleted_files[file_id]
        save_trash(trash)
    
    # Sort by deletion time (newest first)
    files.sort(key=lambda x: x['deleted_at'], reverse=True)
    
    return jsonify({
        'files': files,
        'total': len(files)
    })


@app.route('/api/v1/trash', methods=['DELETE'])
def empty_trash():
    """Permanently delete all files in trash."""
    trash = load_trash()
    deleted_files = trash.get('deleted_files', {})
    
    # Delete physical files
    deleted_count = 0
    for file_id, entry in deleted_files.items():
        file_info = entry.get('file_info', {})
        file_path = file_info.get('file_path')
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
                deleted_count += 1
            except Exception:
                pass
    
    # Clear trash
    trash['deleted_files'] = {}
    save_trash(trash)
    
    return jsonify({
        'message': f'Permanently deleted {deleted_count} file(s)',
        'deleted_count': deleted_count
    })


@app.route('/api/v1/trash/<file_id>', methods=['DELETE'])
def permanently_delete_file(file_id):
    """Permanently delete a specific file from trash."""
    trash = load_trash()
    
    if file_id not in trash.get('deleted_files', {}):
        return jsonify({
            'error': 'NOT_FOUND',
            'message': 'File not found in trash'
        }), 404
    
    entry = trash['deleted_files'][file_id]
    file_info = entry.get('file_info', {})
    file_path = file_info.get('file_path')
    
    # Delete physical file
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except Exception as e:
            return jsonify({
                'error': 'DELETE_FAILED',
                'message': str(e)
            }), 500
    
    # Remove from trash
    del trash['deleted_files'][file_id]
    save_trash(trash)
    
    return jsonify({
        'message': 'File permanently deleted',
        'id': file_id
    })


@app.route('/api/v1/stats', methods=['GET'])
def get_stats():
    """Get platform statistics."""
    metadata = load_metadata()
    files = list(metadata.get('files', {}).values())
    
    total_size = sum(f.get('size', 0) for f in files)
    
    # Count by type
    type_counts = {}
    for f in files:
        icon = f.get('icon', 'file')
        type_counts[icon] = type_counts.get(icon, 0) + 1
    
    return jsonify({
        'total_files': len(files),
        'total_size': total_size,
        'total_size_formatted': format_file_size(total_size),
        'total_folders': len(metadata.get('folders', [])),
        'type_breakdown': type_counts,
        'disk_space': get_disk_usage()
    })


@app.route('/api/v1/settings', methods=['GET'])
def get_settings():
    """Get application settings."""
    settings = load_settings()
    return jsonify(settings)


@app.route('/api/v1/settings', methods=['PUT'])
def update_settings():
    """Update application settings."""
    data = request.get_json()
    settings = load_settings()
    
    if 'upload_dir' in data:
        new_upload_dir = data['upload_dir']
        if new_upload_dir and os.path.isabs(new_upload_dir):
            Path(new_upload_dir).mkdir(parents=True, exist_ok=True)
            settings['upload_dir'] = new_upload_dir
    
    if 'download_dir' in data:
        settings['download_dir'] = data['download_dir']
    
    if 'theme' in data and data['theme'] in ['dark', 'light']:
        settings['theme'] = data['theme']
    
    save_settings(settings)
    return jsonify(settings)


@app.route('/api/v1/files/<file_id>/download/compressed', methods=['GET'])
def download_compressed_file(file_id):
    """Download a file with optional compression."""
    metadata = load_metadata()
    
    if file_id not in metadata.get('files', {}):
        return jsonify({'error': 'NOT_FOUND', 'message': 'File not found'}), 404
    
    file_info = metadata['files'][file_id]
    file_path = file_info['file_path']
    
    if not os.path.exists(file_path):
        return jsonify({'error': 'NOT_FOUND', 'message': 'File not found on disk'}), 404
    
    quality = request.args.get('quality', 80, type=int)
    quality = max(10, min(100, quality))
    
    mime_type = file_info.get('type', '')
    filename = file_info['filename']
    
    if mime_type.startswith('image/') and PILLOW_AVAILABLE:
        try:
            img = Image.open(file_path)
            output = BytesIO()
            
            if mime_type == 'image/png':
                if img.mode in ('RGBA', 'LA', 'P'):
                    img = img.convert('RGBA')
                else:
                    img = img.convert('RGB')
                compress_level = int((100 - quality) / 10)
                img.save(output, format='PNG', optimize=True, compress_level=compress_level)
            elif mime_type in ('image/jpeg', 'image/jpg'):
                if img.mode in ('RGBA', 'LA', 'P'):
                    img = img.convert('RGB')
                img.save(output, format='JPEG', quality=quality, optimize=True)
            elif mime_type == 'image/gif':
                img.save(output, format='GIF', optimize=True)
            else:
                if img.mode in ('RGBA', 'LA', 'P'):
                    img = img.convert('RGB')
                img.save(output, format='JPEG', quality=quality, optimize=True)
                filename = os.path.splitext(filename)[0] + '.jpg'
            
            output.seek(0)
            return send_file(
                output,
                mimetype=mime_type,
                as_attachment=True,
                download_name=filename
            )
        except Exception as e:
            return send_file(file_path, as_attachment=True, download_name=filename)
    
    elif mime_type == 'application/pdf' and PYPDF2_AVAILABLE:
        try:
            reader = PdfReader(file_path)
            writer = PdfWriter()
            
            for page in reader.pages:
                writer.add_page(page)
            
            output = BytesIO()
            writer.write(output)
            output.seek(0)
            
            return send_file(
                output,
                mimetype='application/pdf',
                as_attachment=True,
                download_name=filename
            )
        except Exception as e:
            return send_file(file_path, as_attachment=True, download_name=filename)
    
    return send_file(file_path, as_attachment=True, download_name=filename)


@app.route('/api/v1/compression/support', methods=['GET'])
def get_compression_support():
    """Get information about supported compression formats."""
    return jsonify({
        'image_compression': PILLOW_AVAILABLE,
        'pdf_compression': PYPDF2_AVAILABLE,
        'supported_formats': {
            'images': ['png', 'jpg', 'jpeg', 'gif'] if PILLOW_AVAILABLE else [],
            'documents': ['pdf'] if PYPDF2_AVAILABLE else []
        }
    })


# Error handlers
@app.errorhandler(413)
def request_entity_too_large(error):
    return jsonify({
        'error': 'FILE_TOO_LARGE',
        'message': f'File exceeds maximum size of {format_file_size(MAX_FILE_SIZE)}'
    }), 413


@app.errorhandler(404)
def not_found(error):
    return jsonify({
        'error': 'NOT_FOUND',
        'message': 'Resource not found'
    }), 404


@app.errorhandler(500)
def internal_error(error):
    return jsonify({
        'error': 'SERVER_ERROR',
        'message': 'An internal error occurred'
    }), 500


# Configure app
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE


if __name__ == '__main__':
    host = os.environ.get('SERVER_HOST', '0.0.0.0')
    port = int(os.environ.get('SERVER_PORT', 8000))
    debug = os.environ.get('DEBUG', 'false').lower() == 'true'
    
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║           LAN File-Sharing Platform v1.0.0                   ║
╠══════════════════════════════════════════════════════════════╣
║  Server running at: http://{host}:{port:<24}      ║
║  Upload directory:  {UPLOAD_DIR:<38} ║
║  Max file size:     {format_file_size(MAX_FILE_SIZE):<38} ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    app.run(host=host, port=port, debug=debug, threaded=True)

