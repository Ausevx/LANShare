# LANShare - Technical Documentation

## Overview

LANShare is a lightweight, self-hosted file sharing solution designed for local networks. It enables seamless file transfer between devices on the same LAN without requiring internet connectivity or third-party services. The application provides a modern web interface accessible from any device with a browser, making it ideal for home networks, offices, or any environment where quick local file sharing is needed.

---

## Technology Stack

### Flask (Python Web Framework)

Flask serves as the backend framework powering the API and server-side logic. It handles:

- **Routing** - Defines all API endpoints and serves the web interface
- **File Operations** - Manages file uploads, downloads, and storage
- **Request Processing** - Validates incoming requests and returns JSON responses
- **Static File Serving** - Delivers the HTML template and handles file streaming

### Tailwind CSS

A utility-first CSS framework used to build the responsive user interface:

- Provides consistent styling through utility classes
- Enables rapid UI development with pre-built design tokens
- Supports dark/light mode theming via CSS class toggling
- Handles responsive breakpoints for mobile, tablet, and desktop layouts

### QRCode.js

A JavaScript library for generating QR codes client-side:

- Creates QR codes containing the server's LAN URL
- Enables quick device connection by scanning the QR code
- No server-side processing required for QR generation

### Docker

Containerization platform for consistent deployment:

- Packages the application with all dependencies
- Ensures consistent behavior across different host systems
- Simplifies deployment with `docker-compose` configuration
- Isolates the application environment from the host

### Python

Core programming language for backend logic:

- File system operations and metadata management
- JSON-based metadata storage for file information
- Network utilities for IP detection and hostname resolution
- Utility functions for file size formatting and type detection

### HTML5/JavaScript

Frontend interface built with modern web standards:

- **Drag-and-Drop API** - Native file dropping support for uploads
- **Fetch API** - Asynchronous communication with the backend
- **File API** - Client-side file handling before upload
- **LocalStorage** - Persists user preferences (theme, view mode)

---

## Key Features

### File Upload with Drag-and-Drop Support

Users can upload files and folders by:
- Dragging files or folders directly onto the drop zone
- Clicking the upload area to open a file browser
- Dropping files anywhere on the page for global upload support
- Shift+clicking the upload area to toggle between folder and file selection modes

The upload system features:
- **Multiple file uploads**: Process up to 10 files per batch automatically
- **Folder structure preservation**: Nested folders maintain their hierarchy in storage
- **Real-time progress tracking**: Visual feedback for upload completion
- **Batch error handling**: Individual error reporting per file with summary statistics

### QR Code Sharing for Easy LAN Access

When clicking the "Connect" button, a modal displays:
- The server's local IP address and port
- A QR code that mobile devices can scan
- One-click URL copying to clipboard

This eliminates the need to manually type IP addresses on other devices.

### File Preview and Management

The application supports previewing various file types:
- **Images** - Direct inline preview (PNG, JPEG, GIF)
- **Text Files** - Content display for plain text, JSON, Markdown
- **PDFs** - Browser-native PDF viewer integration

File management operations include renaming and deleting with confirmation modals.

### Batch Operations

Efficiently handle multiple files at once:
- **Download as ZIP** - Select multiple files and download as a single ZIP archive
- **Bulk Delete** - Remove multiple files with a single confirmation
- Selection mode with visual feedback for chosen files

### Responsive Design

The interface adapts to different screen sizes:
- Mobile-first design approach
- Collapsible navigation and filters on small screens
- Touch-friendly buttons and gestures
- Grid/list view toggle for optimal display

### Light/Dark Mode Toggle

User preference for visual theme:
- Dark mode (default) for reduced eye strain
- Light mode for bright environments
- Preference saved to server and persisted across sessions
- Instant switching without page reload

### Settings Menu

Configurable application preferences:
- **Upload Directory**: Set where files are stored on the server
- **Download Directory**: Set preferred download location hint
- **Directory Browser**: Visual folder picker to navigate and select directories
- Settings persist across sessions via server-side storage

### Undo Delete (Trash Recovery)

When files are deleted, they are moved to a temporary trash instead of permanent deletion:

1. **Deletion Process**: Files moved to `.trash.json` with metadata
2. **Recovery Window**: 24 hours to recover deleted files
3. **Automatic Cleanup**: Expired trash entries are cleaned up after 24 hours
4. **Single & Batch**: Works for both individual file delete and batch delete operations
5. **UI Integration**: Delete confirmation modal shows undo button after deletion

**Implementation Details**:
- Trash stored in `.trash.json` alongside metadata
- Each trash entry contains: file info, deletion timestamp, expiration timestamp
- Restoration only requires re-adding to metadata (physical file never deleted)
- Expired recovery periods automatically prevent restoration attempts

### File Compression for PDFs and Images

Download optimization for supported files:

---

## File Compression Feature

The compression feature provides on-demand file optimization for downloads:

