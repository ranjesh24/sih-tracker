"""Sighting emission, in two modes.

JSONL mode is the demo path
---------------------------
It appends one Sighting per line to a local file and touches no network. That
matters more than it sounds: requirement D-6 says the demo must run offline, and
venue wifi fails. A worker in JSONL mode runs to completion with no backend
process alive at all, so the pipeline can be demonstrated, debugged and
re-rehearsed independently of the API server.

HTTP mode posts to the live backend, retries 5xx with exponential backoff, and
fails immediately and loudly on 401 — a wrong ingest key is a configuration
error, and retrying it just delays the message the operator needs to see.

Field names come from schema.md section 3.6 and are generated from the Sighting
dataclass rather than written out again here, so the 30-column correspondence
verified in session 1 cannot drift.
"""

from __future__ import annotations

import dataclasses
import json
import time
from abc import ABC, abstractmethod
from pathlib import Path
from types import TracebackType

import httpx
import numpy as np

from src.config import Settings, get_settings
from src.types import Sighting

INGEST_SIGHTINGS_PATH = "/api/v1/ingest/sightings"
INGEST_KEY_HEADER = "X-Ingest-Key"

HTTP_UNAUTHORIZED = 401
HTTP_SERVER_ERROR_FLOOR = 500


class IngestError(RuntimeError):
    """Base class for ingest failures."""


class IngestAuthError(IngestError):
    """Raised on 401. Fatal by design: the ingest key is wrong.

    Deliberately not retried. The worker turns this into an immediate exit with
    a readable message rather than looping on a request that cannot succeed.
    """


def relative_crop_path(absolute_path: Path, settings: Settings | None = None) -> str:
    """Express a crop path relative to CROP_STORAGE_PATH.

    The backend serves crops through an authenticated route and resolves them
    against its own storage root (techspec.md section 3.3), so an absolute path
    from the worker's filesystem would be meaningless there — and would leak the
    worker's directory layout into the database.

    Args:
        absolute_path: Where the worker actually wrote the crop.
        settings: Pipeline settings; the process singleton when omitted.

    Returns:
        A POSIX-style relative path, e.g. "CAM-01/17.jpg".
    """
    resolved = settings if settings is not None else get_settings()
    storage_root = resolved.CROP_STORAGE_PATH.resolve()

    try:
        return absolute_path.resolve().relative_to(storage_root).as_posix()
    except ValueError:
        # Written outside the configured root. Keep the trailing
        # <camera>/<file> shape the backend resolves against its own root.
        return Path(absolute_path.parent.name, absolute_path.name).as_posix()


def sighting_to_dict(sighting: Sighting) -> dict[str, object]:
    """Serialise a Sighting into a JSON-safe dict keyed by schema column names.

    Keys are read off the dataclass fields, which mirror the `sightings` columns
    in schema.md section 3.6 one for one. Generating them keeps the wire format
    and the schema locked together instead of relying on a hand-written list
    staying in step.

    Args:
        sighting: The sighting to serialise.

    Returns:
        A dict safe to pass to json.dumps.
    """
    payload: dict[str, object] = {}

    for field in dataclasses.fields(sighting):
        value = getattr(sighting, field.name)
        key = field.name

        # The backend's IngestSighting expects `camera_code` (the human code
        # like "CAM-01"), but the Sighting dataclass mirrors the DB column name
        # `camera_id`. The value IS the camera code; only the key differs.
        if key == "camera_id":
            key = "camera_code"

        if isinstance(value, np.ndarray):
            payload[key] = [float(element) for element in value]
        elif isinstance(value, Path):
            payload[key] = value.as_posix()
        elif isinstance(value, np.generic):
            payload[key] = value.item()
        else:
            payload[key] = value

    return payload


class IngestClient(ABC):
    """Common interface for the two emission modes."""

    @abstractmethod
    def send(self, sighting: Sighting) -> None:
        """Emit one sighting."""

    @abstractmethod
    def close(self) -> None:
        """Release any held resource."""

    def __enter__(self) -> IngestClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


