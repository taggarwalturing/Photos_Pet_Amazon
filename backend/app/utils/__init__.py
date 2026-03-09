import os
from pathlib import Path


def get_pipeline_workspace() -> Path:
    """
    Return the pipeline workspace path.
    Reads PIPELINE_WORKSPACE from .env (via dotenv_values) and os.getenv,
    falling back to the legacy local path: backend/master_pipeline/pipeline_workspace
    """
    from dotenv import dotenv_values

    backend_dir = Path(__file__).resolve().parent.parent.parent  # backend/
    _env = dotenv_values(backend_dir / ".env")
    env_ws = _env.get("PIPELINE_WORKSPACE") or os.getenv("PIPELINE_WORKSPACE")
    if env_ws:
        return Path(env_ws)
    return backend_dir / "master_pipeline" / "pipeline_workspace"
