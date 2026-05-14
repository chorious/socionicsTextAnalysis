from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi import Request, Response
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from .core import Kernel1Analyzer
from .llm import LLMClient, LLMConfig


app = FastAPI(title="Shiro Kernel1 MVP", version="0.1.0")
analyzer = Kernel1Analyzer()
STATIC_DIR = Path(__file__).resolve().parent / "static"


@app.middleware("http")
async def force_utf8_response(request: Request, call_next) -> Response:
    content_type = request.headers.get("content-type", "").lower()
    if request.method in {"POST", "PUT", "PATCH"} and "application/json" in content_type:
        if "charset=" in content_type and "charset=utf-8" not in content_type:
            return JSONResponse(
                status_code=415,
                content={"detail": "Only UTF-8 JSON requests are supported."},
                media_type="application/json; charset=utf-8",
            )

    response = await call_next(request)
    content_type = response.headers.get("content-type", "")
    if content_type.startswith(("application/json", "text/")) and "charset=" not in content_type:
        response.headers["content-type"] = f"{content_type}; charset=utf-8"
    return response


class AnalyzeRequest(BaseModel):
    text: str = Field(..., min_length=1)
    case_id: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)
    qa_items: list[dict[str, str]] | None = None
    llm_enabled: bool = False
    llm_base_url: str | None = None
    llm_model: str | None = None
    llm_api_key: str | None = None
    llm_timeout: int = 90
    llm_max_tokens: int = 4096


class ParseQARequest(BaseModel):
    text: str = Field(..., min_length=1)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/kernel1/parse-qa")
def parse_qa(request: ParseQARequest) -> dict[str, Any]:
    return analyzer.parse_qa(request.text)


@app.post("/kernel1/analyze")
def analyze(request: AnalyzeRequest) -> dict[str, Any]:
    options = request.options or {}
    llm_enabled = bool(options.get("llm_enabled", request.llm_enabled))
    if not llm_enabled:
        if request.qa_items:
            return analyzer.analyze_qa(qa_items=request.qa_items, case_id=request.case_id)
        return analyzer.analyze(text=request.text, case_id=request.case_id)

    defaults = LLMConfig()
    config = LLMConfig(
        enabled=True,
        base_url=str(options.get("llm_base_url") or request.llm_base_url or defaults.base_url),
        model=str(options.get("llm_model") or request.llm_model or defaults.model),
        api_key=str(options.get("llm_api_key") or request.llm_api_key or defaults.api_key),
        timeout=int(options.get("llm_timeout") or request.llm_timeout or defaults.timeout),
        max_tokens=int(options.get("llm_max_tokens") or request.llm_max_tokens or defaults.max_tokens),
    )
    request_analyzer = Kernel1Analyzer(llm=LLMClient(config))
    if request.qa_items:
        return request_analyzer.analyze_qa(qa_items=request.qa_items, case_id=request.case_id)
    return request_analyzer.analyze(text=request.text, case_id=request.case_id)
