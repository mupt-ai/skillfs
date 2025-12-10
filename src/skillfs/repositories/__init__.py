"""Git repository management for SkillFS."""

from skillfs.repositories.constants import (
    DEFAULT_GIT_USER_EMAIL,
    DEFAULT_GIT_USER_NAME,
    DEFAULT_GITIGNORE,
)
from skillfs.repositories.git_repo import GitRepo

__all__ = [
    "GitRepo",
    "DEFAULT_GITIGNORE",
    "DEFAULT_GIT_USER_NAME",
    "DEFAULT_GIT_USER_EMAIL",
]
