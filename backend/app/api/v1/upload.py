"""Video upload endpoint — accepts a video file, saves it, and spawns the ML
pipeline worker as a subprocess to process it against a specified camera."""

import logging
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlmodel import Session

from app.api.deps import get_session
from app.core.config import get_settings
from app.core.exceptions import NotFoundError
from app.repositories import camera_repo

logger = logging.getLogger("marg.upload")
router = APIRouter(prefix="/upload", tags=["upload"])

_settings = get_settings()

UPLOAD_DIR = (Path(_settings.CROP_STORAGE_PATH).parent / "uploads").resolve()
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ML_PIPELINE_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent / "ml-pipeline"


class UploadResult(BaseModel):
    job_id: str
    video_filename: str
    camera_code: str
    status: str


class JobStatus(BaseModel):
    job_id: str
    camera_code: str
    status: str
    returncode: Optional[int]


_jobs: dict[str, dict] = {}


@router.post("/video", response_model=UploadResult)
async def upload_video(
    video: UploadFile = File(...),
    camera_code: str = Form(...),
    session: Session = Depends(get_session),
) -> UploadResult:
    camera = camera_repo.get_by_code(session, camera_code)
    if camera is None:
        raise NotFoundError(f"No camera with code {camera_code}")

    job_id = str(uuid.uuid4())[:8]
    ext = Path(video.filename or "video.mp4").suffix or ".mp4"
    video_filename = f"{job_id}_{camera_code}{ext}"
    video_path = (UPLOAD_DIR / video_filename).resolve()
    with open(video_path, "wb") as f:
        while chunk := await video.read(1024 * 1024):
            f.write(chunk)

    logger.info("Video saved: %s (%s)", video_path, camera_code)

    worker_script = ML_PIPELINE_DIR / "scripts" / "run_worker.py"
    # ML pipeline needs Python with cv2/torch/ultralytics/easyocr installed.
    # The backend venv (3.14) doesn't have those — use the system Python that does.
    ml_python_candidates = [
        Path(r"C:\Users\BIT\AppData\Local\Programs\Python\Python312\python.exe"),
        Path(r"C:\Python312\python.exe"),
    ]
    python_exe = str(sys.executable)
    for candidate in ml_python_candidates:
        if candidate.exists():
            python_exe = str(candidate)
            break

    import os
    ml_env_file = ML_PIPELINE_DIR / ".env"
    ml_env: dict[str, str] = {}
    if ml_env_file.exists():
        from dotenv import dotenv_values
        ml_env = {k: v for k, v in dotenv_values(str(ml_env_file)).items() if v is not None}

    env = {**os.environ, **ml_env}
    env["INGEST_API_KEY"] = _settings.INGEST_API_KEY

    log_path = (UPLOAD_DIR / f"{job_id}.log").resolve()
    log_file = open(log_path, "w", encoding="utf-8", errors="replace")

    proc = subprocess.Popen(
        [
            python_exe,
            str(worker_script),
            "--video", str(video_path),
            "--camera-id", camera_code,
            "--post",
        ],
        cwd=str(ML_PIPELINE_DIR),
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )

    _jobs[job_id] = {
        "process": proc,
        "camera_code": camera_code,
        "video_path": str(video_path),
        "log_path": str(log_path),
        "log_file": log_file,
    }

    logger.info("Pipeline worker spawned: job=%s pid=%d camera=%s", job_id, proc.pid, camera_code)

    return UploadResult(
        job_id=job_id,
        video_filename=video_filename,
        camera_code=camera_code,
        status="processing",
    )


@router.get("/status/{job_id}", response_model=JobStatus)
def get_job_status(job_id: str) -> JobStatus:
    job = _jobs.get(job_id)
    if job is None:
        log_path = UPLOAD_DIR / f"{job_id}.log"
        if log_path.exists():
            content = log_path.read_text(encoding="utf-8", errors="replace")
            if "done:" in content:
                return JobStatus(job_id=job_id, camera_code="", status="completed", returncode=0)
            elif "fatal:" in content or "Traceback" in content or "Error" in content:
                return JobStatus(job_id=job_id, camera_code="", status="failed", returncode=1)
        raise NotFoundError(f"No job with id {job_id}")

    proc: subprocess.Popen = job["process"]
    rc = proc.poll()

    if rc is None:
        status = "processing"
    elif rc == 0:
        status = "completed"
        try:
            job["log_file"].close()
        except Exception:
            pass
    else:
        status = "failed"
        try:
            job["log_file"].close()
        except Exception:
            pass

    return JobStatus(
        job_id=job_id,
        camera_code=job["camera_code"],
        status=status,
        returncode=rc,
    )


@router.get("/status/{job_id}/logs")
def get_job_logs(job_id: str) -> dict:
    log_path = UPLOAD_DIR / f"{job_id}.log"
    output = ""
    if log_path.exists():
        output = log_path.read_text(encoding="utf-8", errors="replace")
    return {"job_id": job_id, "logs": output}


@router.get("/serve/{filename}")
def serve_video(filename: str) -> FileResponse:
    path = UPLOAD_DIR / filename
    if not path.is_file() or not path.resolve().is_relative_to(UPLOAD_DIR):
        raise NotFoundError(f"Video file not found: {filename}")
    return FileResponse(path, media_type="video/mp4")
