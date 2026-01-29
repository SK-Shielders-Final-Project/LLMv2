from __future__ import annotations

import base64
import json
import os
import urllib.request
from typing import Any

import docker


class SandboxClient:
    """
    FastAPI 서버에서 원격 Sandbox 서버로 코드를 전달한다.
    Sandbox는 별도 서버에서 컨테이너를 생성/실행/삭제한다.
    """

    def __init__(self, base_url: str, timeout_seconds: int = 15) -> None:
        self.base_url = base_url.rstrip("/") if base_url else ""
        self.timeout_seconds = timeout_seconds
        self.exec_container = os.getenv("SANDBOX_EXEC_CONTAINER")
        self.exec_workdir = os.getenv("SANDBOX_EXEC_WORKDIR", "/")

    def run_code(self, code: str, required_packages: list[str] | None = None) -> dict[str, Any]:
        if self.exec_container:
            return self._run_via_exec(code=code, required_packages=required_packages or [])
        if not self.base_url:
            raise RuntimeError("SANDBOX_SERVER_URL 또는 SANDBOX_EXEC_CONTAINER가 필요합니다.")
        payload = {
            "code": code,
            "required_packages": required_packages or [],
        }
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url=f"{self.base_url}/run",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))

    def _run_via_exec(self, code: str, required_packages: list[str]) -> dict[str, Any]:
        client = docker.from_env()
        container = client.containers.get(self.exec_container)
        encoded = base64.b64encode(code.encode("utf-8")).decode("ascii")
        install_cmd = f"pip install {' '.join(required_packages)} && " if required_packages else ""
        command = (
            "bash -lc \""
            f"{install_cmd}python - <<'PY'\n"
            "import base64\n"
            f"exec(base64.b64decode('{encoded}').decode('utf-8'))\n"
            "PY\""
        )
        result = container.exec_run(command, workdir=self.exec_workdir)
        stdout = result.output.decode("utf-8", errors="replace") if hasattr(result, "output") else ""
        exit_code = getattr(result, "exit_code", 0)
        return {"exit_code": exit_code, "stdout": stdout}