### Supported File Types

- **Images**: PNG, JPEG, GIF
- **Documents**: PDF

### How It Works

1. **User Selection**: When downloading an image or PDF, users can choose to enable compression
2. **Compression Ratio**: A slider allows selecting the quality vs. file size tradeoff (higher compression = smaller file, lower quality)
3. **On-the-Fly Processing**: Compression is applied during the download request, not to stored files
4. **Original Preservation**: Source files are never modified; compression only affects the downloaded copy

### Technical Implementation

- **Image Compression**: Uses the Pillow (PIL) library to adjust JPEG quality or reduce PNG color depth
- **PDF Compression**: Reduces embedded image quality within PDF documents while preserving text clarity
- **Streaming Response**: Compressed files are streamed directly to the client without temporary storage

### Multi-File & Folder Upload Implementation

The upload endpoint handles multiple files efficiently:

1. **Request Format**: Files are sent as multipart form data with `files[]` field
2. **Path Preservation**: When uploading folders via `webkitdirectory`, full paths are preserved:
   - `folder/subfolder/file.txt` → creates nested folder structure
   - File paths are normalized to work across operating systems
3. **Batch Processing**: Files are processed in batches of 10 to manage memory efficiently
4. **Error Handling**: Individual file errors are collected and reported separately:
   - Invalid file types skip gracefully without blocking other files
   - File size violations are caught and reported per-file
   - Folder creation failures are handled with fallback messaging
5. **Response Format**:
   ```json
   {
     "uploaded": [
       { "id": "uuid", "filename": "file.txt", "size": 1024, ... }
     ],
     "errors": [
       { "filename": "bad.exe", "error": "INVALID_TYPE", "message": "..." }
     ],
     "total_uploaded": 1,
     "total_errors": 1
   }
   ```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Serves the main web interface |
| `GET` | `/health` | Health check with server status and statistics |
| `GET` | `/api/v1/connection` | Returns server IP, port, and connection URL |
| `POST` | `/api/v1/upload` | Upload multiple files with folder support |
| `GET` | `/api/v1/files` | List files with optional filtering and sorting |
| `GET` | `/api/v1/files/<id>/download` | Download a specific file |
| `GET` | `/api/v1/files/<id>/preview` | Get file preview (images, text, PDFs) |
| `DELETE` | `/api/v1/files/<id>` | Delete a specific file (moves to trash) |
| `POST` | `/api/v1/files/<id>/restore` | Restore a deleted file from trash |
| `PATCH` | `/api/v1/files/<id>/rename` | Rename a file |
| `GET` | `/api/v1/search` | Search files by name |
| `POST` | `/api/v1/folders` | Create a new folder |
| `POST` | `/api/v1/batch/download` | Download multiple files as ZIP |
| `POST` | `/api/v1/batch/delete` | Delete multiple files (moves to trash) |
| `POST` | `/api/v1/batch/restore` | Restore multiple deleted files |
| `GET` | `/api/v1/stats` | Get platform statistics |
| `GET` | `/api/v1/settings` | Get application settings |
| `PUT` | `/api/v1/settings` | Update application settings |
| `GET` | `/api/v1/files/<id>/download/compressed` | Download compressed file with quality parameter |
| `GET` | `/api/v1/compression/support` | Check available compression capabilities |
| `GET` | `/api/v1/browse` | Browse server directories for folder selection |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Client Browser                            │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────────┐  │
│  │  HTML/CSS   │  │  JavaScript  │  │  QRCode.js + Tailwind  │  │
│  └─────────────┘  └──────────────┘  └────────────────────────┘  │
└───────────────────────────┬─────────────────────────────────────┘
                            │ HTTP (REST API)
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Flask Application                           │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────────┐  │
│  │   Routes    │  │  File Logic  │  │   Metadata Manager     │  │
│  └─────────────┘  └──────────────┘  └────────────────────────┘  │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                       File System                                │
│  ┌─────────────────────┐  ┌────────────────────────────────────┐│
│  │   uploads/          │  │   .metadata.json                   ││
│  │   ├── file1.pdf     │  │   (File index and metadata store)  ││
│  │   ├── file2.png     │  │                                    ││
│  │   └── ...           │  │                                    ││
│  └─────────────────────┘  └────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

### Data Flow

1. **Upload**: Client sends file via multipart form → Flask validates and saves to `uploads/` → Metadata stored in `.metadata.json`
2. **Download**: Client requests file by ID → Flask reads metadata → Streams file from disk
3. **List/Search**: Client queries API → Flask reads metadata → Returns filtered JSON response
4. **Delete**: Client sends delete request → Flask removes file from disk → Updates metadata

### Storage

- Files are stored in the `uploads/` directory with UUID-prefixed names
- Metadata is persisted in `.metadata.json` for quick lookups without filesystem scanning
- Folder structure is preserved within the uploads directory
