"""Agent class for managing persistent agent state."""

import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Type

from skillfs.agents.persistence import load_agent_state, save_agent_state
from skillfs.repositories.git_repo import GitRepo
from skillfs.runners.base import AgentResult, RunnerProvider, RunnerType
from skillfs.runners.tools.load_skill import create_load_skill_tool
from skillfs.sandboxes.base import SandboxConnection
from skillfs.skills.catalog import SkillCatalog
from skillfs.storage.base import BundleStore

logger = logging.getLogger(__name__)

class Agent:
    """High-level interface for managing a persistent agent.

    Encapsulates agent identity, sandbox connection, storage backend, and
    provides convenient methods for loading, saving, and running agent tasks.

    Example:
        >>> from skillfs.sandboxes import E2BSandbox
        >>> from skillfs.storage import GCSBundleStore
        >>> from skillfs.agents import Agent
        >>> from skillfs.runners.providers.anthropic import AnthropicProvider
        >>> from skillfs.runners.types import MainRunner
        >>>
        >>> # Setup
        >>> sandbox = E2BSandbox.create()
        >>> store = GCSBundleStore(bucket="my-agents", prefix="prod/")
        >>> provider = AnthropicProvider(api_key="...", model="claude-sonnet-4-20250514")
        >>>
        >>> # Create agent with runner
        >>> agent = Agent(
        >>>     agent_id="alice-123",
        >>>     sandbox=sandbox,
        >>>     store=store,
        >>>     provider=provider,
        >>>     runner=MainRunner,
        >>>     runner_config={
        >>>         "name": "main",
        >>>         "description": "Main agent",
        >>>         "system_prompt": "You are a helpful assistant...",
        >>>         "tools": ["glob", "grep", "read_file"],
        >>>     },
        >>> )
        >>>
        >>> # Load state (from bundle if exists, or fresh init)
        >>> await agent.load()
        >>>
        >>> # Run a task
        >>> result = await agent.run("Find all Python files")
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
        provider: Optional[RunnerProvider] = None,
        runner: Optional[Type[RunnerType]] = None,
        runner_config: Optional[Dict[str, Any]] = None,
        repo_root: Optional[str] = None,
        mcp_servers: Optional[Dict[str, Dict[str, Any]]] = None,
        generate_mcp_tools: bool = False,
        skills: Optional[Dict[str, Any]] = None,
        load_skills: bool = False,
    ):
        """Initialize agent instance.

        Args:
            agent_id: Unique identifier for this agent.
            sandbox: Active sandbox connection where agent operates.
            store: Storage backend for persisting agent state.
            provider: Default RunnerProvider for creating runners. Can be overridden
                     in runner_config. Required if runner is specified without
                     a provider in runner_config.
            runner: Runner class to instantiate (e.g., MainRunner). If None,
                   agent.run() will raise an error.
            runner_config: Configuration dict passed to runner constructor.
                          Can include 'provider' to override agent's default provider.
                          Other keys depend on the runner class (e.g., name, description,
                          system_prompt, tools, subrunners, max_turns for MainRunner).
            repo_root: Path inside sandbox for the Git repository.
                If None, uses sandbox.default_repo_root.
            mcp_servers: Optional MCP server configurations.
                        Format: {"server-name": {"command": "...", "args": [...], "env": {...}}}
            generate_mcp_tools: If True, generate MCP tool wrappers during load.
                               If False, MCP servers are ignored.
            skills: Optional skills configuration.
                   Format: {"local": "/path/to/skills" or ["/path1", "/path2"]}
            load_skills: If True, load skills from configured sources during load.
                        If False, skills config is ignored.

        After load(), the following attributes are available:
            git_repo: GitRepo instance for the agent's repository.
            skill_catalog: SkillCatalog with discovered SKILL.md files.
            load_skill_schema: Tool schema for load_skill (None if no skills found).
            load_skill_handler: Handler function for load_skill (None if no skills found).
            runner: Instantiated runner (None if no runner class was provided).
        """
        self.agent_id = agent_id
        self.sandbox = sandbox
        self.store = store
        self.provider = provider
        self.runner_class = runner
        self.runner_config = runner_config or {}
        self.repo_root = repo_root if repo_root is not None else sandbox.default_repo_root
        self.mcp_servers = mcp_servers or {}
        self.generate_mcp_tools = generate_mcp_tools
        self.skills = skills or {}
        self.load_skills = load_skills
        self.git_repo: Optional[GitRepo] = None
        self.skill_catalog: Optional[SkillCatalog] = None
        self.load_skill_schema: Optional[Dict[str, Any]] = None
        self.load_skill_handler: Optional[Any] = None
        self.runner: Optional[RunnerType] = None
        self._is_loaded = False

        logger.info(f"Created agent instance: {agent_id}")

    async def load(self) -> None:
        """Load agent state from storage into sandbox.

        Downloads bundle from storage if it exists and restores the Git repository.
        If no bundle exists, initializes a fresh repository with SkillFS structure.
        If MCP servers are configured, sets them up after loading.

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

        # Setup MCP servers if flag is enabled
        if self.generate_mcp_tools and self.mcp_servers:
            await self.setup_mcp_servers(self.mcp_servers)

        # Setup skills if flag is enabled
        if self.load_skills and self.skills:
            await self.setup_skills(self.skills)

        # Create and scan skill catalog to discover SKILL.md files
        # This indexes skills that were uploaded or already exist in the sandbox
        self.skill_catalog = SkillCatalog(
            sandbox=self.sandbox,
            repo_root=self.repo_root,
        )
        num_skills = await self.skill_catalog.scan()
        if num_skills > 0:
            logger.info(f"Discovered {num_skills} skill(s) in sandbox")
            # Create load_skill tool for use with runners
            self.load_skill_schema, self.load_skill_handler = create_load_skill_tool(
                self.skill_catalog
            )

        # Instantiate runner if configured
        if self.runner_class is not None:
            self._setup_runner()

        self._is_loaded = True
        logger.info(f"Agent {self.agent_id} loaded successfully")

    def _setup_runner(self) -> None:
        """Instantiate the runner with skill tool injection.

        Called during load() after skill catalog is set up.
        Resolves provider from runner_config or falls back to agent's provider.
        Automatically injects load_skill tool if skills were discovered.

        Raises:
            RuntimeError: If no provider is available.
        """
        if self.runner_class is None:
            return

        # Make a copy of runner_config to avoid mutating the original
        config = dict(self.runner_config)

        # Resolve provider: runner_config overrides agent default
        runner_provider = config.pop("provider", None) or self.provider
        if runner_provider is None:
            raise RuntimeError(
                f"Agent {self.agent_id}: No provider configured. "
                "Set provider on Agent or in runner_config."
            )

        # Instantiate the runner
        self.runner = self.runner_class(
            sandbox=self.sandbox,
            provider=runner_provider,
            **config,
        )

        # Inject load_skill tool if skills were discovered
        if self.load_skill_schema is not None and self.load_skill_handler is not None:
            # MainRunner (and compatible runners) expose tools/handlers lists
            if hasattr(self.runner, "tools") and hasattr(self.runner, "handlers"):
                self.runner.tools.append(self.load_skill_schema)
                self.runner.handlers["load_skill"] = self.load_skill_handler
                logger.info("Injected load_skill tool into runner")
            else:
                logger.warning(
                    f"Runner {self.runner_class.__name__} does not expose "
                    "tools/handlers for skill injection"
                )

    async def run(self, task: str) -> AgentResult:
        """Run a task using the agent's configured runner.

        Delegates to the runner that was instantiated during load().
        The runner has access to all configured tools plus the load_skill
        tool if skills were discovered.

        Args:
            task: The task or prompt for the agent to process.

        Returns:
            AgentResult with the response and conversation history.

        Raises:
            RuntimeError: If agent is not loaded or no runner is configured.

        Example:
            >>> await agent.load()
            >>> result = await agent.run("Find all Python files and summarize them")
            >>> print(result.message)
        """
        if not self._is_loaded:
            raise RuntimeError(
                f"Agent {self.agent_id} is not loaded. Call load() first."
            )

        if self.runner is None:
            raise RuntimeError(
                f"Agent {self.agent_id} has no runner configured. "
                "Pass runner and runner_config to Agent() to enable run()."
            )

        logger.info(f"Agent {self.agent_id} running task: {task[:50]}...")
        result = await self.runner.run(task)
        logger.info(f"Agent {self.agent_id} completed task (success={result.success})")

        return result

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

    async def setup_mcp_servers(
        self, servers_config: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Path]:
        """Setup MCP servers and generate tool files in the sandbox.

        This method fetches tools from each configured MCP server and generates
        Python wrapper files in the src/servers/<server-name>/ directory within
        the agent's repository.

        Args:
            servers_config: Dictionary mapping server names to their configurations.
                           Each config should include 'command', 'args', and optionally 'env'.

        Returns:
            Dictionary mapping server names to their generated directories.

        Raises:
            RuntimeError: If git repo is not initialized or if MCP setup fails.

        Example:
            >>> servers = {
            ...     "filesystem": {
            ...         "command": "npx",
            ...         "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
            ...     }
            ... }
            >>> await agent.setup_mcp_servers(servers)
        """
        if self.git_repo is None:
            raise RuntimeError(
                f"Agent {self.agent_id} repository not initialized. Call load() first."
            )

        import asyncio
        from tempfile import TemporaryDirectory

        from skillfs.mcp import MCPServerManager

        logger.info(f"Setting up {len(servers_config)} MCP servers for agent {self.agent_id}")

        sandbox_servers_base = f"{self.repo_root}/src/servers"

        # Create a temporary directory on the host machine for generation
        with TemporaryDirectory() as tmpdir:
            tmp_servers_dir = Path(tmpdir) / "servers"
            tmp_servers_dir.mkdir()

            # Setup MCP servers and generate files locally
            manager = MCPServerManager(tmp_servers_dir)
            server_dirs = await manager.setup_multiple_servers(servers_config)

            # Upload each server directory to sandbox in parallel
            upload_tasks = []
            results = {}

            for server_name, local_dir in server_dirs.items():
                # Extract normalized directory name from the local path
                normalized_name = local_dir.name
                remote_dir = f"{sandbox_servers_base}/{normalized_name}"
                logger.info(f"Uploading {server_name} tools to {remote_dir}")
                upload_tasks.append(self.sandbox.upload_directory(local_dir, remote_dir))
                results[server_name] = Path(remote_dir)

            # Execute all uploads in parallel
            await asyncio.gather(*upload_tasks)

            logger.info(f"Successfully setup {len(results)} MCP servers in sandbox")
            return results

    async def setup_skills(
        self, skills_config: Dict[str, Any]
    ) -> Dict[str, Path]:
        """Setup skills by uploading skill folders to the sandbox.

        This method processes skill sources from the configuration and uploads
        contents to the src/skills/ directory within the agent's repository.

        The provided path should be a directory CONTAINING skill folders. Each
        subdirectory within the path is treated as a skill and uploaded to
        src/skills/<skill_name>/. Top-level files (e.g., README.md, SKILL.md)
        are also uploaded to src/skills/.

        Args:
            skills_config: Dictionary with skill source configurations.
                          Supports:
                          - {"local": "/path" or ["/path1", "/path2"]}
                          - {"github": "url" or ["url1", "url2"] or {"url": ..., "ref": ..., "path": ...}}

                          GitHub options:
                          - url: Repository URL (required)
                          - ref: Branch, tag, or commit to clone (optional)
                          - path: Subfolder within repo to use (optional)

                          Local paths: each subdirectory becomes a skill folder.
                          GitHub: the repo (or subfolder) becomes a skill folder named after
                          the repo or the last segment of path.
                          Local paths take precedence over github.

        Returns:
            Dictionary mapping skill/file names to their sandbox paths.

        Raises:
            RuntimeError: If git repo is not initialized.

        Example:
            >>> # Local skills (each subdirectory becomes a skill)
            >>> skills = {"local": "/path/to/skills"}
            >>> await agent.setup_skills(skills)
            >>>
            >>> # GitHub (repo becomes skills/skills-repo/)
            >>> skills = {"github": "https://github.com/user/skills-repo"}
            >>> await agent.setup_skills(skills)
            >>>
            >>> # GitHub with ref and path (becomes skills/browser/)
            >>> skills = {"github": {
            ...     "url": "https://github.com/user/plugins",
            ...     "ref": "main",
            ...     "path": "skills/browser"
            ... }}
            >>> await agent.setup_skills(skills)
        """
        if self.git_repo is None:
            raise RuntimeError(
                f"Agent {self.agent_id} repository not initialized. Call load() first."
            )

        import asyncio

        # Common artifacts to filter out
        FILTERED_ITEMS = {
            ".DS_Store",
            "Thumbs.db",
            "__pycache__",
            ".git",
            ".gitignore",
            ".pytest_cache",
        }

        sandbox_skills_base = f"{self.repo_root}/src/skills"

        # Track which items come from which paths (for collision logging)
        # Separate tracking for folders and files
        skill_folder_sources: Dict[str, List[str]] = {}
        file_sources: Dict[str, List[str]] = {}
        # Track which items we've already uploaded (first-wins)
        uploaded_items: Dict[str, Path] = {}
        # Track which source actually uploaded each item (for accurate collision logging)
        uploaded_by: Dict[str, str] = {}

        # Normalize local paths to a list
        local_paths: List[str] = []
        if "local" in skills_config:
            local_value = skills_config["local"]
            if isinstance(local_value, str):
                local_paths = [local_value]
            elif isinstance(local_value, list):
                local_paths = local_value

        # Normalize github configs to a list of dicts
        github_configs: List[Dict[str, str]] = []
        if "github" in skills_config:
            github_value = skills_config["github"]
            if isinstance(github_value, str):
                github_configs = [{"url": github_value}]
            elif isinstance(github_value, dict):
                github_configs = [github_value]
            elif isinstance(github_value, list):
                for item in github_value:
                    if isinstance(item, str):
                        github_configs.append({"url": item})
                    elif isinstance(item, dict):
                        github_configs.append(item)

        logger.info(f"Setting up skills from {len(local_paths)} local path(s) and {len(github_configs)} github repo(s)")

        dir_upload_tasks: List[Any] = []
        file_upload_tasks: List[tuple[Path, str]] = []

        # Helper to process a source directory (shared between local and github)
        def process_source_directory(source_path: Path, source_label: str) -> None:
            """Process a directory containing skill folders and files."""
            for item in source_path.iterdir():
                # Skip filtered items
                if item.name in FILTERED_ITEMS:
                    continue

                item_name = item.name

                if item.is_dir():
                    # Handle skill folders
                    if item_name not in skill_folder_sources:
                        skill_folder_sources[item_name] = []
                    skill_folder_sources[item_name].append(source_label)

                    # First-wins: skip if already uploaded
                    if item_name in uploaded_items:
                        continue

                    # Check if skill folder is empty (after filtering)
                    skill_contents = [
                        f for f in item.iterdir()
                        if f.name not in FILTERED_ITEMS
                    ]
                    if not skill_contents:
                        logger.info(f"Skill folder '{item_name}' is empty, skipping")
                        continue

                    # Queue directory upload with filtering
                    remote_dir = f"{sandbox_skills_base}/{item_name}"
                    dir_upload_tasks.append(
                        self.sandbox.upload_directory(item, remote_dir, exclude=FILTERED_ITEMS)
                    )
                    uploaded_items[item_name] = Path(remote_dir)
                    uploaded_by[item_name] = source_label

                elif item.is_file():
                    # Handle top-level files
                    if item_name not in file_sources:
                        file_sources[item_name] = []
                    file_sources[item_name].append(source_label)

                    # First-wins: skip if already uploaded
                    if item_name in uploaded_items:
                        continue

                    # Queue file upload (store paths for async upload later)
                    remote_path = f"{sandbox_skills_base}/{item_name}"
                    file_upload_tasks.append((item, remote_path))
                    uploaded_items[item_name] = Path(remote_path)
                    uploaded_by[item_name] = source_label

        # Process local paths first (they take precedence)
        for source_path_str in local_paths:
            source_path = Path(source_path_str)

            if not source_path.exists():
                logger.warning(f"Skills path '{source_path}' does not exist, skipping")
                continue

            if not source_path.is_dir():
                logger.warning(f"Skills path '{source_path}' is not a directory, skipping")
                continue

            process_source_directory(source_path, str(source_path))

        # Helper to extract repo name from GitHub URL
        def get_repo_name(url: str) -> str:
            """Extract repository name from GitHub URL."""
            url = url.rstrip("/")
            if url.endswith(".git"):
                url = url[:-4]
            return url.split("/")[-1]

        # Process GitHub repos (each repo/subfolder becomes a skill folder)
        temp_dirs: List[tempfile.TemporaryDirectory] = []
        for github_config in github_configs:
            url = github_config.get("url") or ""
            ref = github_config.get("ref")  # Optional branch/tag/commit
            subpath = (github_config.get("path") or "").strip("/")  # Optional subfolder

            if not url:
                logger.warning("GitHub config missing 'url', skipping")
                continue

            # Skill folder name: last segment of path if specified, else repo name
            if subpath:
                skill_name = subpath.split("/")[-1]
            else:
                skill_name = get_repo_name(url)

            # Create temp directory for cloning
            temp_dir = tempfile.TemporaryDirectory()
            temp_dirs.append(temp_dir)
            clone_path = Path(temp_dir.name)

            # Build git clone command
            clone_cmd = ["git", "clone", "--depth", "1"]
            if ref:
                clone_cmd.extend(["--branch", ref])
            clone_cmd.extend([url, str(clone_path)])

            logger.info(f"Cloning {url}" + (f" (ref: {ref})" if ref else "") + " to temp directory")
            try:
                result = subprocess.run(
                    clone_cmd,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                if result.returncode != 0:
                    logger.warning(f"Failed to clone {url}: {result.stderr}")
                    continue
            except subprocess.TimeoutExpired:
                logger.warning(f"Timeout cloning {url}, skipping")
                continue
            except Exception as e:
                logger.warning(f"Error cloning {url}: {e}")
                continue

            # Determine source path (whole repo or subfolder)
            source_path = clone_path / subpath if subpath else clone_path
            if not source_path.exists() or not source_path.is_dir():
                logger.warning(f"Path '{subpath}' not found in {url}, skipping")
                continue

            # Track collision for skill name
            if skill_name not in skill_folder_sources:
                skill_folder_sources[skill_name] = []
            skill_folder_sources[skill_name].append(url + (f":{subpath}" if subpath else ""))

            # First-wins: skip if already uploaded
            if skill_name in uploaded_items:
                continue

            # Check if source is empty (after filtering)
            source_contents = [
                f for f in source_path.iterdir()
                if f.name not in FILTERED_ITEMS
            ]
            if not source_contents:
                logger.info(f"GitHub skill '{skill_name}' is empty, skipping")
                continue

            # Upload as a skill folder
            remote_dir = f"{sandbox_skills_base}/{skill_name}"
            dir_upload_tasks.append(
                self.sandbox.upload_directory(source_path, remote_dir, exclude=FILTERED_ITEMS)
            )
            uploaded_items[skill_name] = Path(remote_dir)
            uploaded_by[skill_name] = url + (f":{subpath}" if subpath else "")

        # Helper for async file upload
        async def upload_file_async(local_file: Path, remote_file: str) -> None:
            await asyncio.to_thread(self.sandbox.upload_file, local_file, remote_file)

        # Execute all uploads in parallel
        all_tasks = dir_upload_tasks + [
            upload_file_async(local_file, remote_file)
            for local_file, remote_file in file_upload_tasks
        ]
        if all_tasks:
            await asyncio.gather(*all_tasks)

        # Cleanup temp directories from GitHub clones
        for temp_dir in temp_dirs:
            temp_dir.cleanup()

        # Log collision summary for skill folders
        for skill_name, sources in skill_folder_sources.items():
            if len(sources) > 1 and skill_name in uploaded_by:
                used = uploaded_by[skill_name]
                skipped = [s for s in sources if s != used]
                logger.info(
                    f"Skill '{skill_name}' found in {len(sources)} locations: "
                    f"{used} (used), {', '.join(skipped)} (skipped)"
                )

        # Log collision summary for files
        for file_name, sources in file_sources.items():
            if len(sources) > 1 and file_name in uploaded_by:
                used = uploaded_by[file_name]
                skipped = [s for s in sources if s != used]
                logger.info(
                    f"File '{file_name}' found in {len(sources)} locations: "
                    f"{used} (used), {', '.join(skipped)} (skipped)"
                )

        num_folders = len([k for k in uploaded_items if k in skill_folder_sources])
        num_files = len([k for k in uploaded_items if k in file_sources])
        logger.info(f"Successfully setup {num_folders} skill(s) and {num_files} file(s) in sandbox")
        return uploaded_items

    @property
    def is_loaded(self) -> bool:
        """Check if agent state is currently loaded."""
        return self._is_loaded

    def __repr__(self) -> str:
        """String representation of the agent."""
        status = "loaded" if self._is_loaded else "not loaded"
        return f"Agent(id={self.agent_id}, status={status})"
