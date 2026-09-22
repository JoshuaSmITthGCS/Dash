import gzip
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import publish_storage as module


class FakeBlob:
    def __init__(self, bucket, name):
        self.bucket, self.name = bucket, name
        self.md5_hash = None
        self.cache_control = self.content_encoding = self.content_type = None

    def upload_from_string(self, body, content_type):
        self.content_type = content_type
        self.md5_hash = module.md5_base64(body)
        self.bucket.objects[self.name] = self
        self.bucket.bodies[self.name] = body


class FakeBucket:
    def __init__(self):
        self.objects, self.bodies = {}, {}

    def blob(self, name):
        return FakeBlob(self, name)

    def list_blobs(self, prefix=""):
        return [blob for name, blob in self.objects.items() if name.startswith(prefix)]


def write(root, relative, text):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


NOW = datetime(2026, 9, 22, 20, 0, tzinfo=timezone.utc)


def test_every_file_is_uploaded_gzipped_under_data_with_revalidating_headers(tmp_path):
    write(tmp_path, "advisor.json", '{"a": 1}')
    write(tmp_path, "etf/SPY.json", '{"b": 2}')
    bucket = FakeBucket()

    summary = module.publish(bucket, str(tmp_path), now=NOW)

    assert summary["uploaded"] == 2
    blob = bucket.objects["data/etf/SPY.json"]
    assert (blob.content_type, blob.content_encoding, blob.cache_control) == \
        ("application/json", "gzip", "no-cache")
    assert gzip.decompress(bucket.bodies["data/etf/SPY.json"]) == b'{"b": 2}'


def test_a_rerun_uploads_only_what_changed(tmp_path):
    write(tmp_path, "advisor.json", '{"a": 1}')
    write(tmp_path, "report.json", '{"r": 1}')
    bucket = FakeBucket()
    module.publish(bucket, str(tmp_path), now=NOW)

    write(tmp_path, "report.json", '{"r": 2}')
    summary = module.publish(bucket, str(tmp_path), now=NOW)

    assert (summary["uploaded"], summary["unchanged"]) == (1, 1)
    assert gzip.decompress(bucket.bodies["data/report.json"]) == b'{"r": 2}'


def test_advisor_json_is_archived_once_per_utc_day(tmp_path):
    write(tmp_path, "advisor.json", '{"a": 1}')
    bucket = FakeBucket()

    summary = module.publish(bucket, str(tmp_path), now=NOW)

    assert summary["archived"] == "archive/advisor/2026-09-22.json"
    assert gzip.decompress(bucket.bodies["archive/advisor/2026-09-22.json"]) == b'{"a": 1}'


def test_hidden_temp_files_are_not_published(tmp_path):
    write(tmp_path, ".advisor.json.tmp123", "partial")
    write(tmp_path, "report.json", "{}")
    assert [relative for relative, _ in module.local_files(str(tmp_path))] == ["report.json"]


def test_gzip_output_is_deterministic_so_unchanged_files_hash_the_same():
    assert module.gzip_bytes(b"same") == module.gzip_bytes(b"same")


def test_missing_configuration_skips_without_failing(monkeypatch, capsys):
    monkeypatch.delenv("FIREBASE_SERVICE_ACCOUNT_JSON", raising=False)
    monkeypatch.delenv("FIREBASE_STORAGE_BUCKET", raising=False)
    assert module.main([]) == 0
    assert "skipped" in capsys.readouterr().out
