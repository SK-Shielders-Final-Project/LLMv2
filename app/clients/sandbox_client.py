from __future__ import annotations

import json
import urllib.request
from typing import Any


class SandboxClient:
    """
    FastAPI 서버에서 원격 Sandbox 서버로 코드를 전달한다.
    Sandbox는 별도 서버에서 컨테이너를 생성/실행/삭제한다.
    """

    def __init__(self, base_url: str, timeout_seconds: int = 15) -> None:
        if not base_url:
            raise RuntimeError("SANDBOX_SERVER_URL이 설정되지 않았습니다.")
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def run_code(self, code: str, required_packages: list[str] | None = None) -> dict[str, Any]:
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
