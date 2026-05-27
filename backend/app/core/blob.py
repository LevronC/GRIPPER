"""
Vercel Blob Storage utility.

On Vercel, the local filesystem is ephemeral — files written to /tmp are lost
between function invocations. This module provides upload/download helpers that
use the Vercel Blob REST API when BLOB_READ_WRITE_TOKEN is set, falling back to
local disk operations for local development.

Usage:
    from app.core.blob import store_upload, fetch_blob

    # On upload — returns the URL (blob URL on Vercel, local path in dev)
    file_ref = store_upload(content: bytes, filename: str) -> str

    # In the cron worker — returns raw PDF bytes
    content = fetch_blob(file_ref: str) -> bytes
"""

import logging
import os
import urllib.request
import urllib.error
import json
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

_BLOB_API = "https://blob.vercel-storage.com"


def _is_blob_url(ref: str) -> bool:
    """Returns True if the file reference is a Vercel Blob URL rather than a local path."""
    return ref.startswith("https://")


def store_upload(content: bytes, filename: str) -> str:
    """
    Persists PDF bytes and returns a stable file reference.

    On Vercel (BLOB_READ_WRITE_TOKEN set): uploads to Vercel Blob and returns
    the public blob URL.

    In local development: writes to UPLOAD_DIR and returns the local file path.
    """
    if settings.BLOB_READ_WRITE_TOKEN:
        return _upload_to_vercel_blob(content, filename)

    # Local fallback
    local_path = os.path.join(settings.UPLOAD_DIR, filename)
    with open(local_path, "wb") as fh:
        fh.write(content)
    return local_path


def fetch_blob(file_ref: str) -> bytes:
    """
    Downloads and returns the raw bytes for a file reference.

    Handles both Vercel Blob URLs (https://...) and local paths.
    """
    if _is_blob_url(file_ref):
        return _download_from_vercel_blob(file_ref)

    with open(file_ref, "rb") as fh:
        return fh.read()


def delete_blob(file_ref: str) -> None:
    """
    Deletes a stored file after ingestion is complete.
    Safe to call even if the file has already been removed.
    """
    if _is_blob_url(file_ref):
        _delete_from_vercel_blob(file_ref)
        return

    try:
        os.remove(file_ref)
        logger.info("Deleted local upload: %s", file_ref)
    except FileNotFoundError:
        pass
    except OSError as e:
        logger.warning("Could not delete local upload %s: %s", file_ref, e)


# ── Internal Vercel Blob helpers ──────────────────────────────────────────────

def _upload_to_vercel_blob(content: bytes, filename: str) -> str:
    """
    Uploads bytes to Vercel Blob via the REST PUT API.
    Returns the public blob URL.

    API reference: https://vercel.com/docs/storage/vercel-blob/using-blob-sdk#upload-a-blob
    """
    url = f"{_BLOB_API}/{filename}"
    headers = {
        "Authorization": f"Bearer {settings.BLOB_READ_WRITE_TOKEN}",
        "Content-Type": "application/octet-stream",
        "x-content-type": "application/pdf",
        # Cache-Control: no caching — PDFs are processed once and deleted
        "x-cache-control-max-age": "0",
    }

    req = urllib.request.Request(url, data=content, headers=headers, method="PUT")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode())
            blob_url: str = body["url"]
            logger.info("Uploaded %s to Vercel Blob: %s", filename, blob_url)
            return blob_url
    except urllib.error.HTTPError as e:
        error_body = e.read().decode(errors="replace")
        raise RuntimeError(
            f"Vercel Blob upload failed ({e.code}): {error_body}"
        ) from e
    except Exception as e:
        raise RuntimeError(f"Vercel Blob upload error: {e}") from e


def _download_from_vercel_blob(blob_url: str) -> bytes:
    """
    Downloads raw bytes from a Vercel Blob URL.
    """
    req = urllib.request.Request(
        blob_url,
        headers={"Authorization": f"Bearer {settings.BLOB_READ_WRITE_TOKEN}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        raise RuntimeError(
            f"Vercel Blob download failed ({e.code}) for {blob_url}"
        ) from e
    except Exception as e:
        raise RuntimeError(f"Vercel Blob download error: {e}") from e


def _delete_from_vercel_blob(blob_url: str) -> None:
    """
    Deletes a blob via the Vercel Blob DELETE API.
    """
    delete_url = f"{_BLOB_API}/delete"
    payload = json.dumps({"urls": [blob_url]}).encode()
    headers = {
        "Authorization": f"Bearer {settings.BLOB_READ_WRITE_TOKEN}",
        "Content-Type": "application/json",
    }
    req = urllib.request.Request(delete_url, data=payload, headers=headers, method="DELETE")
    try:
        urllib.request.urlopen(req, timeout=10)
        logger.info("Deleted blob: %s", blob_url)
    except Exception as e:
        logger.warning("Could not delete blob %s: %s", blob_url, e)
