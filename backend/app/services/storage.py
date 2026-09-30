"""Cloudflare R2 storage for game film and clips (S3-compatible API).

Objects are referenced in the database as ``r2://<bucket>/<key>`` so the
storage location is explicit and never confused with a local path.
"""

from functools import lru_cache
from typing import BinaryIO

import boto3
from botocore.config import Config

from app.core.config import get_settings

R2_SCHEME = "r2://"
# Presigned links for chunk uploads only need to outlive one chunk; playback
# links need to outlive a long film session.
PART_URL_TTL_SECONDS = 60 * 60
PLAYBACK_URL_TTL_SECONDS = 12 * 60 * 60


class StorageNotConfigured(RuntimeError):
    pass


@lru_cache
def _client():
    settings = get_settings()
    if not (settings.r2_account_id and settings.r2_access_key_id and settings.r2_secret_access_key):
        raise StorageNotConfigured("R2 credentials are not set")
    return boto3.client(
        "s3",
        endpoint_url=f"https://{settings.r2_account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
        region_name="auto",
        config=Config(signature_version="s3v4", retries={"max_attempts": 3, "mode": "standard"}),
    )


def _bucket() -> str:
    return get_settings().r2_bucket


def to_storage_url(key: str) -> str:
    return f"{R2_SCHEME}{_bucket()}/{key}"


def key_from_storage_url(storage_url: str | None) -> str | None:
    """Return the object key for an r2:// reference, or None for anything else."""
    if not storage_url or not storage_url.startswith(R2_SCHEME):
        return None
    _bucket_name, _, key = storage_url[len(R2_SCHEME):].partition("/")
    return key or None


def create_multipart_upload(key: str, content_type: str) -> str:
    response = _client().create_multipart_upload(Bucket=_bucket(), Key=key, ContentType=content_type)
    return response["UploadId"]


def presign_upload_part(key: str, upload_id: str, part_number: int) -> str:
    return _client().generate_presigned_url(
        "upload_part",
        Params={"Bucket": _bucket(), "Key": key, "UploadId": upload_id, "PartNumber": part_number},
        ExpiresIn=PART_URL_TTL_SECONDS,
    )


def list_parts(key: str, upload_id: str) -> list[dict]:
    parts: list[dict] = []
    marker = 0
    while True:
        response = _client().list_parts(
            Bucket=_bucket(), Key=key, UploadId=upload_id, PartNumberMarker=marker
        )
        parts.extend(
            {"part_number": p["PartNumber"], "etag": p["ETag"], "size": p["Size"]}
            for p in response.get("Parts", [])
        )
        if not response.get("IsTruncated"):
            return parts
        marker = response["NextPartNumberMarker"]


def complete_multipart_upload(key: str, upload_id: str, parts: list[dict]) -> None:
    _client().complete_multipart_upload(
        Bucket=_bucket(),
        Key=key,
        UploadId=upload_id,
        MultipartUpload={
            "Parts": [
                {"PartNumber": p["part_number"], "ETag": p["etag"]}
                for p in sorted(parts, key=lambda p: p["part_number"])
            ]
        },
    )


def abort_multipart_upload(key: str, upload_id: str) -> None:
    _client().abort_multipart_upload(Bucket=_bucket(), Key=key, UploadId=upload_id)


def put_object(key: str, body: BinaryIO, content_type: str) -> None:
    _client().upload_fileobj(body, _bucket(), key, ExtraArgs={"ContentType": content_type})


def object_size(key: str) -> int:
    return _client().head_object(Bucket=_bucket(), Key=key)["ContentLength"]


def presign_download(key: str, ttl_seconds: int = PLAYBACK_URL_TTL_SECONDS) -> str:
    return _client().generate_presigned_url(
        "get_object", Params={"Bucket": _bucket(), "Key": key}, ExpiresIn=ttl_seconds
    )


def delete_object(key: str) -> None:
    _client().delete_object(Bucket=_bucket(), Key=key)
