"""Agent class for managing persistent agent state."""

import logging
from typing import Optional

from skillfs.constants import DEFAULT_REPO_ROOT
from skillfs.agents.persistence import load_agent_state, save_agent_state
from skillfs.repositories.git_repo import GitRepo
from skillfs.sandboxes.base import SandboxConnection
from skillfs.storage.base import BundleStore

logger = logging.getLogger(__name__)


class Agent:
    """High-level interface for managing a persistent agent.

    Encapsulates agent identity, sandbox connection, storage backend, and
    provides convenient methods for loading and saving agent state.

    Example:
        >>> from skillfs.sandboxes import E2BSandbox
        >>> from skillfs.storage import GCSBundleStore
        >>> from skillfs.agents import Agent
        >>>
        >>> # Setup
        >>> sandbox = E2BSandbox.create()
        >>> store = GCSBundleStore(bucket="my-agents", prefix="prod/")
        >>>
        >>> # Create agent
        >>> agent = Agent(
        >>>     agent_id="alice-123",
        >>>     sandbox=sandbox,
        >>>     store=store
        >>> )
        >>>
        >>> # Load state (from bundle if exists, or fresh init)
        >>> agent.load()
        >>>
        >>> # Agent does work...
        >>> # ... writes skills, modifies files in agent.git_repo ...
        >>>
        >>> # Save state back to storage
        >>> agent.save()
        >>>
        >>> # Cleanup
        >>> sandbox.close()
    """

    def __init__(
        self,
        agent_id: str,
        sandbox: SandboxConnection,
        store: BundleStore,
        repo_root: str = DEFAULT_REPO_ROOT,
    ):
        """Initialize agent instance.

        Args:
            agent_id: Unique identifier for this agent.
            sandbox: Active sandbox connection where agent operates.
            store: Storage backend for persisting agent state.
            repo_root: Path inside sandbox for the Git repository.
        """
        self.agent_id = agent_id
        self.sandbox = sandbox
        self.store = store
        self.repo_root = repo_root
        self.git_repo: Optional[GitRepo] = None
        self._is_loaded = False

        logger.info(f"Created agent instance: {agent_id}")

    def load(self) -> None:
        """Load agent state from storage into sandbox.

        Downloads bundle from storage if it exists and restores the Git repository.
        If no bundle exists, initializes a fresh repository with SkillFS structure.

        After calling this method, the agent's Git repository is accessible
        via `self.git_repo`.

        Raises:
            RuntimeError: If agent is already loaded or if load operation fails.
        """
        if self._is_loaded:
            raise RuntimeError(
                f"Agent {self.agent_id} is already loaded. "
                "Call save() and create a new Agent instance if you need to reload."
            )

        logger.info(f"Loading agent {self.agent_id}")

        self.git_repo = load_agent_state(
            agent_id=self.agent_id,
            sandbox=self.sandbox,
            bundle_store=self.store,
            repo_root=self.repo_root,
        )

        self._is_loaded = True
        logger.info(f"Agent {self.agent_id} loaded successfully")

    def save(self, commit_message: Optional[str] = None) -> None:
        """Save agent state from sandbox to storage.

        Commits pending changes, creates a Git bundle, and uploads it to storage.

        Args:
            commit_message: Optional custom commit message. If None, generates
                          a default message with timestamp.

        Raises:
            RuntimeError: If agent is not loaded or if save operation fails.
        """
        if not self._is_loaded or self.git_repo is None:
            raise RuntimeError(
                f"Agent {self.agent_id} is not loaded. Call load() first."
            )

        logger.info(f"Saving agent {self.agent_id}")

        save_agent_state(
            agent_id=self.agent_id,
            sandbox=self.sandbox,
            git_repo=self.git_repo,
            bundle_store=self.store,
            commit_message=commit_message,
        )

        logger.info(f"Agent {self.agent_id} saved successfully")

    @property
    def is_loaded(self) -> bool:
        """Check if agent state is currently loaded."""
        return self._is_loaded

    def __repr__(self) -> str:
        """String representation of the agent."""
        status = "loaded" if self._is_loaded else "not loaded"
        return f"Agent(id={self.agent_id}, status={status})"
