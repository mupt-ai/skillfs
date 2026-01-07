"""Git commit tool - stage changes, generate commit message, commit, and save bundle.

This tool enables agents to checkpoint their work by committing changes to the
Git repository and persisting the state to the bundle store.
"""

from typing import Any, Callable, Dict, Optional

from skillfs.repositories.git_repo import GitRepo
from skillfs.sandboxes.base import SandboxConnection
from skillfs.storage.base import BundleStore
from skillfs.workspaces.persistence import BUNDLE_PATH_TEMPLATE

import logging

logger = logging.getLogger(__name__)


SCHEMA = {
    "name": "git_commit",
    "description": """Commit current changes and save state to persistent storage.

This tool:
1. Shows the current diff and status
2. Stages all changes (git add -A)
3. Creates a commit with an auto-generated message (or custom if provided)
4. Creates a Git bundle and uploads it to storage

Use this to checkpoint your work. The commit message follows conventional commit format:
- feat: new feature or capability
- fix: bug fix
- refactor: code restructuring
- docs: documentation changes
- chore: maintenance tasks

Call this periodically to save progress, especially after completing significant changes.""",
    "input_schema": {
        "type": "object",
        "properties": {
            "message": {
                "type": "string",
                "description": "Optional custom commit message. If not provided, one will be auto-generated from the diff.",
            },
        },
        "required": [],
    },
}


def _generate_commit_message(status: str, diff: str) -> str:
    """Generate a conventional commit message from git status and diff.

    Args:
        status: Output of `git status --short`
        diff: Output of `git diff` (unstaged changes) or `git diff --cached` (staged)

    Returns:
        A conventional commit message.
    """
    if not status.strip():
        return "chore: no changes to commit"

    lines = status.strip().split("\n")

    # Parse status codes
    added = []
    modified = []
    deleted = []
    renamed = []

    for line in lines:
        if not line.strip():
            continue
        # Status format: XY filename (X=index, Y=worktree)
        # We care about the combined state
        code = line[:2]
        filename = line[3:].strip()

        # Handle renamed files (R with arrow)
        if " -> " in filename:
            filename = filename.split(" -> ")[-1]

        if "A" in code or "?" in code:
            added.append(filename)
        elif "M" in code:
            modified.append(filename)
        elif "D" in code:
            deleted.append(filename)
        elif "R" in code:
            renamed.append(filename)

    # Determine commit type based on changes
    # Check file extensions and paths for hints
    all_files = added + modified + deleted + renamed

    has_docs = any(
        f.endswith((".md", ".rst", ".txt")) or "doc" in f.lower() or "readme" in f.lower()
        for f in all_files
    )
    has_tests = any(
        "test" in f.lower() or f.endswith("_test.py") or f.startswith("test_")
        for f in all_files
    )
    has_config = any(
        f.endswith((".json", ".yaml", ".yml", ".toml", ".ini", ".cfg"))
        or f in ("Makefile", "Dockerfile", ".gitignore", "pyproject.toml", "package.json")
        for f in all_files
    )

    # Determine type
    if has_docs and not any([has_tests, has_config]) and len(modified) == 0:
        commit_type = "docs"
    elif has_tests and len(added) > len(modified):
        commit_type = "test"
    elif has_config and len(all_files) <= 2:
        commit_type = "chore"
    elif len(added) > 0 and len(modified) == 0 and len(deleted) == 0:
        commit_type = "feat"
    elif len(deleted) > len(added) and len(modified) == 0:
        commit_type = "refactor"
    elif len(modified) > 0:
        # Check diff content for hints
        if diff and ("fix" in diff.lower() or "bug" in diff.lower() or "error" in diff.lower()):
            commit_type = "fix"
        else:
            commit_type = "feat" if len(added) > len(modified) else "update"
    else:
        commit_type = "chore"

    # Build description
    parts = []
    if added:
        if len(added) == 1:
            parts.append(f"add {added[0]}")
        else:
            parts.append(f"add {len(added)} files")
    if modified:
        if len(modified) == 1:
            parts.append(f"update {modified[0]}")
        else:
            parts.append(f"update {len(modified)} files")
    if deleted:
        if len(deleted) == 1:
            parts.append(f"remove {deleted[0]}")
        else:
            parts.append(f"remove {len(deleted)} files")
    if renamed:
        if len(renamed) == 1:
            parts.append(f"rename to {renamed[0]}")
        else:
            parts.append(f"rename {len(renamed)} files")

    if not parts:
        description = "update files"
    else:
        description = ", ".join(parts)

    # Truncate if too long
    max_desc_len = 60
    if len(description) > max_desc_len:
        description = description[:max_desc_len - 3] + "..."

    return f"{commit_type}: {description}"


