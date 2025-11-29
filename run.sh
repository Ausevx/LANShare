#!/bin/bash
# ============================================================================
# LAN File-Sharing Platform - Setup & Run Script
# For Linux and macOS systems
# ============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Default configuration
PORT=${PORT:-8000}
MODE=""
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ============================================================================
# Helper Functions
# ============================================================================

print_banner() {
    echo -e "${CYAN}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║                                                              ║"
    echo "║           ${BOLD}LAN File-Sharing Platform${NC}${CYAN}                         ║"
    echo "║                   v1.0.0                                     ║"
    echo "║                                                              ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_step() {
    echo -e "\n${BOLD}▶ $1${NC}"
}

# ============================================================================
# Utility Functions
# ============================================================================

check_command() {
    command -v "$1" &> /dev/null
}

get_local_ip() {
    # Try different methods to get local IP
    local ip=""
    
    if check_command ip; then
        ip=$(ip route get 1 2>/dev/null | awk '{print $7; exit}')
    fi
    
    if [ -z "$ip" ] && check_command ifconfig; then
        ip=$(ifconfig 2>/dev/null | grep -Eo 'inet (addr:)?([0-9]*\.){3}[0-9]*' | grep -Eo '([0-9]*\.){3}[0-9]*' | grep -v '127.0.0.1' | head -n1)
    fi
    
    if [ -z "$ip" ]; then
        ip=$(hostname -I 2>/dev/null | awk '{print $1}')
    fi
    
    if [ -z "$ip" ]; then
        ip="localhost"
    fi
    
    echo "$ip"
}

cleanup() {
    if [ -n "$PYTHON_PID" ]; then
        print_status "Shutting down server..."
        kill "$PYTHON_PID" 2>/dev/null || true
    fi
}

trap cleanup EXIT

# ============================================================================
# Docker Functions
# ============================================================================

check_docker() {
    if check_command docker; then
        if docker info &> /dev/null; then
            return 0
        else
            print_warning "Docker is installed but not running"
            return 1
        fi
    fi
    return 1
}

