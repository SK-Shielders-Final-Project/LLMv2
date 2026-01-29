from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.sandbox.manager import SandboxManager

app = FastAPI(title="Sandbox Executor")
manager = SandboxManager()


class SandboxRequest(BaseModel):
    code: str = Field(..., description="실행할 Python 코드")
    required_packages: list[str] = Field(default_factory=list)


@app.post("/run")
def run(request: SandboxRequest) -> dict:
    """
    요청마다 새 컨테이너를 생성하고 실행 후 즉시 제거한다.
    """
    result = manager.run_code(code=request.code, packages=request.required_packages)
    if result.get("exit_code") not in (0, None):
        raise HTTPException(status_code=400, detail=result.get("error", "Sandbox execution failed"))
    return result
