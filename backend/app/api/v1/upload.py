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
from sqlalchemy import delete
from sqlmodel import Session, select

from app.api.deps import get_session
from app.core.config import get_settings
from app.core.exceptions import NotFoundError
from app.models import MatchDecision, Sighting, Vehicle
from app.repositories import camera_repo, video_repo

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

# Batch membership is stated by the client, never inferred.
#
# It used to be derived from a 600-second sliding window: an upload joined the
# newest batch if that batch's most recent video was under 600s old. Two genuinely
# separate sessions minutes apart therefore merged into one batch, and a camera
# from the earlier run kept rendering on the live wall with stale footage. A time
# window cannot distinguish "same session, slow operator" from "new session
# shortly after", so the guess is removed rather than retuned.


@router.post("/video", response_model=UploadResult)
async def upload_video(
    video: UploadFile = File(...),
    camera_code: str = Form(...),
    batch_id: Optional[str] = Form(default=None),
    session: Session = Depends(get_session),
) -> UploadResult:
    """Accept one video for a camera and start the pipeline worker.

    Args:
        batch_id: The upload session this video belongs to, supplied by the
            client. Omitting it opens a fresh single-video batch, so a direct
            curl never silently joins whatever session ran last.
    """
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

    # Record the camera-to-video association. The live wall filters on this
    # table, so a camera only appears once a video has actually been uploaded
    # for it — seeded sightings do not make a camera look live.
    video_repo.create_video(
        session,
        camera_id=camera.id,
        filename=video_filename,
        batch_id=batch_id or str(uuid.uuid4()),
        job_id=job_id,
    )

    worker_script = ML_PIPELINE_DIR / "scripts" / "run_worker.py"
    # ML pipeline needs Python with cv2/torch/ultralytics/easyocr installed.
    # The backend venv (3.14) doesn't have those — use the system Python that does.
    # The ml-pipeline venv is checked first and is the portable answer: it sits
    # inside the repo, so it resolves on any machine and any OS. The absolute
    # Windows paths below stay as fallbacks for the setup that has no venv.
    ml_python_candidates = [
        ML_PIPELINE_DIR / "venv" / "bin" / "python",  # POSIX venv layout
        ML_PIPELINE_DIR / "venv" / "Scripts" / "python.exe",  # Windows venv layout
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


class SessionResetResult(BaseModel):
    batch_id: Optional[str]
    videos_removed: int
    sightings_removed: int


@router.post("/session/reset", response_model=SessionResetResult)
def reset_session(session: Session = Depends(get_session)) -> SessionResetResult:
    """Clear uploaded videos and every sighting they produced.

    All batches are removed, not just the newest: deleting only the current one
    would promote the previous batch to "current" and resurrect its cameras on
    the live wall, which is the opposite of what "clear uploads" means.

    Membership is read from the recorded ``batch_id`` on each row, never guessed
    from timestamps. Seeded demo sightings carry no batch id, so the prepared
    #A47F trajectory survives an operator resetting a bad run.
    """
    batch_id = video_repo.get_current_batch_id(session)
    videos_removed = video_repo.delete_all(session)

    stale = session.exec(
        select(Sighting).where(Sighting.batch_id.is_not(None))  # type: ignore[union-attr]
    ).all()
    for sighting in stale:
        session.execute(
            delete(MatchDecision).where(MatchDecision.sighting_id == sighting.id)
        )
        session.delete(sighting)
    session.commit()

    # Drop vehicles left with no sightings. Without this every reset stranded
    # the vehicles those uploads created, and the pile pushed the seeded demo
    # vehicle off the first page of /vehicles, so the UI selected an orphan.
    orphans = session.exec(
        select(Vehicle).where(
            ~select(Sighting.id)
            .where(Sighting.vehicle_id == Vehicle.id)
            .exists()
        )
    ).all()
    for vehicle in orphans:
        session.delete(vehicle)
    session.commit()

    logger.info(
        "Upload session reset: last_batch=%s videos=%d sightings=%d",
        batch_id,
        videos_removed,
        len(stale),
    )
    return SessionResetResult(
        batch_id=batch_id,
        videos_removed=videos_removed,
        sightings_removed=len(stale),
    )


@router.get("/serve/{filename}")
def serve_video(filename: str) -> FileResponse:
    path = UPLOAD_DIR / filename
    if not path.is_file() or not path.resolve().is_relative_to(UPLOAD_DIR):
        raise NotFoundError(f"Video file not found: {filename}")
    return FileResponse(path, media_type="video/mp4")
