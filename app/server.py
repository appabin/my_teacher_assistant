from __future__ import annotations

import argparse
import json
import mimetypes
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from .config import ROOT_DIR, load_settings
from .llm_client import LLMAPIError
from .workflow import OUTPUT_DIR, TeachingWorkflow, UploadedImage, WorkflowError, make_job_id


STATIC_DIR = ROOT_DIR / "static"
MAX_BODY_BYTES = 80 * 1024 * 1024
JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()


def create_job(job_id: str) -> None:
    now = time.time()
    with JOBS_LOCK:
        JOBS[job_id] = {
            "job_id": job_id,
            "status": "queued",
            "step": "upload",
            "percent": 0,
            "message": "任务已创建，等待后台处理",
            "result": None,
            "error": None,
            "created_at": now,
            "updated_at": now,
        }


def update_job(job_id: str, **fields) -> None:
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if job is None:
            return
        job.update(fields)
        job["updated_at"] = time.time()


def read_job(job_id: str) -> dict | None:
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if job is None:
            return None
        snapshot = dict(job)

    snapshot["elapsed_seconds"] = round(time.time() - float(snapshot["created_at"]), 1)
    snapshot.pop("created_at", None)
    snapshot.pop("updated_at", None)
    return snapshot


def run_workflow_job(
    job_id: str,
    images: list[UploadedImage],
    focus: str,
    grade_level: str,
    dry_run: bool,
) -> None:
    def on_progress(update: dict) -> None:
        update_job(
            job_id,
            status="running",
            step=update.get("step", "upload"),
            percent=int(update.get("percent", 0)),
            message=str(update.get("message", "")),
        )

    try:
        settings = load_settings()
        workflow = TeachingWorkflow(settings)
        result = workflow.run(
            images=images,
            focus=focus,
            grade_level=grade_level,
            dry_run=dry_run,
            job_id=job_id,
            progress=on_progress,
        )
        update_job(
            job_id,
            status="done",
            step="done",
            percent=100,
            message="生成完成",
            result=result,
        )
    except (LLMAPIError, WorkflowError, ValueError) as exc:
        update_job(
            job_id,
            status="error",
            percent=100,
            message="处理失败",
            error=str(exc),
        )
    except Exception as exc:
        update_job(
            job_id,
            status="error",
            percent=100,
            message="服务器处理失败",
            error=str(exc),
        )


class TeachingAssistantHandler(BaseHTTPRequestHandler):
    server_version = "TeachingAssistant/0.1"

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            self._send_file(STATIC_DIR / "index.html")
            return
        if path == "/api/config-status":
            self._send_config_status()
            return
        if path.startswith("/api/workflows/"):
            self._send_workflow_status(path.removeprefix("/api/workflows/"))
            return
        if path.startswith("/static/"):
            self._send_safe_file(STATIC_DIR, path.removeprefix("/static/"))
            return
        if path.startswith("/outputs/"):
            self._send_safe_file(OUTPUT_DIR, path.removeprefix("/outputs/"))
            return
        self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path != "/api/workflows":
            self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
            return

        try:
            payload = self._read_json_body()
            images = [
                UploadedImage(name=str(item.get("name", "")), data_url=str(item.get("data_url", "")))
                for item in payload.get("images", [])
                if isinstance(item, dict)
            ]
            if not images:
                raise WorkflowError("请至少上传一张课本截图。")

            job_id = make_job_id()
            create_job(job_id)
            thread = threading.Thread(
                target=run_workflow_job,
                args=(
                    job_id,
                    images,
                    str(payload.get("focus", "")).strip(),
                    str(payload.get("grade_level", "")).strip(),
                    bool(payload.get("dry_run", False)),
                ),
                daemon=True,
            )
            thread.start()
            self._send_json(
                {
                    "job_id": job_id,
                    "status": "queued",
                    "step": "upload",
                    "percent": 0,
                    "message": "任务已创建",
                    "status_url": f"/api/workflows/{job_id}",
                },
                HTTPStatus.ACCEPTED,
            )
        except (WorkflowError, ValueError) as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self._send_json({"error": f"服务器处理失败: {exc}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            raise ValueError("请求体为空。")
        if length > MAX_BODY_BYTES:
            raise ValueError("请求体超过 80 MB，请减少截图数量或压缩图片。")
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("请求体不是合法 JSON。") from exc
        if not isinstance(payload, dict):
            raise ValueError("请求体必须是 JSON 对象。")
        return payload

    def _send_config_status(self) -> None:
        settings = load_settings()
        self._send_json(
            {
                "has_api_key": settings.has_required_keys,
                "mock_mode": settings.mock_mode,
                "vision_configured": settings.vision.has_api_key,
                "page_configured": settings.page.has_api_key,
                "script_configured": settings.script.has_api_key,
                "vision_base_url": settings.vision.base_url,
                "page_base_url": settings.page.base_url,
                "script_base_url": settings.script.base_url,
                "vision_model": settings.vision.model,
                "page_model": settings.page.model,
                "script_model": settings.script.model,
                "tts_enabled": settings.tts_enabled,
                "enable_html_repair": settings.enable_html_repair,
                "allow_external_assets": settings.allow_external_assets,
            }
        )

    def _send_workflow_status(self, job_id: str) -> None:
        snapshot = read_job(unquote(job_id))
        if snapshot is None:
            self._send_json({"error": "Job not found"}, HTTPStatus.NOT_FOUND)
            return
        self._send_json(snapshot)

    def _send_safe_file(self, root: Path, relative_path: str) -> None:
        root = root.resolve()
        target = (root / unquote(relative_path)).resolve()
        if not target.is_relative_to(root):
            self._send_json({"error": "Forbidden"}, HTTPStatus.FORBIDDEN)
            return
        self._send_file(target)

    def _send_file(self, path: Path) -> None:
        if not path.exists() or not path.is_file():
            self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
            return
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        content = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8" if content_type.startswith("text/") or content_type == "application/json" else content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _send_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format: str, *args) -> None:
        print(f"{self.address_string()} - {format % args}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local teaching assistant workflow server.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((args.host, args.port), TeachingAssistantHandler)
    print(f"Teaching assistant server running at http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
