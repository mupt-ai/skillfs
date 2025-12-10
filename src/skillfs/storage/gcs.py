"""Google Cloud Storage bundle persistence."""

import json
import logging
import os
from pathlib import Path

from skillfs.storage.base import BundleStore

logger = logging.getLogger(__name__)

try:
    from google.cloud import storage
    from google.oauth2 import service_account
except ImportError as e:
    raise ImportError(
        "GCS storage requires google-cloud-storage. "
        "Install with: pip install skillfs[gcs]"
    ) from e


class GCSBundleStore(BundleStore):
    """Manages Git bundle storage in Google Cloud Storage.

    Handles uploading and downloading agent state bundles to/from GCS.
    Supports explicit service account credentials (object/file/info/env) with
    ADC as a fallback.

    Example:
        >>> from skillfs.storage import GCSBundleStore
        >>> from pathlib import Path
        >>> store = GCSBundleStore(bucket="my-agents-bucket")
        >>>
        >>> # Save agent state
        >>> store.upload_bundle("agent-123", Path("./123.bundle"))
        >>>
        >>> # Load agent state
        >>> if store.download_bundle("agent-123", Path("./restored.bundle")):
        >>>     print("Bundle restored successfully")
    """

    def __init__(
        self,
        bucket: str,
        prefix: str = "",
        *,
        credentials=None,
        credentials_file: str | None = None,
        credentials_info: dict | None = None,
    ):
        """Initialize GCS bundle store.

        Args:
            bucket: GCS bucket name (without gs:// prefix).
            prefix: Object key prefix for bundles (default: "").
                    Should end with "/" if used as a directory.
            credentials: Optional google.auth credentials object. If provided,
                takes priority over other sources.
            credentials_file: Optional path to a service account JSON key file.
            credentials_info: Optional dict containing service account info
                (parsed JSON). Useful for secrets provided via env.

        Credential resolution order:
            1) credentials (explicit object)
            2) credentials_file (explicit path)
            3) credentials_info (explicit dict)
            4) env GCS_SERVICE_ACCOUNT_FILE
            5) env GCS_SERVICE_ACCOUNT_JSON
            6) ADC fallback

        Raises:
            RuntimeError: If GCS authentication fails.
        """
        self.bucket_name = bucket
        self.prefix = prefix

        creds = self._resolve_credentials(credentials, credentials_file, credentials_info)

        try:
            project_id = getattr(creds, "project_id", None) if creds is not None else None
            self.client = storage.Client(credentials=creds, project=project_id)
            self.bucket = self.client.bucket(bucket)
            logger.info(f"Initialized GCS bundle store: gs://{bucket}/{prefix}")
        except Exception as e:
            raise RuntimeError(
                "GCS authentication failed. Ensure you have:\n"
                "1. Provide a valid service account via credentials/credentials_file/credentials_info, OR\n"
                "2. Set GOOGLE_APPLICATION_CREDENTIALS / GCS_SERVICE_ACCOUNT_FILE / GCS_SERVICE_ACCOUNT_JSON, OR\n"
                "3. Run 'gcloud auth application-default login', OR\n"
                "4. Are running on GCP with appropriate IAM roles"
            ) from e

    def key_for_agent(self, agent_id: str) -> str:
        """Generate the GCS object key for an agent's bundle.

        Args:
            agent_id: The agent identifier.

        Returns:
            Full GCS object key (e.g., "agent-123.bundle" or "prefix/agent-123.bundle").
        """
        return f"{self.prefix}{agent_id}.bundle"

    def download_bundle(self, agent_id: str, dest: Path) -> bool:
        """Download an agent's bundle from GCS if it exists.

        Args:
            agent_id: The agent identifier.
            dest: Local path where bundle should be saved.

        Returns:
            True if bundle was downloaded, False if bundle doesn't exist.

        Raises:
            RuntimeError: If download fails for reasons other than not existing.
        """
        key = self.key_for_agent(agent_id)
        blob = self.bucket.blob(key)

        logger.info(f"Checking for bundle: gs://{self.bucket_name}/{key}")

        if not blob.exists():
            logger.info(f"No existing bundle found for agent {agent_id}")
            return False

        try:
            # Ensure parent directory exists
            dest.parent.mkdir(parents=True, exist_ok=True)

            # Download the bundle
            logger.info(f"Downloading bundle to {dest}")
            blob.download_to_filename(str(dest))
            logger.info(f"Successfully downloaded bundle ({dest.stat().st_size} bytes)")
            return True

        except Exception as e:
            raise RuntimeError(f"Failed to download bundle from GCS: {e}") from e

    def upload_bundle(self, agent_id: str, src: Path) -> None:
        """Upload an agent's bundle to GCS.

        Args:
            agent_id: The agent identifier.
            src: Local path to the bundle file.

        Raises:
            FileNotFoundError: If source bundle doesn't exist.
            RuntimeError: If upload fails.
        """
        if not src.exists():
            raise FileNotFoundError(f"Bundle file not found: {src}")

        key = self.key_for_agent(agent_id)
        blob = self.bucket.blob(key)

        try:
            logger.info(
                f"Uploading bundle to gs://{self.bucket_name}/{key} "
                f"({src.stat().st_size} bytes)"
            )
            blob.upload_from_filename(str(src))
            logger.info("Bundle uploaded successfully")

        except Exception as e:
            raise RuntimeError(f"Failed to upload bundle to GCS: {e}") from e

    def _resolve_credentials(self, credentials, credentials_file, credentials_info):
        """Resolve credentials from explicit args or env, else return None for ADC."""

        # 1) Explicit object
        if credentials is not None:
            return credentials

        # 2) Explicit file
        if credentials_file:
            return service_account.Credentials.from_service_account_file(credentials_file)

        # 3) Explicit info dict
        if credentials_info:
            return service_account.Credentials.from_service_account_info(credentials_info)

        # 4) Env: file
        env_file = os.getenv("GCS_SERVICE_ACCOUNT_FILE")
        if env_file:
            return service_account.Credentials.from_service_account_file(env_file)

        # 5) Env: JSON
        env_json = os.getenv("GCS_SERVICE_ACCOUNT_JSON")
        if env_json:
            try:
                info = json.loads(env_json)
            except json.JSONDecodeError as e:
                raise RuntimeError("Invalid JSON in GCS_SERVICE_ACCOUNT_JSON") from e
            return service_account.Credentials.from_service_account_info(info)

        # 6) None -> ADC fallback
        return None