def build_handler(
    sandbox: SandboxConnection,
    git_repo: GitRepo,
    bundle_store: BundleStore,
    agent_id: str,
) -> Callable[..., Dict[str, Any]]:
    """Build a git_commit handler with access to git repo and storage.

    Args:
        sandbox: The sandbox connection.
        git_repo: GitRepo instance for the agent's repository.
        bundle_store: Storage backend for bundles.
        agent_id: Agent identifier for bundle naming.

    Returns:
        Handler function for git_commit tool.
    """
    from pathlib import Path
    from tempfile import TemporaryDirectory

    def handle_git_commit(
        message: Optional[str] = None,
        **_: Any,
    ) -> Dict[str, Any]:
        """Commit changes and save to bundle store."""
        try:
            # Get current status and diff
            status = git_repo.status()
            diff = git_repo.diff()

            # Also get staged diff
            staged_result = git_repo._run("git diff --cached")
            staged_diff = staged_result.logs if staged_result.exit_code == 0 else ""

            # Check if there are any changes
            if not status.strip() and not staged_diff.strip():
                return {
                    "status": "no_changes",
                    "message": "No changes to commit",
                    "git_status": "",
                }

            # Generate commit message if not provided
            if message is None:
                combined_diff = diff + "\n" + staged_diff
                message = _generate_commit_message(status, combined_diff)

            # Stage all changes
            git_repo.add_all()

            # Commit
            commit_result = git_repo.commit(message)

            if commit_result.exit_code != 0:
                # Check for "nothing to commit" case
                if "nothing to commit" in (commit_result.logs or "").lower():
                    return {
                        "status": "no_changes",
                        "message": "Nothing to commit (working tree clean)",
                        "git_status": status,
                    }
                return {
                    "error": f"Commit failed: {commit_result.error or commit_result.logs}"
                }

            # Create bundle
            remote_bundle = BUNDLE_PATH_TEMPLATE.format(agent_id=agent_id)
            git_repo.create_bundle(remote_bundle)

            # Download bundle from sandbox and upload to store
            with TemporaryDirectory() as tmpdir:
                local_bundle = Path(tmpdir) / f"{agent_id}.bundle"
                sandbox.download_file(remote_bundle, local_bundle)
                bundle_store.upload_bundle(agent_id, local_bundle)

            # Get commit hash
            hash_result = git_repo._run("git rev-parse --short HEAD")
            commit_hash = hash_result.logs.strip() if hash_result.exit_code == 0 else "unknown"

            return {
                "status": "committed",
                "commit_hash": commit_hash,
                "commit_message": message,
                "files_changed": status,
                "bundle_saved": True,
            }

        except Exception as e:
            logger.exception("git_commit failed")
            return {"error": str(e)}

    return handle_git_commit


def create_git_commit_tool(
    sandbox: SandboxConnection,
    git_repo: GitRepo,
    bundle_store: BundleStore,
    agent_id: str,
) -> tuple[Dict[str, Any], Callable[..., Dict[str, Any]]]:
    """Create the git_commit tool schema and handler.

    This is a convenience function that returns both the schema and handler
    together, for easy integration with runners.

    Args:
        sandbox: The sandbox connection.
        git_repo: GitRepo instance for the agent's repository.
        bundle_store: Storage backend for bundles.
        agent_id: Agent identifier for bundle naming.

    Returns:
        Tuple of (schema, handler).

    Example:
        >>> schema, handler = create_git_commit_tool(sandbox, git_repo, store, "agent-123")
        >>> tools.append(schema)
        >>> handlers["git_commit"] = handler
    """
    handler = build_handler(sandbox, git_repo, bundle_store, agent_id)
    return SCHEMA, handler
