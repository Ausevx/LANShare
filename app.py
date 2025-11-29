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
    """Handle file upload with support for chunked uploads."""
    if 'file' not in request.files:
        return jsonify({
            'error': 'NO_FILE',
            'message': 'No file provided in request'
        }), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({
            'error': 'EMPTY_FILENAME',
            'message': 'No file selected'
        }), 400
    
    if not allowed_file(file.filename):
        return jsonify({
            'error': 'INVALID_TYPE',
            'message': f'File type not allowed. Allowed types: {", ".join(ALLOWED_EXTENSIONS)}'
        }), 400
    
    # Get folder path from request
    folder_path = request.form.get('folder_path', 'root')
    
    # Generate unique file ID
    file_id = str(uuid.uuid4())
    
    # Secure the filename
    original_filename = file.filename
    safe_filename = secure_filename(original_filename)
    
    # Handle duplicate filenames
    metadata = load_metadata()
    existing_files = [f['filename'] for f in metadata['files'].values() 
                      if f.get('folder_path') == folder_path]
    
    if safe_filename in existing_files:
        name, ext = os.path.splitext(safe_filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        safe_filename = f"{name}_{timestamp}{ext}"
    
    # Create folder structure if needed
    folder_dir = os.path.join(UPLOAD_DIR, folder_path) if folder_path != 'root' else UPLOAD_DIR
    Path(folder_dir).mkdir(parents=True, exist_ok=True)
    
    # Save file
    file_path = os.path.join(folder_dir, f"{file_id}_{safe_filename}")
    file.save(file_path)
    
    # Get file info
    file_size = os.path.getsize(file_path)
    mime_type, _ = mimetypes.guess_type(safe_filename)
    
    # Check file size
    if file_size > MAX_FILE_SIZE:
        os.remove(file_path)
        return jsonify({
            'error': 'FILE_TOO_LARGE',
            'message': f'File exceeds maximum size of {format_file_size(MAX_FILE_SIZE)}'
        }), 413
    
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
    
    save_metadata(metadata)
    
    return jsonify({
        'id': file_id,
        'filename': safe_filename,
        'size': file_size,
        'size_formatted': format_file_size(file_size),
        'type': mime_type,
        'icon': file_metadata['icon'],
        'upload_date': file_metadata['upload_date'],
        'url': f'/api/v1/files/{file_id}/download'
    }), 201


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
    """Delete a specific file."""
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
        os.remove(file_path)
    
    # Remove from metadata
    del metadata['files'][file_id]
    save_metadata(metadata)
    
    return '', 204


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
    """Delete multiple files at once."""
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
        'total_deleted': len(deleted)
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

