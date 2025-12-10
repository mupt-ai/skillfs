"""Storage backends for SkillFS state persistence."""

from skillfs.storage.base import BundleStore

# GCS storage is optional and will raise ImportError if dependencies not installed
try:
    from skillfs.storage.gcs import GCSBundleStore

    __all__ = ["BundleStore", "GCSBundleStore"]
except ImportError:
    # google-cloud-storage not installed
    __all__ = ["BundleStore"]
