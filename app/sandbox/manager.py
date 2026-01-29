from __future__ import annotations

import base64
import os
import shlex
import uuid
from typing import Any

try:
    import paramiko
except Exception:  # pragma: no cover - 런타임 환경에서 확인
    paramiko = None

import docker


class SandboxManager:
    def __init__(self) -> None:
        self.client = docker.from_env()
        self.image = "python:3.10-slim"
        self.remote_host = os.getenv("SANDBOX_REMOTE_HOST")
        self.remote_port = int(os.getenv("SANDBOX_REMOTE_PORT", "22"))
        self.remote_user = os.getenv("SANDBOX_REMOTE_USER", "ec2-user")
        self.remote_key_path = os.getenv("SANDBOX_REMOTE_KEY_PATH")

    def run_code(self, code: str, packages: list[str] | None = None, timeout: int = 15) -> dict[str, Any]:
        if self.remote_host:
            return self._run_remote(code=code, packages=packages, timeout=timeout)

        return self._run_local(code=code, packages=packages, timeout=timeout)

    def _run_local(self, code: str, packages: list[str] | None = None, timeout: int = 15) -> dict[str, Any]:
        container_name = f"sandbox_{uuid.uuid4().hex}"
        packages = packages or []

        encoded = base64.b64encode(code.encode("utf-8")).decode("ascii")
        install_cmd = f"pip install {' '.join(packages)} && " if packages else ""
        full_command = (
            "sh -c \""
            f"{install_cmd}python - <<'PY'\n"
            "import base64\n"
            f"exec(base64.b64decode('{encoded}').decode('utf-8'))\n"
            "PY\""
        )

        container = None
        try:
            container = self.client.containers.run(
                image=self.image,
                command=full_command,
                name=container_name,
                network_mode="none",
                mem_limit="256m",
                nano_cpus=500_000_000,
                detach=True,
                remove=True,
            )
            result = container.wait(timeout=timeout)
            logs = container.logs().decode("utf-8", errors="replace")
            return {"exit_code": result.get("StatusCode"), "stdout": logs}
        except Exception as exc:
            return {"exit_code": 1, "error": str(exc)}
        finally:
            if container is not None:
                try:
                    container.remove(force=True)
                except Exception:
                    pass

    def _run_remote(self, code: str, packages: list[str] | None = None, timeout: int = 15) -> dict[str, Any]:
        if paramiko is None:
            return {"exit_code": 1, "error": "paramiko가 설치되지 않았습니다."}
        if not self.remote_key_path:
            return {"exit_code": 1, "error": "SANDBOX_REMOTE_KEY_PATH가 설정되지 않았습니다."}

        container_name = f"sandbox_{uuid.uuid4().hex}"
        packages = packages or []
        encoded = base64.b64encode(code.encode("utf-8")).decode("ascii")
        install_cmd = f"pip install {' '.join(packages)} && " if packages else ""
        python_block = (
            "python - <<'PY'\n"
            "import base64\n"
            f"exec(base64.b64decode('{encoded}').decode('utf-8'))\n"
            "PY"
        )
        shell_cmd = f"{install_cmd}{python_block}"
        docker_cmd = (
            "docker run --rm "
            f"--name {container_name} "
            "--network none --memory 256m --cpus 0.5 "
            f"{self.image} sh -c {shlex.quote(shell_cmd)}"
        )

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(
                hostname=self.remote_host,
                port=self.remote_port,
                username=self.remote_user,
                key_filename=self.remote_key_path,
                timeout=10,
            )
            stdin, stdout, stderr = client.exec_command(docker_cmd, timeout=timeout)
            exit_code = stdout.channel.recv_exit_status()
            out = stdout.read().decode("utf-8", errors="replace")
            err = stderr.read().decode("utf-8", errors="replace")
            if exit_code != 0:
                return {"exit_code": exit_code, "error": err or out}
            return {"exit_code": exit_code, "stdout": out, "stderr": err}
        except Exception as exc:
            try:
                client.exec_command(f"docker rm -f {container_name}")
            except Exception:
                pass
            return {"exit_code": 1, "error": str(exc)}
        finally:
            client.close()
