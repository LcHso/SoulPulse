"""Alibaba Cloud OSS image upload utility."""

import uuid
from io import BytesIO

import oss2

from core.config import settings

_bucket: oss2.Bucket | None = None


def _get_bucket() -> oss2.Bucket:
    global _bucket
    if _bucket is None:
        auth = oss2.Auth(settings.OSS_ACCESS_KEY_ID, settings.OSS_ACCESS_KEY_SECRET)
        _bucket = oss2.Bucket(auth, settings.OSS_ENDPOINT, settings.OSS_BUCKET_NAME)
    return _bucket


def upload_image(file_bytes: bytes, content_type: str = "image/jpeg") -> str:
    """Upload an image to OSS and return its public URL.

    Args:
        file_bytes: Raw image bytes.
        content_type: MIME type of the image.

    Returns:
        The public URL of the uploaded image.
    """
    bucket = _get_bucket()
    ext = content_type.split("/")[-1] if "/" in content_type else "jpg"
    key = f"posts/{uuid.uuid4().hex}.{ext}"

    headers = {"Content-Type": content_type}
    bucket.put_object(key, BytesIO(file_bytes), headers=headers)

    # Build public-read URL
    url = f"https://{settings.OSS_BUCKET_NAME}.{settings.OSS_ENDPOINT.replace('https://', '')}/{key}"
    return url
