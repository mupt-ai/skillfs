"""Storage backends for SkillFS state persistence."""

from skillfs.storage.base import BundleStore
from skillfs.storage.local import LocalBundleStore

__all__ = ["BundleStore", "LocalBundleStore"]

# GCS storage is optional and will raise ImportError if dependencies not installed
try:
    from skillfs.storage.gcs import GCSBundleStore

    __all__.append("GCSBundleStore")
except ImportError:
    # google-cloud-storage not installed
    pass
