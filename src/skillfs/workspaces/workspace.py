"""Workspace class for managing persistent sandbox state."""

import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from skillfs.workspaces.persistence import load_agent_state, save_agent_state
from skillfs.workspaces.git_commit import create_git_commit_tool
from skillfs.repositories.git_repo import GitRepo
from skillfs.sandboxes.base import SandboxConnection
from skillfs.skills.catalog import SkillCatalog
from skillfs.storage.base import BundleStore

logger = logging.getLogger(__name__)


class Workspace:
    """Persistent, version-controlled sandbox for AI agents.

    Workspace handles the infrastructure: load state, save state, setup MCP servers,
    manage skills. Bring your own LLM loop.

    Example:
        >>> from skillfs.sandboxes import E2BSandbox
        >>> from skillfs.storage import LocalBundleStore
        >>> from skillfs.workspaces import Workspace
        >>>
        >>> sandbox = E2BSandbox.create()
        >>> store = LocalBundleStore(directory="/tmp/workspaces")
        >>>
        >>> workspace = Workspace(
        >>>     workspace_id="my-workspace",
        >>>     sandbox=sandbox,
        >>>     store=store,
        >>>     mcp_servers={"playwright": {"command": "npx", "args": ["@playwright/mcp@latest"]}},
        >>>     generate_mcp_tools=True,
        >>> )
        >>>
        >>> await workspace.load()  # Restore from bundle if exists
        >>>
        >>> # Use sandbox directly or with your own agent
        >>> workspace.sandbox.run_command("ls -la")
        >>> workspace.sandbox.write_file("hello.txt", "Hello, world!")
        >>>
        >>> workspace.save()  # Commit and upload git bundle
        >>> sandbox.close()
    """

    def __init__(
        self,
        workspace_id: str,
        sandbox: SandboxConnection,
        store: BundleStore,
        repo_root: Optional[str] = None,
        mcp_servers: Optional[Dict[str, Dict[str, Any]]] = None,
        generate_mcp_tools: bool = False,
        skills: Optional[Dict[str, Any]] = None,
        load_skills: bool = False,
    ):
        """Initialize workspace instance.

        Args:
            workspace_id: Unique identifier for this workspace.
            sandbox: Active sandbox connection where workspace operates.
            store: Storage backend for persisting workspace state.
            repo_root: Path inside sandbox for the Git repository.
                If None, uses sandbox.default_repo_root.
            mcp_servers: Optional MCP server configurations.
                        Format: {"server-name": {"command": "...", "args": [...], "env": {...}}}
            generate_mcp_tools: If True, generate MCP tool wrappers during load.
            skills: Optional skills configuration.
                   Format: {"local": "/path/to/skills" or ["/path1", "/path2"]}
            load_skills: If True, load skills from configured sources during load.

        After load(), the following attributes are available:
            git_repo: GitRepo instance for the workspace's repository.
            skill_catalog: SkillCatalog with discovered SKILL.md files.
        """
        self.workspace_id = workspace_id
        self.sandbox = sandbox
        self.store = store
        self.repo_root = repo_root if repo_root is not None else sandbox.default_repo_root
        self.mcp_servers = mcp_servers or {}
        self.generate_mcp_tools = generate_mcp_tools
        self.skills = skills or {}
        self.load_skills = load_skills
        self.git_repo: Optional[GitRepo] = None
        self.skill_catalog: Optional[SkillCatalog] = None
        self._is_loaded = False

        logger.info(f"Created workspace: {workspace_id}")

    async def load(self) -> None:
        """Load workspace state from storage into sandbox.

        Downloads bundle from storage if it exists and restores the Git repository.
        If no bundle exists, initializes a fresh repository.
        If MCP servers are configured, sets them up after loading.

        Raises:
            RuntimeError: If workspace is already loaded.
        """
        if self._is_loaded:
            raise RuntimeError(
                f"Workspace {self.workspace_id} is already loaded. "
                "Call save() and create a new Workspace instance if you need to reload."
            )

        logger.info(f"Loading workspace {self.workspace_id}")

        self.git_repo = load_agent_state(
            agent_id=self.workspace_id,
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
        self.skill_catalog = SkillCatalog(
            sandbox=self.sandbox,
            repo_root=self.repo_root,
        )
        num_skills = await self.skill_catalog.scan()
        if num_skills > 0:
            logger.info(f"Discovered {num_skills} skill(s) in sandbox")

        self._is_loaded = True
        logger.info(f"Workspace {self.workspace_id} loaded successfully")

    def save(self, commit_message: Optional[str] = None) -> None:
        """Save workspace state from sandbox to storage.

        Commits pending changes, creates a Git bundle, and uploads it to storage.

        Args:
            commit_message: Optional custom commit message. If None, generates
                          a default message with timestamp.

        Raises:
            RuntimeError: If workspace is not loaded.
        """
        if not self._is_loaded or self.git_repo is None:
            raise RuntimeError(
                f"Workspace {self.workspace_id} is not loaded. Call load() first."
            )

        logger.info(f"Saving workspace {self.workspace_id}")

        save_agent_state(
            agent_id=self.workspace_id,
            sandbox=self.sandbox,
            git_repo=self.git_repo,
            bundle_store=self.store,
            commit_message=commit_message,
        )

        logger.info(f"Workspace {self.workspace_id} saved successfully")

    def get_commit_tool(self) -> tuple[Dict[str, Any], Any]:
        """Get the git_commit tool schema and handler.

        Returns a tool that commits changes and saves state to storage.
        Add this to your runner's tools to enable checkpointing.

        Returns:
            Tuple of (schema, handler) to add to a runner.

        Raises:
            RuntimeError: If workspace is not loaded.

        Example:
            >>> schema, handler = workspace.get_commit_tool()
            >>> runner.tools.append(schema)
            >>> runner.handlers["git_commit"] = handler
        """
        if not self._is_loaded or self.git_repo is None:
            raise RuntimeError(
                f"Workspace {self.workspace_id} is not loaded. Call load() first."
            )

        return create_git_commit_tool(
            sandbox=self.sandbox,
            git_repo=self.git_repo,
            bundle_store=self.store,
            agent_id=self.workspace_id,
        )

    async def setup_mcp_servers(
        self, servers_config: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Path]:
        """Setup MCP servers and generate tool files in the sandbox.

        Fetches tools from each configured MCP server and generates Python wrapper
        files in src/servers/<server-name>/.

        Args:
            servers_config: Dictionary mapping server names to their configurations.
                           Each config should include 'command', 'args', and optionally 'env'.

        Returns:
            Dictionary mapping server names to their generated directories.

        Raises:
            RuntimeError: If git repo is not initialized.
        """
        if self.git_repo is None:
            raise RuntimeError(
                f"Workspace {self.workspace_id} repository not initialized. Call load() first."
            )

        import asyncio
        from tempfile import TemporaryDirectory

        from skillfs.mcp import MCPServerManager

        logger.info(f"Setting up {len(servers_config)} MCP servers")

        sandbox_servers_base = f"{self.repo_root}/src/servers"

        with TemporaryDirectory() as tmpdir:
            tmp_servers_dir = Path(tmpdir) / "servers"
            tmp_servers_dir.mkdir()

            manager = MCPServerManager(tmp_servers_dir)
            server_dirs = await manager.setup_multiple_servers(servers_config)

            upload_tasks = []
            results = {}

            for server_name, local_dir in server_dirs.items():
                normalized_name = local_dir.name
                remote_dir = f"{sandbox_servers_base}/{normalized_name}"
                logger.info(f"Uploading {server_name} tools to {remote_dir}")
                upload_tasks.append(self.sandbox.upload_directory(local_dir, remote_dir))
                results[server_name] = Path(remote_dir)

            await asyncio.gather(*upload_tasks)

            logger.info(f"Successfully setup {len(results)} MCP servers")
            return results

    async def setup_skills(
        self, skills_config: Dict[str, Any]
    ) -> Dict[str, Path]:
        """Setup skills by uploading skill folders to the sandbox.

        Args:
            skills_config: Dictionary with skill source configurations.
                          Supports:
                          - {"local": "/path" or ["/path1", "/path2"]}
                          - {"github": "url" or ["url1", "url2"] or {"url": ..., "ref": ..., "path": ...}}

        Returns:
            Dictionary mapping skill/file names to their sandbox paths.

        Raises:
            RuntimeError: If git repo is not initialized.
        """
        if self.git_repo is None:
            raise RuntimeError(
                f"Workspace {self.workspace_id} repository not initialized. Call load() first."
            )

        import asyncio

        FILTERED_ITEMS = {
            ".DS_Store",
            "Thumbs.db",
            "__pycache__",
            ".git",
            ".gitignore",
            ".pytest_cache",
        }

        sandbox_skills_base = f"{self.repo_root}/src/skills"

        skill_folder_sources: Dict[str, List[str]] = {}
        file_sources: Dict[str, List[str]] = {}
        uploaded_items: Dict[str, Path] = {}
        uploaded_by: Dict[str, str] = {}

        local_paths: List[str] = []
        if "local" in skills_config:
            local_value = skills_config["local"]
            if isinstance(local_value, str):
                local_paths = [local_value]
            elif isinstance(local_value, list):
                local_paths = local_value

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

        def process_source_directory(source_path: Path, source_label: str) -> None:
            for item in source_path.iterdir():
                if item.name in FILTERED_ITEMS:
                    continue

                item_name = item.name

                if item.is_dir():
                    if item_name not in skill_folder_sources:
                        skill_folder_sources[item_name] = []
                    skill_folder_sources[item_name].append(source_label)

                    if item_name in uploaded_items:
                        continue

                    skill_contents = [
                        f for f in item.iterdir()
                        if f.name not in FILTERED_ITEMS
                    ]
                    if not skill_contents:
                        logger.info(f"Skill folder '{item_name}' is empty, skipping")
                        continue

                    remote_dir = f"{sandbox_skills_base}/{item_name}"
                    dir_upload_tasks.append(
                        self.sandbox.upload_directory(item, remote_dir, exclude=FILTERED_ITEMS)
                    )
                    uploaded_items[item_name] = Path(remote_dir)
                    uploaded_by[item_name] = source_label

                elif item.is_file():
                    if item_name not in file_sources:
                        file_sources[item_name] = []
                    file_sources[item_name].append(source_label)

                    if item_name in uploaded_items:
                        continue

                    remote_path = f"{sandbox_skills_base}/{item_name}"
                    file_upload_tasks.append((item, remote_path))
                    uploaded_items[item_name] = Path(remote_path)
                    uploaded_by[item_name] = source_label

        for source_path_str in local_paths:
            source_path = Path(source_path_str)

            if not source_path.exists():
                logger.warning(f"Skills path '{source_path}' does not exist, skipping")
                continue

            if not source_path.is_dir():
                logger.warning(f"Skills path '{source_path}' is not a directory, skipping")
                continue

            process_source_directory(source_path, str(source_path))

        def get_repo_name(url: str) -> str:
            url = url.rstrip("/")
            if url.endswith(".git"):
                url = url[:-4]
            return url.split("/")[-1]

        temp_dirs: List[tempfile.TemporaryDirectory] = []
        for github_config in github_configs:
            url = github_config.get("url") or ""
            ref = github_config.get("ref")
            subpath = (github_config.get("path") or "").strip("/")

            if not url:
                logger.warning("GitHub config missing 'url', skipping")
                continue

            if subpath:
                skill_name = subpath.split("/")[-1]
            else:
                skill_name = get_repo_name(url)

            temp_dir = tempfile.TemporaryDirectory()
            temp_dirs.append(temp_dir)
            clone_path = Path(temp_dir.name)

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

            source_path = clone_path / subpath if subpath else clone_path
            if not source_path.exists() or not source_path.is_dir():
                logger.warning(f"Path '{subpath}' not found in {url}, skipping")
                continue

            if skill_name not in skill_folder_sources:
                skill_folder_sources[skill_name] = []
            skill_folder_sources[skill_name].append(url + (f":{subpath}" if subpath else ""))

            if skill_name in uploaded_items:
                continue

            source_contents = [
                f for f in source_path.iterdir()
                if f.name not in FILTERED_ITEMS
            ]
            if not source_contents:
                logger.info(f"GitHub skill '{skill_name}' is empty, skipping")
                continue

            remote_dir = f"{sandbox_skills_base}/{skill_name}"
            dir_upload_tasks.append(
                self.sandbox.upload_directory(source_path, remote_dir, exclude=FILTERED_ITEMS)
            )
            uploaded_items[skill_name] = Path(remote_dir)
            uploaded_by[skill_name] = url + (f":{subpath}" if subpath else "")

        async def upload_file_async(local_file: Path, remote_file: str) -> None:
            await asyncio.to_thread(self.sandbox.upload_file, local_file, remote_file)

        all_tasks = dir_upload_tasks + [
            upload_file_async(local_file, remote_file)
            for local_file, remote_file in file_upload_tasks
        ]
        if all_tasks:
            await asyncio.gather(*all_tasks)

        for temp_dir in temp_dirs:
            temp_dir.cleanup()

        for skill_name, sources in skill_folder_sources.items():
            if len(sources) > 1 and skill_name in uploaded_by:
                used = uploaded_by[skill_name]
                skipped = [s for s in sources if s != used]
                logger.info(
                    f"Skill '{skill_name}' found in {len(sources)} locations: "
                    f"{used} (used), {', '.join(skipped)} (skipped)"
                )

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
        logger.info(f"Successfully setup {num_folders} skill(s) and {num_files} file(s)")
        return uploaded_items

    @property
    def is_loaded(self) -> bool:
        """Check if workspace state is currently loaded."""
        return self._is_loaded

    def __repr__(self) -> str:
        """String representation of the workspace."""
        status = "loaded" if self._is_loaded else "not loaded"
        return f"Workspace(id={self.workspace_id}, status={status})"