run_docker() {
    print_step "Starting with Docker..."
    
    # Create necessary directories
    mkdir -p "$SCRIPT_DIR/uploads" "$SCRIPT_DIR/logs"
    
    # Check if container already exists
    if docker ps -a --format '{{.Names}}' | grep -q '^fileshare-server$'; then
        print_status "Stopping existing container..."
        docker stop fileshare-server &> /dev/null || true
        docker rm fileshare-server &> /dev/null || true
    fi
    
    # Check if image exists, build if not
    if ! docker images --format '{{.Repository}}:{{.Tag}}' | grep -q '^fileshare:latest$'; then
        print_status "Building Docker image..."
        docker build -t fileshare:latest "$SCRIPT_DIR"
    else
        print_status "Using existing Docker image"
        print_status "To rebuild, run: docker build -t fileshare:latest ."
    fi
    
    # Run container
    print_status "Starting container..."
    docker run -d \
        --name fileshare-server \
        -p "$PORT:8000" \
        -v "$SCRIPT_DIR/uploads:/app/uploads" \
        -e SERVER_PORT=8000 \
        -e MAX_FILE_SIZE=536870912 \
        --restart unless-stopped \
        fileshare:latest
    
    # Wait for container to be healthy
    print_status "Waiting for service to start..."
    local max_attempts=30
    local attempt=0
    
    while [ $attempt -lt $max_attempts ]; do
        if curl -s "http://localhost:$PORT/health" &> /dev/null; then
            break
        fi
        sleep 1
        attempt=$((attempt + 1))
    done
    
    if [ $attempt -eq $max_attempts ]; then
        print_error "Service failed to start. Check logs with: docker logs fileshare-server"
        exit 1
    fi
    
    local_ip=$(get_local_ip)
    
    echo ""
    print_success "Server is running!"
    echo ""
    echo -e "${CYAN}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║${NC}  ${GREEN}Local Access:${NC}     http://localhost:$PORT                    ${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}  ${GREEN}Network Access:${NC}   http://$local_ip:$PORT                    ${CYAN}║${NC}"
    echo -e "${CYAN}╠══════════════════════════════════════════════════════════════╣${NC}"
    echo -e "${CYAN}║${NC}  ${YELLOW}Commands:${NC}                                                   ${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}    Stop:    docker stop fileshare-server                     ${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}    Logs:    docker logs -f fileshare-server                  ${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}    Restart: docker restart fileshare-server                  ${CYAN}║${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

# ============================================================================
# Python Functions
# ============================================================================

check_python() {
    if check_command python3; then
        local version=$(python3 --version 2>&1 | awk '{print $2}')
        local major=$(echo "$version" | cut -d. -f1)
        local minor=$(echo "$version" | cut -d. -f2)
        
        if [ "$major" -ge 3 ] && [ "$minor" -ge 9 ]; then
            return 0
        else
            print_warning "Python $version found, but 3.9+ is recommended"
            return 0
        fi
    fi
    return 1
}

setup_venv() {
    local venv_dir="$SCRIPT_DIR/.venv"
    
    if [ ! -d "$venv_dir" ]; then
        print_status "Creating virtual environment..."
        python3 -m venv "$venv_dir"
    fi
    
    print_status "Activating virtual environment..."
    source "$venv_dir/bin/activate"
    
    print_status "Installing dependencies..."
    pip install --upgrade pip -q
    pip install -r "$SCRIPT_DIR/requirements.txt" -q
}

run_python() {
    print_step "Starting with Python..."
    
    # Create necessary directories
    mkdir -p "$SCRIPT_DIR/uploads" "$SCRIPT_DIR/logs"
    
    # Setup virtual environment
    setup_venv
    
    local_ip=$(get_local_ip)
    
    echo ""
    print_success "Starting server..."
    echo ""
    echo -e "${CYAN}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║${NC}  ${GREEN}Local Access:${NC}     http://localhost:$PORT                    ${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}  ${GREEN}Network Access:${NC}   http://$local_ip:$PORT                    ${CYAN}║${NC}"
    echo -e "${CYAN}╠══════════════════════════════════════════════════════════════╣${NC}"
    echo -e "${CYAN}║${NC}  ${YELLOW}Press Ctrl+C to stop the server${NC}                             ${CYAN}║${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    
    # Run the server
    cd "$SCRIPT_DIR"
    export SERVER_PORT=$PORT
    export SERVER_HOST=0.0.0.0
    python3 app.py
}

# ============================================================================
# Main Script
# ============================================================================

show_help() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --docker      Force Docker mode"
    echo "  --python      Force Python mode"
    echo "  --port PORT   Set server port (default: 8000)"
    echo "  --build       Rebuild Docker image"
    echo "  --help        Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0                    # Auto-detect best method"
    echo "  $0 --docker           # Use Docker"
    echo "  $0 --python --port 3000  # Use Python on port 3000"
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --docker)
            MODE="docker"
            shift
            ;;
        --python)
            MODE="python"
            shift
            ;;
        --port)
            PORT="$2"
            shift 2
            ;;
        --build)
            if check_docker; then
                print_status "Rebuilding Docker image..."
                docker build -t fileshare:latest "$SCRIPT_DIR"
                print_success "Image rebuilt successfully"
            else
                print_error "Docker is not available"
            fi
            exit 0
            ;;
        --help|-h)
            show_help
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Main execution
print_banner

cd "$SCRIPT_DIR"

if [ "$MODE" = "docker" ]; then
    if check_docker; then
        run_docker
    else
        print_error "Docker is not available or not running"
        exit 1
    fi
elif [ "$MODE" = "python" ]; then
    if check_python; then
        run_python
    else
        print_error "Python 3.9+ is required but not found"
        exit 1
    fi
else
    # Auto-detect mode
    print_step "Detecting best runtime environment..."
    
    if check_docker; then
        print_status "Docker detected - using containerized deployment"
        run_docker
    elif check_python; then
        print_status "Python detected - using native deployment"
        run_python
    else
        print_error "Neither Docker nor Python 3.9+ found!"
        echo ""
        echo "Please install one of the following:"
        echo "  - Docker: https://docs.docker.com/get-docker/"
        echo "  - Python 3.9+: https://www.python.org/downloads/"
        exit 1
    fi
fi

