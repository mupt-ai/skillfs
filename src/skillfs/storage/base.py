"""Base for bundle storage backends."""

from abc import ABC, abstractmethod
from pathlib import Path


class BundleStore(ABC):
    """Abstract interface for storing and retrieving agent state bundles.

    Implementations handle persistence to different storage backends
    (GCS, S3, local filesystem, etc.).
    """

    @abstractmethod
    def key_for_agent(self, agent_id: str) -> str:
        """Generate the storage key for an agent's bundle.

        Args:
            agent_id: The agent identifier.

        Returns:
            Storage-specific key or path for the bundle.
        """
        pass

    @abstractmethod
    def download_bundle(self, agent_id: str, dest: Path) -> bool:
        """Download an agent's bundle if it exists.

        Args:
            agent_id: The agent identifier.
            dest: Local path where bundle should be saved.

        Returns:
            True if bundle was downloaded, False if bundle doesn't exist.

        Raises:
            RuntimeError: If download fails for reasons other than not existing.
        """
        pass

    @abstractmethod
    def upload_bundle(self, agent_id: str, src: Path) -> None:
        """Upload an agent's bundle.

        Args:
            agent_id: The agent identifier.
            src: Local path to the bundle file.

        Raises:
            FileNotFoundError: If source bundle doesn't exist.
            RuntimeError: If upload fails.
        """
        pass
