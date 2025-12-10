"""Constants for Git repository management."""

# Default .gitignore content for SkillFS repos
DEFAULT_GITIGNORE = """# Generated/cached files
__pycache__/
*.pyc
*.pyo
*.egg-info/
.pytest_cache/

# Environment
.env
.env.local
.venv/
venv/

# SkillFS directories
workspace/*
!workspace/.gitkeep
deps/

# OS files
.DS_Store
"""

# Default Git user configuration for agents
DEFAULT_GIT_USER_NAME = "skillfs-agent"
DEFAULT_GIT_USER_EMAIL = "agent@skillfs.local"
