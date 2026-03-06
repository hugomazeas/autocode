import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

REPO_PLATFORM: str = os.getenv("REPO_PLATFORM", "github")
REPO_TOKEN: str = os.getenv("REPO_TOKEN", "")
SSH_KEY_PATH: str = os.getenv("SSH_KEY_PATH", "")
SSH_PRIVATE_KEY: str = os.getenv("SSH_PRIVATE_KEY", "")
STAGING_URL: str = os.getenv("STAGING_URL", "")
MAX_TURNS: int = int(os.getenv("MAX_TURNS", "20"))
WORKSPACE_DIR: Path = Path(__file__).parent.parent / "workspace"

WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)


def validate():
    errors = []
    if not REPO_TOKEN:
        errors.append("REPO_TOKEN is required")
    if REPO_PLATFORM not in ("github", "gitlab", "bitbucket"):
        errors.append(f"REPO_PLATFORM must be github|gitlab|bitbucket, got {REPO_PLATFORM}")
    if errors:
        raise RuntimeError("Config errors: " + "; ".join(errors))
