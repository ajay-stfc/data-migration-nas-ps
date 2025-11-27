# Delta Migration API

FastAPI wrapper around rsync for delta copy between folders.

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

## Status Response

```json
{
  "source": {"path": "/app/source", "files": 100, "total_size_mb": 50},
  "destination": {"path": "/app/destination", "files": 100, "total_size_mb": 50},
  "sync": {
    "is_running": true,
    "progress": {
      "status": "running",
      "current_file": "data/file.txt",
      "files_completed": 45,
      "total_files": 100,
      "percentage": 45
    },
    "last_sync": null
  }
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
