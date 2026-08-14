"""Storage backends for processed profile-photo objects."""

import re
from abc import ABC, abstractmethod
from pathlib import Path


PROFILE_PHOTO_KEY_PATTERN = re.compile(r"^(?:profiles/)?[0-9a-f]{32}\.webp$")


class ProfilePhotoStorage(ABC):
    """Small storage contract independent of filesystem or cloud providers."""

    @abstractmethod
    def save(self, key, content): ...

    @abstractmethod
    def open(self, key): ...

    @abstractmethod
    def delete(self, key): ...

    @abstractmethod
    def exists(self, key): ...


class LocalProfilePhotoStorage(ProfilePhotoStorage):
    """Development backend rooted in the private Flask instance directory."""

    def __init__(self, root):
        self.root = Path(root).resolve()

    def _path(self, key):
        if not PROFILE_PHOTO_KEY_PATTERN.fullmatch(key or ""):
            raise ValueError("Invalid profile photo storage key.")
        path = (self.root / Path(*key.split("/"))).resolve()
        if self.root not in path.parents:
            raise ValueError("Invalid profile photo storage key.")
        return path

    def save(self, key, content):
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.tmp")
        try:
            temporary.write_bytes(content)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)

    def open(self, key):
        return self._path(key).open("rb")

    def delete(self, key):
        try:
            self._path(key).unlink(missing_ok=True)
            return True
        except (OSError, ValueError):
            return False

    def exists(self, key):
        try:
            return self._path(key).is_file()
        except ValueError:
            return False


def build_profile_photo_storage(config):
    """Build the configured backend without coupling profile routes to local files."""
    backend = config["PROFILE_PHOTO_STORAGE_BACKEND"]
    if backend == "local":
        return LocalProfilePhotoStorage(config["PROFILE_UPLOAD_FOLDER"])
    raise RuntimeError(f"Unsupported profile photo storage backend: {backend}")
