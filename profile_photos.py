"""Secure decoding and normalization for profile-photo uploads."""

import io
import os
from uuid import uuid4

from PIL import Image, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener


register_heif_opener()

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "GIF", "BMP", "TIFF", "HEIF"}
FINAL_PROFILE_SIZE = (800, 800)


class ProfilePhotoError(ValueError):
    """A safe, user-facing photo validation or processing error."""


def _file_size(upload):
    position = upload.stream.tell()
    upload.stream.seek(0, os.SEEK_END)
    size = upload.stream.tell()
    upload.stream.seek(position)
    return size


def _validated_crop(crop):
    try:
        x = float(crop.get("x", 0.5))
        y = float(crop.get("y", 0.5))
        zoom = float(crop.get("zoom", 1))
    except (TypeError, ValueError, AttributeError):
        raise ProfilePhotoError("The photo crop settings are invalid. Please reset the crop and try again.") from None
    if not (0 <= x <= 1 and 0 <= y <= 1 and 1 <= zoom <= 4):
        raise ProfilePhotoError("The photo crop settings are invalid. Please reset the crop and try again.")
    return x, y, zoom


def process_profile_photo(upload, maximum_size, crop=None):
    """Decode real image content and return metadata-free optimized WebP bytes."""
    if not upload or not upload.filename:
        return None
    if _file_size(upload) > maximum_size:
        raise ProfilePhotoError("Profile photos must be 5 MB or smaller.")
    try:
        upload.stream.seek(0)
        with Image.open(upload.stream) as candidate:
            if candidate.format not in ALLOWED_FORMATS:
                raise ProfilePhotoError("The selected file is not a supported photo format.")
            candidate.verify()
        upload.stream.seek(0)
        with Image.open(upload.stream) as source:
            source.seek(0)  # Animated formats use their first frame.
            image = ImageOps.exif_transpose(source)
            if image.mode not in {"RGB", "RGBA"}:
                image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
            image.load()
            x, y, zoom = _validated_crop(crop or {})
            crop_size = min(image.size) / zoom
            center_x, center_y = x * image.width, y * image.height
            left = min(max(center_x - crop_size / 2, 0), image.width - crop_size)
            top = min(max(center_y - crop_size / 2, 0), image.height - crop_size)
            output = image.crop((round(left), round(top), round(left + crop_size), round(top + crop_size)))
            output.thumbnail(FINAL_PROFILE_SIZE, Image.Resampling.LANCZOS)
    except ProfilePhotoError:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError):
        raise ProfilePhotoError("The selected photo is invalid or corrupted.") from None

    encoded = io.BytesIO()
    try:
        output.save(encoded, format="WEBP", quality=86, method=6)
    except OSError:
        raise ProfilePhotoError("We couldn't process that photo. Please try another one.") from None
    return encoded.getvalue()


def generate_profile_photo_key():
    return f"profiles/{uuid4().hex}.webp"
