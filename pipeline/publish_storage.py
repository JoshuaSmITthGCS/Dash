"""Publish ``public/data/`` to Firebase Storage so the site can read it from a bucket.

Why this exists: the pipeline's only publishing path used to be committing ``public/data/``
to ``main``. Git keeps every version of every file forever, so each refresh added tens of MB
of history (advisor.json alone is 36 MB), the full-history checkout every refresh starts
with kept getting slower, and a single file crossing GitHub's 100 MB limit silently stopped
all publishing for five days. A bucket keeps only the latest copy.

What it does, per run:

  data/<path>                    every file under public/data/, gzip-encoded, uploaded only
                                 when its content changed since the last upload
  archive/advisor/<date>.json    one dated copy of advisor.json per UTC day, the history
                                 shadow_portfolios.py currently reads out of git log

Objects carry ``Cache-Control: no-cache`` so a browser revalidates against the object's
ETag on every load: an unchanged file answers 304 instead of re-downloading, a refreshed
one comes through immediately - the same contract useData.js already relies on.

Configuration (both already exist for alert delivery, plus one new variable):

  FIREBASE_SERVICE_ACCOUNT_JSON  service-account key with write access to the bucket
  FIREBASE_STORAGE_BUCKET        bucket name, e.g. ``your-project.firebasestorage.app``

When either is unset this exits 0 with a message, so the workflow keeps working on the
git-commit path alone until the bucket is configured.
"""

from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

from common import DATA_DIR, LOG

DATA_PREFIX = "data/"
ARCHIVE_PREFIX = "archive/advisor/"
CACHE_CONTROL = "no-cache"
# Browsers fetching the bucket from the Netlify site are cross-origin, so the bucket must
# answer CORS. GET/HEAD only: the site never writes to it.
CORS_RULES = [{
    "origin": ["*"],
    "method": ["GET", "HEAD"],
    "responseHeader": ["Content-Type", "Content-Encoding", "ETag", "Cache-Control"],
    "maxAgeSeconds": 3600,
}]


def content_type(path):
    return {
        ".json": "application/json",
        ".csv": "text/csv",
        ".txt": "text/plain",
        ".md": "text/markdown",
    }.get(os.path.splitext(path)[1].lower(), "application/octet-stream")


def gzip_bytes(raw):
    # mtime=0 so identical input always produces identical bytes, which is what lets the
    # MD5 comparison below skip unchanged files.
    return gzip.compress(raw, compresslevel=9, mtime=0)


def md5_base64(data):
    return base64.b64encode(hashlib.md5(data).digest()).decode("ascii")  # noqa: S324 - GCS's own checksum


def local_files(root=DATA_DIR):
    """``[(relative_path, absolute_path)]`` for every publishable file, sorted."""
    files = []
    for directory, _, names in os.walk(root):
        for name in names:
            if name.startswith("."):
                continue
            absolute = os.path.join(directory, name)
            files.append((os.path.relpath(absolute, root).replace(os.sep, "/"), absolute))
    return sorted(files)


def plan_uploads(files, remote_md5):
    """Which files need uploading: ``[(object_name, relative_path, gzipped_bytes)]``.

    ``remote_md5`` maps object name -> the base64 MD5 GCS reports for it. A file whose
    gzipped bytes hash the same is already current and is skipped.
    """
    uploads = []
    for relative, absolute in files:
        with open(absolute, "rb") as handle:
            body = gzip_bytes(handle.read())
        name = DATA_PREFIX + relative
        if remote_md5.get(name) != md5_base64(body):
            uploads.append((name, relative, body))
    return uploads


def archive_name(now=None):
    return f"{ARCHIVE_PREFIX}{(now or datetime.now(timezone.utc)).date().isoformat()}.json"


def _bucket(credentials_json, bucket_name):
    import firebase_admin
    from firebase_admin import credentials, storage

    app_name = "publish-storage"
    try:
        app = firebase_admin.get_app(app_name)
    except ValueError:
        app = firebase_admin.initialize_app(
            credentials.Certificate(json.loads(credentials_json)),
            {"storageBucket": bucket_name}, name=app_name)
    return storage.bucket(app=app)


def _upload(bucket, name, body, relative):
    blob = bucket.blob(name)
    blob.cache_control = CACHE_CONTROL
    blob.content_encoding = "gzip"
    blob.upload_from_string(body, content_type=content_type(relative))


def ensure_cors(bucket):
    """Set the read-only CORS policy if it is missing. Best effort: a key without
    ``storage.buckets.update`` logs the one-line manual fix instead of failing the run."""
    try:
        bucket.reload()
        if bucket.cors == CORS_RULES:
            return True
        bucket.cors = CORS_RULES
        bucket.patch()
        LOG.info("Firebase Storage: CORS policy set for browser reads")
        return True
    except Exception as error:  # noqa: BLE001 - reported, never fatal
        LOG.warn(f"Firebase Storage: could not set CORS ({type(error).__name__}). Set it once by "
                 "hand: gcloud storage buckets update gs://<bucket> --cors-file=cors.json")
        return False


def publish(bucket, root=DATA_DIR, now=None):
    remote = {blob.name: blob.md5_hash for blob in bucket.list_blobs(prefix=DATA_PREFIX)}
    files = local_files(root)
    uploads = plan_uploads(files, remote)
    for name, relative, body in uploads:
        _upload(bucket, name, body, relative)
    archived = None
    advisor = os.path.join(root, "advisor.json")
    if os.path.exists(advisor):
        with open(advisor, "rb") as handle:
            archived = archive_name(now)
            _upload(bucket, archived, gzip_bytes(handle.read()), "advisor.json")
    summary = {
        "uploaded": len(uploads),
        "unchanged": len(files) - len(uploads),
        "uploaded_bytes": sum(len(body) for _, _, body in uploads),
        "archived": archived,
    }
    LOG.info(f"Firebase Storage: uploaded {summary['uploaded']} changed file(s) "
             f"({summary['uploaded_bytes'] / 1e6:.1f} MB gzipped), "
             f"{summary['unchanged']} unchanged; archived {archived}")
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=DATA_DIR, help="directory to publish (default public/data)")
    args = parser.parse_args(argv)
    credentials_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
    bucket_name = os.getenv("FIREBASE_STORAGE_BUCKET")
    if not credentials_json or not bucket_name:
        print("Firebase Storage publish skipped: FIREBASE_SERVICE_ACCOUNT_JSON and "
              "FIREBASE_STORAGE_BUCKET must both be set")
        return 0
    bucket = _bucket(credentials_json, bucket_name)
    ensure_cors(bucket)
    publish(bucket, args.root)
    return 0


if __name__ == "__main__":
    sys.exit(main())
