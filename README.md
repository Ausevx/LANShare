# LAN File-Sharing Platform

A lightweight, self-hosted file-sharing solution for local networks. Share files quickly and securely within your LAN without any cloud services.

![Platform Preview](https://img.shields.io/badge/Platform-Cross--Platform-brightgreen)
![Python](https://img.shields.io/badge/Python-3.9+-blue)
![Docker](https://img.shields.io/badge/Docker-Ready-blue)
![License](https://img.shields.io/badge/License-MIT-green)

## Features

- **Drag & Drop Upload** - Simply drag files or folders onto the page to upload
- **Folder Upload Support** - Upload entire folder structures with preserved hierarchy
- **Multiple Files** - Upload multiple files at once with batch processing
- **Real-time Progress** - Visual upload progress with cancel support
- **Dark/Light Theme** - Toggle between dark and light modes
- **File Preview** - Preview images, PDFs, and text files directly in browser
- **File Compression** - Compress images and PDFs on download with adjustable quality
- **Batch Operations** - Download multiple files as ZIP or delete in batch
- **Undo Delete** - Recover accidentally deleted files within 24 hours
- **Search & Filter** - Find files by name, filter by type (Images, Docs, Videos, etc.)
- **Settings Menu** - Configure application preferences
- **QR Code Sharing** - Scan QR code to connect from mobile devices
- **LAN Only** - Files stay within your local network for privacy
- **Zero Configuration** - Single command deployment

## Quick Start

### Option 1: Docker (Recommended)

```bash
# Clone or download the project
chmod +x run.sh
./run.sh --docker
```

### Option 2: Python

```bash
chmod +x run.sh
./run.sh --python
```

### Windows

```cmd
run.bat
```

The platform will automatically detect whether to use Docker or Python.

## Manual Setup

### Using Docker

```bash
# Build and run
docker build -t fileshare:latest .
docker run -d -p 8000:8000 -v ./uploads:/app/uploads --name fileshare-server fileshare:latest

# Or use Docker Compose
docker-compose up -d
```

### Using Python

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate    # Windows

# Install dependencies
pip install -r requirements.txt

# Run
python app.py
```

## Access the Platform

Once running, access the platform at:
- **Local**: http://localhost:8000
- **Network**: http://YOUR_LOCAL_IP:8000

Share the network URL with other devices on your LAN to enable file sharing.

## Configuration

Environment variables can be set to customize the platform:

| Variable | Default | Description |
|----------|---------|-------------|
| `SERVER_HOST` | `0.0.0.0` | Server bind address |
| `SERVER_PORT` | `8000` | Server port |
| `UPLOAD_DIR` | `./uploads` | File storage directory |
| `MAX_FILE_SIZE` | `536870912` | Max file size in bytes (500MB) |
| `ALLOWED_EXTENSIONS` | Various | Comma-separated list of allowed extensions |

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Web interface |
| `GET` | `/health` | Health check |
| `POST` | `/api/v1/upload` | Upload file |
| `GET` | `/api/v1/files` | List files |
| `GET` | `/api/v1/files/{id}/download` | Download file |
| `GET` | `/api/v1/files/{id}/preview` | Preview file |
| `DELETE` | `/api/v1/files/{id}` | Delete file |
| `PATCH` | `/api/v1/files/{id}/rename` | Rename file |
| `GET` | `/api/v1/search` | Search files |
| `POST` | `/api/v1/batch/download` | Batch download as ZIP |
| `POST` | `/api/v1/batch/delete` | Batch delete |
| `GET` | `/api/v1/stats` | Platform statistics |
| `GET/PUT` | `/api/v1/settings` | Get/update settings |
| `GET` | `/api/v1/files/{id}/download/compressed` | Download with compression |
| `GET` | `/api/v1/browse` | Browse server directories |

## Supported File Types

- **Documents**: PDF, DOC, DOCX, TXT, MD
- **Spreadsheets**: CSV, XLS, XLSX
- **Presentations**: PPT, PPTX
- **Images**: PNG, JPG, JPEG, GIF
- **Audio**: MP3, WAV
- **Video**: MP4, AVI, MOV
- **Archives**: ZIP, TAR, GZ
- **Data**: JSON

## Project Structure

```
file-sharing/
├── app.py              # Flask backend
├── templates/
│   └── index.html      # Web UI
├── uploads/            # File storage (created on first run)
├── Dockerfile          # Docker configuration
├── docker-compose.yml  # Docker Compose setup
├── requirements.txt    # Python dependencies
├── run.sh              # Linux/macOS setup script
├── run.bat             # Windows setup script
└── README.md           # This file
```

## Docker Commands

```bash
# View logs
docker logs -f fileshare-server

# Stop server
docker stop fileshare-server

# Restart server
docker restart fileshare-server

# Rebuild image
docker build -t fileshare:latest .
```

## Troubleshooting

### Port already in use
```bash
# Use a different port
./run.sh --port 3000
# or
PORT=3000 docker-compose up -d
```

### Permission denied on uploads
```bash
# Fix permissions
chmod 777 uploads/
```

### Can't access from other devices
- Ensure firewall allows port 8000
- Verify devices are on the same network
- Use the network IP, not localhost

## Security Considerations

- This platform is designed for **LAN use only**
- Files are stored unencrypted on disk
- No authentication by default
- Do not expose to the public internet

## License

MIT License - feel free to use and modify for your needs.

