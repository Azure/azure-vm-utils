import dataclasses
import io
import logging
import shlex
import socket
import subprocess
import time
from io import StringIO
from pathlib import Path
from typing import List, Optional, Union

import paramiko

logger = logging.getLogger("lpt.ssh")


class SystemReadyTimeout(Exception):
    def __init__(self, status: str) -> None:
        self.status = status


@dataclasses.dataclass
class SSH:
    user: str
    host: str
    client: Optional[paramiko.SSHClient] = None
    proxy_client: Optional[paramiko.SSHClient] = None
    proxy_host: Optional[str] = None
    proxy_user: Optional[str] = None
    proxy_sock: Optional[paramiko.Channel] = None
    private_key: Optional[Union[Path, str]] = None
    public_key: Optional[Path] = None
    transport: Optional[paramiko.Transport] = None

    def close(self) -> None:
        if self.client:
            logger.debug("closing client...")
            self.client.close()
            self.client = None

        if self.proxy_sock:
            logger.debug("closing proxy sock...")
            self.proxy_sock.close()
            self.proxy_sock = None

        if self.transport:
            logger.debug("closing proxy transport...")
            self.transport.close()
            self.transport = None

        if self.proxy_client:
            logger.debug("closing proxy client...")
            self.proxy_client.close()
            self.proxy_client = None

        logger.debug("closed client...")

    def connect(self) -> None:
        if self.private_key and isinstance(self.private_key, Path):
            pkey = paramiko.RSAKey.from_private_key_file(str(self.private_key))
        elif self.private_key and isinstance(self.private_key, str):
            pkey = paramiko.RSAKey.from_private_key(StringIO(self.private_key))
        else:
            pkey = None

        if not self.client:
            self.client = paramiko.SSHClient()

        if self.proxy_host:
            self.proxy_client = paramiko.SSHClient()
            self.proxy_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            logger.debug(
                "connecting to proxy ssh server (proxy_host=%s, proxy_user=%s)",
                self.proxy_host,
                self.proxy_user,
            )
            self.proxy_client.connect(
                hostname=self.proxy_host, username=self.proxy_user
            )
            logger.debug(
                "connected to proxy ssh server (proxy_host=%s, proxy_user=%s)",
                self.proxy_host,
                self.proxy_user,
            )

            self.transport = self.proxy_client.get_transport()
            if not self.transport:
                raise RuntimeError("unable to open transport")

            logger.debug("opening transport channel to %s...", self.host)
            self.proxy_sock = self.transport.open_channel(
                "direct-tcpip", (self.host, 22), ("", 0)
            )

        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        logger.debug(
            "connecting to ssh server (host=%s, user=%s)", self.host, self.user
        )
        self.client.connect(
            hostname=self.host,
            username=self.user,
            sock=self.proxy_sock,
            pkey=pkey,
        )
        logger.debug("connected to ssh server (host=%s, user=%s)", self.host, self.user)

    def connect_with_retries(self, attempts: int = 300, sleep: float = 1.0) -> bool:
        while True:
            attempts -= 1
            try:
                self.connect()
                return True
            except paramiko.ssh_exception.AuthenticationException as exc:
                logger.debug("failed auth: %r", exc)
            except paramiko.ssh_exception.BadHostKeyException as exc:
                logger.debug("failed to verify host key: %r", exc)
            except paramiko.ssh_exception.NoValidConnectionsError as exc:
                logger.debug("failed to connect: %r", exc)
            except paramiko.ssh_exception.SSHException as exc:
                logger.debug("failed to connect: %r", exc)
            except TimeoutError as exc:
                logger.debug("failed to conenct due to timeout: %r", exc)
            except socket.error as exc:
                logger.debug("failed to connect due to socket error: %r", exc)

            self.close()

            if attempts <= 0:
                break

            time.sleep(sleep)

        return False

    def fetch(self, remote_path: Path, local_path: Path) -> None:
        cmd = ["cat", str(remote_path)]

        proc = self.run(cmd, capture_output=True, check=False)
        if proc.returncode != 0:
            logger.debug("falling back to fetching %r with sudo...", remote_path)
            cmd.insert(0, "sudo")
            try:
                proc = self.run(cmd, capture_output=True, check=True)
            except subprocess.CalledProcessError as exc:
                logger.debug("failed to fetch file %r: %r", remote_path, exc)
                raise FileNotFoundError(2, "No such file or directory") from exc

        assert isinstance(proc.stdout, bytes)
        local_path.write_bytes(proc.stdout)

    def fetch_binary(self, remote_path: Path) -> bytes:
        cmd = ["cat", str(remote_path)]

        proc = self.run(cmd, capture_output=True, check=False)
        if proc.returncode != 0:
            logger.debug("falling back to fetching %r with sudo...", remote_path)
            cmd.insert(0, "sudo")
            try:
                proc = self.run(cmd, capture_output=True, check=True)
            except subprocess.CalledProcessError as exc:
                logger.debug("failed to fetch file %r: %r", remote_path, exc)
                raise FileNotFoundError(2, "No such file or directory") from exc

        assert isinstance(proc.stdout, bytes)
        return proc.stdout

    def fetch_text(self, remote_path: Path) -> str:
        cmd = ["cat", str(remote_path)]

        proc = self.run(cmd, capture_output=True, check=False, text=True)
        if proc.returncode != 0:
            logger.debug("falling back to fetching %r with sudo...", remote_path)
            cmd.insert(0, "sudo")
            try:
                proc = self.run(cmd, capture_output=True, check=True, text=True)
            except subprocess.CalledProcessError as exc:
                logger.debug("failed to fetch file %r: %r", remote_path, exc)
                raise FileNotFoundError(2, "No such file or directory") from exc

        assert isinstance(proc.stdout, str)
        return proc.stdout

    def run(  # pylint: disable=too-many-locals,too-many-statements
        self,
        cmd: List[str],
        *,
        capture_output: bool = False,
        check: bool = False,
        text: bool = False,
        timeout: float = 300.0,
        recv_len: int = 64 * 1024,
        relax_duration: float = 0.02,
    ) -> subprocess.CompletedProcess:
        stderr_out: Union[bytes, str, None] = b""
        stdout_out: Union[bytes, str, None] = b""
        cmd_string = shlex.join(cmd)

        assert self.client

        logger.debug("opening ssh channel...")
        transport = self.client.get_transport()
        assert transport

        channel = transport.open_session()
        channel.settimeout(timeout)

        logger.debug("running command: %r", cmd_string)
        channel.exec_command(cmd_string)

        logger.debug("shutting down write...")
        channel.shutdown_write()

        stdout_io = io.BytesIO()
        stderr_io = io.BytesIO()

        while (
            not channel.exit_status_ready()
            or channel.recv_ready()
            or channel.recv_stderr_ready()
            or not channel.eof_received
        ):
            exited = channel.exit_status_ready()
            pending_data = channel.recv_ready() or channel.recv_stderr_ready()

            if not exited:
                logger.debug("waiting for command to exit: %r", cmd_string)
            elif pending_data:
                logger.debug("reading pending data: %r", cmd_string)
            else:
                logger.debug("waiting for channel eof: %r", cmd_string)

            if channel.recv_ready():
                logger.debug("reading stdout...")
                data = channel.recv(recv_len)
                while data:
                    logger.debug("read stdout: %d bytes", len(data))
                    stdout_io.write(data)
                    logger.debug("reading stdout...")
                    data = channel.recv(recv_len)

            if channel.recv_stderr_ready():
                logger.debug("reading stderr...")
                data = channel.recv_stderr(recv_len)
                while data:
                    logger.debug("read stderr: %d bytes", len(data))
                    stderr_io.write(data)
                    logger.debug("reading stderr...")
                    data = channel.recv_stderr(recv_len)

            if not pending_data:
                time.sleep(relax_duration)

        returncode = channel.recv_exit_status()
        stdout_out = stdout_io.getvalue()
        stderr_out = stderr_io.getvalue()
        logger.debug(
            "command exited with: %d (stdout=%d stderr=%d)",
            returncode,
            len(stdout_out),
            len(stderr_out),
        )
        channel.close()

        if check and returncode != 0:
            raise subprocess.CalledProcessError(
                returncode, cmd_string, stdout_out, stderr_out
            )

        if not capture_output:
            stdout_out = None
            stderr_out = None

        if text:
            assert isinstance(stderr_out, bytes)
            assert isinstance(stdout_out, bytes)
            stdout_out = stdout_out.decode(encoding="utf-8", errors="strict")
            stderr_out = stderr_out.decode(encoding="utf-8", errors="strict")

        return subprocess.CompletedProcess(cmd, returncode, stdout_out, stderr_out)

    def reboot(self) -> None:
        cmd = ["sudo", "shutdown", "-r", "1"]

        logger.debug("rebooting vm...")
        self.run(cmd, capture_output=True, check=True, text=True)
        logger.debug("rebooted vm, will start in 60s...")

    def wait_for_system_ready(self, *, attempts: int = 300, sleep: float = 1.0) -> str:
        try:
            cmd = ["cloud-init", "status", "--wait"]
            self.run(cmd, capture_output=True, check=False, text=True)
        except Exception:  # pylint: disable=broad-except
            pass

        try:
            cmd = ["systemctl", "is-system-running", "--wait"]
            self.run(cmd, capture_output=True, check=False, text=True)
        except Exception:  # pylint: disable=broad-except
            pass

        cmd = ["systemctl", "is-system-running"]

        logger.debug("waiting for system ready...")
        for _ in range(attempts):
            proc = self.run(cmd, capture_output=True, check=False, text=True)
            status = proc.stdout.strip()

            if status == "degraded":
                logger.warning("system ready, but degraded")
                return status

            if status == "running":
                logger.debug("system ready")
                return status

            logger.debug("system status: %s (rc=%d)", status, proc.returncode)
            time.sleep(sleep)

        logger.error("timed out waiting for system ready: %r", status)
        raise SystemReadyTimeout(status)
