"""SkillFS - Persistent, version-controlled sandbox for AI agents."""

from skillfs.workspaces import Workspace
from skillfs.repositories import GitRepo
from skillfs.sandboxes import E2BSandbox, SandboxConfig, SandboxConnection
from skillfs.storage import BundleStore

__version__ = "0.1.0"

__all__ = [
    "Workspace",
    "GitRepo",
    "E2BSandbox",
    "SandboxConnection",
    "SandboxConfig",
    "BundleStore",
]
