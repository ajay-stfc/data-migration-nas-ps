# Data Migration API

FastAPI wrapper around rsync for delta copy between folders.

## Clone

```bash
git clone https://github.com/ajay-stfc/data-migration-nas-ps.git
cd data-migration-nas-ps
```

## Quick Start

### Docker

```bash
cp .env.example .env
mkdir -p source destination
docker-compose up -d --build
```

API: http://localhost:8000
Docs: http://localhost:8000/docs

### Local

```bash
cp .env.example .env
pip install -r requirements.txt
python main.py
```

## Configuration

Edit `.env` file:
```
SOURCE_DIR=/app/source
DESTINATION_DIR=/app/destination
```

## API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/sync` | POST | Start sync (background) |
| `/status` | GET | Folder stats + sync progress |
| `/health` | GET | Health check |
| `/docs` | GET | Swagger UI |

## Usage

```bash
# Start sync
curl -X POST http://localhost:8000/sync

# Check progress
curl http://localhost:8000/status

# Health check
curl http://localhost:8000/health
```

## API Responses

### POST /sync
```json
{
  "status": "started",
  "message": "Sync started in background",
  "timestamp": "2025-11-27T10:30:00",
  "source_path": "/app/source",
  "destination_path": "/app/destination"
}
```

### GET /status (during sync)
```json
{
  "source": {"path": "/app/source", "files": 100, "total_size_mb": 50},
  "destination": {"path": "/app/destination", "files": 45, "total_size_mb": 22},
  "sync": {
    "is_running": true,
    "progress": {
      "status": "running",
      "started_at": "2025-11-27T10:30:00",
      "current_file": "data/file.txt",
      "files_completed": 45,
      "total_files": 100,
      "percentage": 45
    },
    "last_sync": null
  },
  "disk_space": {"free_gb": 50.0},
  "rsync_available": true
}
```

### GET /status (after sync)
```json
{
  "source": {"path": "/app/source", "files": 100, "total_size_mb": 50},
  "destination": {"path": "/app/destination", "files": 100, "total_size_mb": 50},
  "sync": {
    "is_running": false,
    "progress": null,
    "last_sync": {
      "status": "success",
      "message": "Sync completed",
      "timestamp": "2025-11-27T10:32:00",
      "files_transferred": 100,
      "warnings": null
    }
  },
  "disk_space": {"free_gb": 50.0},
  "rsync_available": true
}
```

## Features

- Delta sync (only changed files transferred)
- Resume interrupted transfers
- Real-time progress tracking
- Background sync with status polling

## Docker Commands

```bash
docker-compose up -d        # Start
docker-compose down         # Stop
docker-compose logs -f      # Logs
docker-compose restart      # Restart
```

## Requirements

- Python 3.8+
- rsync
