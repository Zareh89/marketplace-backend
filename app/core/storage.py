import uuid

from google.cloud import storage
from google.cloud.exceptions import NotFound

from app.core.config import settings

_client = storage.Client()


def upload_product_image(file_obj, content_type: str | None) -> str:
    bucket = _client.bucket(settings.gcs_bucket_name)
    blob_name = f"products/{uuid.uuid4()}"
    blob = bucket.blob(blob_name)
    blob.upload_from_file(file_obj, content_type=content_type)
    return f"https://storage.googleapis.com/{settings.gcs_bucket_name}/{blob_name}"


def delete_product_image(image_url: str) -> None:
    prefix = f"https://storage.googleapis.com/{settings.gcs_bucket_name}/"
    if not image_url.startswith(prefix):
        return
    blob_name = image_url.removeprefix(prefix)
    bucket = _client.bucket(settings.gcs_bucket_name)
    try:
        bucket.blob(blob_name).delete()
    except NotFound:
        pass
