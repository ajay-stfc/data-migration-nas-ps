"""
Delta Migration API
"""

import logging
import os
import shutil
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, BackgroundTasks

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('delta_migration.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Delta Migration API",
    description="Rsync-based delta copy API",
    version="1.0.0"
)

BASE_DIR = Path(__file__).resolve().parent
SOURCE_DIR = Path(os.getenv("SOURCE_DIR", BASE_DIR / "source"))
DESTINATION_DIR = Path(os.getenv("DESTINATION_DIR", BASE_DIR / "destination"))

sync_state = {
    "is_running": False,
    "progress": None,
    "last_sync": None
}
sync_lock = threading.Lock()


def count_source_files(directory: Path) -> int:
    count = 0
    try:
        for item in directory.rglob('*'):
            if item.is_file():
                count += 1
    except Exception:
        pass
    return count


def check_rsync_available() -> bool:
    return shutil.which("rsync") is not None


def get_disk_space(path: Path) -> Dict[str, int]:
    try:
        stat = shutil.disk_usage(path)
        return {
            "total": stat.total,
            "used": stat.used,
            "free": stat.free,
            "free_gb": round(stat.free / (1024**3), 2)
        }
    except Exception as e:
        logger.error(f"Failed to get disk space: {e}")
        return {"total": 0, "used": 0, "free": 0, "free_gb": 0}


@app.get("/")
async def root():
    return {
        "message": "Delta Migration API",
        "version": "1.0.0",
        "endpoints": {
            "/sync": "POST - Trigger sync",
            "/status": "GET - Check status",
            "/health": "GET - Health check",
            "/docs": "GET - API docs"
        }
    }


@app.get("/health")
async def health_check():
    checks = {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "checks": {
            "rsync_available": check_rsync_available(),
            "source_directory": SOURCE_DIR.exists(),
            "destination_directory": DESTINATION_DIR.exists(),
            "disk_space": get_disk_space(BASE_DIR)
        }
    }

    if not checks["checks"]["rsync_available"]:
        checks["status"] = "unhealthy"
        checks["error"] = "rsync not installed"
    elif not checks["checks"]["source_directory"]:
        checks["status"] = "degraded"
        checks["warning"] = "source directory not found"

    return checks


def run_sync_background():
    global sync_state
    warnings = []

    try:
        total_files = count_source_files(SOURCE_DIR)

        with sync_lock:
            sync_state["is_running"] = True
            sync_state["progress"] = {
                "status": "running",
                "started_at": datetime.now().isoformat(),
                "current_file": None,
                "files_completed": 0,
                "total_files": total_files,
                "percentage": 0
            }

        logger.info(f"Starting sync - {total_files} files to process")

        if not check_rsync_available():
            raise Exception("rsync not installed")

        if not SOURCE_DIR.exists():
            raise Exception(f"Source not found: {SOURCE_DIR}")

        source_empty = False
        try:
            if not any(SOURCE_DIR.iterdir()):
                source_empty = True
        except Exception as e:
            logger.warning(f"Could not check source: {e}")

        if source_empty:
            with sync_lock:
                sync_state["is_running"] = False
                sync_state["progress"] = None
                sync_state["last_sync"] = {
                    "status": "success",
                    "message": "Source is empty - nothing to sync",
                    "timestamp": datetime.now().isoformat(),
                    "files_transferred": 0,
                    "warnings": ["Source directory is empty"]
                }
            return

        DESTINATION_DIR.mkdir(parents=True, exist_ok=True)

        try:
            test_file = DESTINATION_DIR / ".write_test"
            test_file.touch()
            test_file.unlink()
        except PermissionError:
            raise Exception(f"Cannot write to destination: {DESTINATION_DIR}")

        disk = get_disk_space(DESTINATION_DIR)
        if disk["free_gb"] < 0.5:
            raise Exception(f"Low disk space: only {disk['free_gb']}GB free")

        cmd = [
            "rsync", "-avh", "--progress", "--stats", "--delete",
            "--partial-dir=.rsync-partial",
            f"{SOURCE_DIR}/", f"{DESTINATION_DIR}/"
        ]

        logger.info(f"Running: {' '.join(cmd)}")

        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        stdout_lines = []
        files_completed = 0
        for line in process.stdout:
            stdout_lines.append(line)
            line_stripped = line.strip()
            if line_stripped and not line_stripped.startswith(' ') and not line_stripped.endswith('/'):
                files_completed += 1
                with sync_lock:
                    if sync_state["progress"]:
                        sync_state["progress"]["current_file"] = line_stripped[:100]
                        sync_state["progress"]["files_completed"] = files_completed
                        if total_files > 0:
                            sync_state["progress"]["percentage"] = min(99, round((files_completed / total_files) * 100))

        process.wait()
        stderr = process.stderr.read()

        result_stdout = ''.join(stdout_lines)
        result_returncode = process.returncode

        logger.info(f"Rsync exit code: {result_returncode}")

        stderr_lower = stderr.lower()

        if result_returncode == 0:
            status = "success"
            message = "Sync completed"
        elif result_returncode in [3]:
            status = "failed"
            message = "Permission denied"
        elif result_returncode == 11:
            status = "failed"
            message = "Disk full" if "no space left" in stderr_lower else "Disk I/O error"
        elif result_returncode == 23:
            status = "warning"
            message = "Partial transfer - some files failed"
            warnings.append("Some files had errors")
        elif result_returncode == 24:
            status = "warning"
            message = "Files vanished during sync"
            warnings.append("Some files were deleted during sync")
        else:
            status = "failed"
            message = f"Rsync failed with code {result_returncode}"

        output = result_stdout + stderr
        files_transferred = 0

        for line in output.split('\n'):
            if 'Number of regular files transferred:' in line:
                try:
                    files_transferred = int(line.split(':')[1].strip())
                except (IndexError, ValueError):
                    pass

        logger.info(f"Transferred {files_transferred} files")

        with sync_lock:
            sync_state["is_running"] = False
            sync_state["progress"] = None
            sync_state["last_sync"] = {
                "status": status,
                "message": message,
                "timestamp": datetime.now().isoformat(),
                "files_transferred": files_transferred,
                "warnings": warnings if warnings else None
            }

    except Exception as e:
        logger.exception("Sync failed")
        with sync_lock:
            sync_state["is_running"] = False
            sync_state["progress"] = None
            sync_state["last_sync"] = {
                "status": "failed",
                "message": str(e),
                "timestamp": datetime.now().isoformat(),
                "files_transferred": 0,
                "warnings": None
            }


