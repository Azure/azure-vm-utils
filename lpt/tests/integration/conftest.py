import datetime
import logging
import os
import random
import string
import subprocess
from pathlib import Path

import pytest
import whatismyip  # type: ignore

from lpt.clouds.azure import Azure
from lpt.ssh import SSH

logger = logging.getLogger(__name__)


def pytest_configure(config):
    output_dir = Path(os.environ.get("LPT_TEST_OUTPUT_DIR", "/tmp/lpt-tests"))
    output_dir.mkdir(exist_ok=True, parents=True)

    worker_id = os.environ.get("PYTEST_XDIST_WORKER")
    if worker_id is None:
        return

    output_file = output_dir / f"{worker_id}.log"

    logging.basicConfig(
        filename=str(output_file),
        format="%(asctime)s.%(msecs)03d|%(levelname)s|%(name)s:%(module)s:%(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


@pytest.fixture(autouse=True)
def cleanup_logging():
    logging.getLogger("azure").setLevel(logging.WARNING)
    # logging.getLogger("paramiko").setLevel(logging.WARNING)
    # logging.getLogger("paramiko").propagate = False


@pytest.fixture
def restrict_ssh_source_ip():
    try:
        yield os.environ["LPT_TESTS_AZURE_RESTRICT_SOURCE_IP"]
    except KeyError:
        yield whatismyip.whatismyipv4()


@pytest.fixture
def admin_username():
    yield os.environ.get("LPT_TESTS_AZURE_ADMIN_USERNAME", "testuser")


@pytest.fixture
def admin_password():
    yield os.environ.get("LPT_TESTS_AZURE_ADMIN_PASSWORD")


@pytest.fixture
def azure():
    yield Azure(os.environ["LPT_TEST_AZURE_SUBSCRIPTION_ID"])


@pytest.fixture
def rg(azure, rg_location, rg_name):
    rg = azure.rg_create(rg_name, location=rg_location)
    try:
        yield rg
    finally:
        azure.rg_delete(rg, wait=False)


@pytest.fixture
def rg_location():
    yield os.environ.get("LPT_TESTS_AZURE_LOCATION", "eastus")


@pytest.fixture
def common_name():
    extra = "".join(random.choice(string.digits) for i in range(4))
    yield datetime.datetime.utcnow().strftime(f"t%m%d%Y%H%M%S%f{extra}")


@pytest.fixture
def rg_name(common_name):
    yield f"deleteme-{common_name}-rg"


@pytest.fixture
def vm_name(common_name):
    yield f"deleteme-{common_name}-vm"


@pytest.fixture
def ssh_keys(tmp_path: Path, vm_name: str):
    tmp_path.mkdir(exist_ok=True, parents=True)
    public_key = tmp_path / (vm_name + ".pub")
    private_key = tmp_path / vm_name

    subprocess.run(
        ["ssh-keygen", "-f", private_key.as_posix(), "-N", "", "-t", "rsa"],
        check=True,
        capture_output=True,
    )
    logger.debug("created ssh key: %s %s", public_key, private_key)

    yield public_key, private_key

    public_key.unlink()
    private_key.unlink()


@pytest.fixture
def ssh(ssh_keys, admin_username):
    proxy_host = os.environ.get("LPT_TESTS_AZURE_SSH_PROXY_HOST")
    proxy_user = os.environ.get("LPT_TESTS_AZURE_SSH_PROXY_USER")
    public_key, private_key = ssh_keys
    yield SSH(
        host=None,
        user=admin_username,
        proxy_host=proxy_host,
        proxy_user=proxy_user,
        private_key=private_key,
        public_key=public_key,
    )
