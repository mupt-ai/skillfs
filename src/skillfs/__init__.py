"""SkillFS - Code-first AI agent runtime with Git-based persistence."""

from skillfs.agents import Agent
from skillfs.repositories import GitRepo
from skillfs.sandboxes import E2BSandbox, SandboxConfig, SandboxConnection
from skillfs.storage import BundleStore

__version__ = "0.1.0"

__all__ = [
    "Agent",
    "GitRepo",
    "E2BSandbox",
    "SandboxConnection",
    "SandboxConfig",
    "BundleStore",
]