@app.post("/sync")
async def sync_folders(background_tasks: BackgroundTasks):
    with sync_lock:
        if sync_state["is_running"]:
            raise HTTPException(status_code=409, detail="Sync already in progress")

    if not check_rsync_available():
        raise HTTPException(status_code=500, detail="rsync not installed")

    if not SOURCE_DIR.exists():
        raise HTTPException(status_code=404, detail=f"Source not found: {SOURCE_DIR}")

    background_tasks.add_task(run_sync_background)

    return {
        "status": "started",
        "message": "Sync started in background",
        "timestamp": datetime.now().isoformat(),
        "source_path": str(SOURCE_DIR),
        "destination_path": str(DESTINATION_DIR)
    }


@app.get("/status")
async def get_status():
    try:
        def count_files(directory: Path) -> Dict[str, Any]:
            if not directory.exists():
                return {"exists": False, "files": 0, "folders": 0, "total_size": 0, "total_size_mb": 0}

            files = folders = total_size = 0

            try:
                for item in directory.rglob('*'):
                    try:
                        if item.is_file():
                            files += 1
                            total_size += item.stat().st_size
                        elif item.is_dir():
                            folders += 1
                    except (PermissionError, OSError):
                        continue
            except Exception as e:
                logger.error(f"Error scanning {directory}: {e}")

            return {
                "exists": True,
                "files": files,
                "folders": folders,
                "total_size": total_size,
                "total_size_mb": round(total_size / (1024 * 1024), 2)
            }

        source_info = count_files(SOURCE_DIR)
        destination_info = count_files(DESTINATION_DIR)
        disk_space = get_disk_space(BASE_DIR)

        with sync_lock:
            current_sync = {
                "is_running": sync_state["is_running"],
                "progress": sync_state["progress"],
                "last_sync": sync_state["last_sync"]
            }

        return {
            "source": {"path": str(SOURCE_DIR), **source_info},
            "destination": {"path": str(DESTINATION_DIR), **destination_info},
            "sync": current_sync,
            "disk_space": disk_space,
            "rsync_available": check_rsync_available(),
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.exception("Status check failed")
        raise HTTPException(status_code=500, detail=f"Status error: {str(e)}")


if __name__ == "__main__":
    import uvicorn

    logger.info("Starting server")

    if not check_rsync_available():
        logger.warning("WARNING: rsync not installed")

    uvicorn.run(app, host="0.0.0.0", port=8000)
