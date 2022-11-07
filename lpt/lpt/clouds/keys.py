import logging
import subprocess
from pathlib import Path
from typing import Tuple

logger = logging.getLogger(__name__)


def generate_ssh_keys(dir_path: Path, name: str) -> Tuple[Path, Path]:
    """Generate keypair and return path to public, private keys."""
    dir_path.mkdir(exist_ok=True, parents=True)
    public_key = dir_path / (name + ".pub")
    private_key = dir_path / name

    subprocess.run(
        ["ssh-keygen", "-f", private_key.as_posix(), "-N", "", "-t", "rsa"],
        check=True,
        capture_output=True,
    )
    logger.debug("Created ssh key: %s %s", public_key, private_key)

    return public_key, private_key
