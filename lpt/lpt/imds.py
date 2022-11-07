import dataclasses
import json
import logging
import subprocess
from pathlib import Path
from typing import Dict

from .ssh import SSH

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class InstanceMetadata:
    metadata: Dict

    @classmethod
    def load_remote(cls, ssh: SSH, *, output_dir: Path) -> "InstanceMetadata":
        return cls.load(output_dir=output_dir, run=ssh.run)

    @classmethod
    def load(cls, *, output_dir: Path, run=subprocess.run) -> "InstanceMetadata":
        cmd = [
            "curl",
            "-H",
            "Metadata: true",
            "http://169.254.169.254/metadata/instance?api-version=2019-06-01",
        ]
        try:
            logger.debug("executing: %r", cmd)
            proc = run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as error:
            logger.error("cmd (%r) failed (error=%r)", cmd, error)

        metadata = json.loads(proc.stdout)

        out = output_dir / "imds.json"
        out.write_text(proc.stdout)

        return InstanceMetadata(metadata=metadata)