class JsonlIngestClient(IngestClient):
    """Appends one JSON object per line to a local file. No network.

    The file handle stays open for the worker's lifetime and is flushed after
    every write, so a run that is interrupted still leaves every sighting
    emitted up to that point on disk and readable.
    """

    def __init__(self, output_path: Path) -> None:
        """Open the JSONL sink, creating parent directories as needed.

        Args:
            output_path: File to append sightings to.
        """
        self._output_path = output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = output_path.open("a", encoding="utf-8")
        self._written_count = 0

    @property
    def output_path(self) -> Path:
        """The file being appended to."""
        return self._output_path

    @property
    def written_count(self) -> int:
        """How many sightings this client has written."""
        return self._written_count

    def send(self, sighting: Sighting) -> None:
        """Append one sighting as a single JSON line."""
        line = json.dumps(sighting_to_dict(sighting), separators=(",", ":"))
        self._handle.write(f"{line}\n")
        self._handle.flush()
        self._written_count += 1

    def close(self) -> None:
        """Close the file handle."""
        if not self._handle.closed:
            self._handle.close()


class HttpIngestClient(IngestClient):
    """POSTs sightings to the backend, retrying transient failures."""

    def __init__(self, settings: Settings | None = None) -> None:
        """Build the HTTP client.

        Args:
            settings: Pipeline settings; the process singleton when omitted.

        Raises:
            IngestAuthError: If no ingest key is configured. Failing here beats
                discovering it after the first tracklet completes.
        """
        self._settings = settings if settings is not None else get_settings()

        if not self._settings.INGEST_API_KEY:
            raise IngestAuthError(
                "INGEST_API_KEY is empty. Set it in ml-pipeline/.env to match the "
                "backend's key, or run with --out to use JSONL mode instead."
            )

        self._url = self._settings.BACKEND_BASE_URL.rstrip("/") + INGEST_SIGHTINGS_PATH
        self._client = httpx.Client(
            timeout=self._settings.INGEST_TIMEOUT_SECONDS,
            # The key is a header, never a query parameter: query strings end up
            # in server access logs (rules.md section 8).
            headers={INGEST_KEY_HEADER: self._settings.INGEST_API_KEY},
        )

    @property
    def url(self) -> str:
        """The ingest endpoint being posted to."""
        return self._url

    def send(self, sighting: Sighting) -> None:
        """POST one sighting, retrying 5xx and transport errors.

        Args:
            sighting: The sighting to submit.

        Raises:
            IngestAuthError: On 401. Not retried.
            IngestError: On a non-retryable 4xx, or once retries are exhausted.
        """
        payload = sighting_to_dict(sighting)
        max_attempts = self._settings.INGEST_MAX_RETRIES + 1
        last_error: str = "no attempt was made"

        for attempt_index in range(max_attempts):
            try:
                response = self._client.post(self._url, json=payload)
            except httpx.RequestError as exc:
                # Transport-level failure: the backend may simply not be up yet.
                last_error = f"transport error: {exc}"
            else:
                if response.status_code == HTTP_UNAUTHORIZED:
                    raise IngestAuthError(
                        f"{INGEST_KEY_HEADER} rejected by {self._url} (401). The "
                        "pipeline key does not match the backend's INGEST_API_KEY. "
                        "This is a configuration error, so it is not retried."
                    )

                if response.status_code < HTTP_SERVER_ERROR_FLOOR:
                    if response.is_success:
                        return
                    # A 4xx that is not 401 means the payload is wrong. Retrying
                    # an identical body cannot fix that.
                    raise IngestError(
                        f"ingest rejected sighting {sighting.id} with "
                        f"{response.status_code}: {response.text[:200]}"
                    )

                last_error = f"server error {response.status_code}: {response.text[:300]}"

            is_last_attempt = attempt_index == max_attempts - 1
            if not is_last_attempt:
                backoff_seconds = self._settings.INGEST_BACKOFF_BASE_SECONDS * (
                    2**attempt_index
                )
                time.sleep(backoff_seconds)

        raise IngestError(
            f"ingest failed for sighting {sighting.id} after {max_attempts} "
            f"attempts against {self._url}; last failure: {last_error}"
        )

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        self._client.close()
