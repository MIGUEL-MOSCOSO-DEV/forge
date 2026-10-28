import os
from pathlib import Path


def data_dir():
    root = Path(os.environ.get("FORGE_HOME", Path.home() / ".forge"))
    root.mkdir(parents=True, exist_ok=True)
    return root
