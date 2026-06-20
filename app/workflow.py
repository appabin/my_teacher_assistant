from __future__ import annotations

import base64
import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .config import AppSettings, ROOT_DIR
from .html_quality import analyze_html_quality, apply_html_safety_patches
from .llm_client import LLMAPIError, OpenAICompatibleClient, message_text
from .prompts import analysis_messages, guide_script_messages, page_messages, page_repair_messages, vision_messages
from .template_library import TEMPLATE_DIR, TEMPLATES, build_template_bundle


OUTPUT_DIR = ROOT_DIR / "outputs"


class WorkflowError(RuntimeError):
    """Raised when the teaching workflow cannot complete."""


ProgressCallback = Callable[[dict[str, Any]], None]


@dataclass(frozen=True)
class UploadedImage:
    name: str
    data_url: str


def make_job_id() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]


def emit_progress(
    progress: ProgressCallback | None,
    step: str,
    percent: int,
    message: str,
) -> None:
    if progress is not None:
        progress({"step": step, "percent": percent, "message": message})


def parse_json_object(text: str) -> dict[str, Any]:
    cleaned = strip_code_fence(text)
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise WorkflowError(f"模型没有返回可解析 JSON: {text[:500]}")
        try:
            value = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError as exc:
            raise WorkflowError(f"模型返回 JSON 片段仍无法解析: {cleaned[start : end + 1][:500]}") from exc

    if not isinstance(value, dict):
        raise WorkflowError("模型返回 JSON 不是对象。")
    return value


def strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    return stripped.strip()


def clean_html(text: str) -> str:
    html = strip_code_fence(text)
    lowered = html.lower()
    html_start = lowered.find("<!doctype")
    if html_start == -1:
        html_start = lowered.find("<html")
    if html_start > 0:
        html = html[html_start:]
    if "<html" not in html.lower():
        html = (
            '<!doctype html>\n<html lang="zh-CN"><head><meta charset="utf-8">'
            "<title>互动课件</title></head><body>"
            f"{html}</body></html>"
        )
    return html


def data_url_to_bytes(data_url: str) -> tuple[str, bytes]:
    match = re.match(r"^data:([^;,]+);base64,(.+)$", data_url, re.DOTALL)
    if not match:
        raise WorkflowError("图片必须是 data:{MIME_TYPE};base64,... 格式。")
    mime_type = match.group(1).strip()
    try:
        return mime_type, base64.b64decode(match.group(2), validate=False)
    except ValueError as exc:
        raise WorkflowError("图片 base64 内容无法解码。") from exc


def image_extension(mime_type: str) -> str:
    return {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
        "image/webp": ".webp",
        "image/bmp": ".bmp",
    }.get(mime_type.lower(), ".img")


class TeachingWorkflow:
    def __init__(self, settings: AppSettings):
        self.settings = settings
        self.vision_client = OpenAICompatibleClient(settings.vision, settings.request_timeout_seconds)
        self.page_client = OpenAICompatibleClient(settings.page, settings.request_timeout_seconds)
        self.script_client = OpenAICompatibleClient(settings.script, settings.request_timeout_seconds)

    def run(
        self,
        images: list[UploadedImage],
        focus: str,
        grade_level: str,
        dry_run: bool = False,
        job_id: str | None = None,
        progress: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        if not images:
            raise WorkflowError("请至少上传一张课本截图。")

        job_id = job_id or make_job_id()
        job_dir = OUTPUT_DIR / job_id
        upload_dir = job_dir / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)

        emit_progress(progress, "upload", 5, "正在保存上传的课本截图")
        image_data_urls: list[str] = []
        for index, image in enumerate(images, start=1):
            mime_type, content = data_url_to_bytes(image.data_url)
            if len(content) > 50 * 1024 * 1024:
                raise WorkflowError(f"{image.name or f'第 {index} 张图片'} 超过 50 MB。")
            (upload_dir / f"{index:02d}{image_extension(mime_type)}").write_bytes(content)
            image_data_urls.append(image.data_url)
        emit_progress(progress, "upload", 10, f"已保存 {len(images)} 张截图")

        use_mock = dry_run or self.settings.mock_mode
        if not use_mock:
            self._ensure_required_keys()

        if use_mock:
            emit_progress(progress, "vision", 25, "模拟识别截图中的知识点")
            analysis = mock_analysis(focus, grade_level)
            emit_progress(progress, "template", 35, "选择模拟课件模板和素材")
            template_bundle = build_template_bundle(analysis, focus, grade_level, self.settings.allow_external_assets)
            emit_progress(progress, "page", 60, "模拟生成互动 H5 页面")
            html = mock_html(analysis)
            emit_progress(progress, "quality", 72, "检查模拟页面质量")
            html = apply_html_safety_patches(html)
            quality_report = analyze_html_quality(
                html,
                template_bundle["selected_template"]["id"],
                self.settings.allow_external_assets,
            )
            quality_report["repaired"] = False
            emit_progress(progress, "script", 82, "模拟生成课堂引导语")
            script = mock_script(analysis)
        else:
            emit_progress(progress, "vision", 18, f"正在调用 {self.settings.vision.model} 识别截图")
            analysis = self._analyze_images(image_data_urls, focus, grade_level)
            emit_progress(progress, "template", 36, "正在匹配小学数学模板和矢量素材")
            template_bundle = build_template_bundle(analysis, focus, grade_level, self.settings.allow_external_assets)
            selected = template_bundle["selected_template"]["name"]
            emit_progress(progress, "page", 52, f"已选择「{selected}」，正在调用 {self.settings.page.model} 生成互动网页")
            html = self._generate_page(analysis, focus, grade_level, template_bundle)
            emit_progress(progress, "quality", 72, "正在检查互动网页质量")
            html = apply_html_safety_patches(html)
            quality_report = analyze_html_quality(
                html,
                template_bundle["selected_template"]["id"],
                self.settings.allow_external_assets,
            )
            quality_report["repaired"] = False
            if self.settings.enable_html_repair and quality_report["severe_issues"]:
                emit_progress(progress, "quality", 76, "页面质量检查发现问题，正在调用模型修复一次")
                html = self._repair_page(html, quality_report, analysis, template_bundle)
                html = apply_html_safety_patches(html)
                quality_report = analyze_html_quality(
                    html,
                    template_bundle["selected_template"]["id"],
                    self.settings.allow_external_assets,
                )
                quality_report["repaired"] = True
            emit_progress(progress, "script", 84, f"互动网页完成，正在调用 {self.settings.script.model} 生成教师引导文案")
            script = self._generate_script(analysis, focus, grade_level)

        emit_progress(progress, "saving", 96, "正在保存课件、识别结果、模板上下文和引导文案")
        (job_dir / "analysis.json").write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")
        (job_dir / "template_context.json").write_text(json.dumps(template_bundle, ensure_ascii=False, indent=2), encoding="utf-8")
        (job_dir / "html_quality.json").write_text(json.dumps(quality_report, ensure_ascii=False, indent=2), encoding="utf-8")
        (job_dir / "index.html").write_text(html, encoding="utf-8")
        (job_dir / "guide_script.txt").write_text(script, encoding="utf-8")
        emit_progress(progress, "done", 100, "生成完成")

        return {
            "job_id": job_id,
            "analysis": analysis,
            "guide_script": script,
            "page_url": f"/outputs/{job_id}/index.html",
            "analysis_url": f"/outputs/{job_id}/analysis.json",
            "template_url": f"/outputs/{job_id}/template_context.json",
            "quality_url": f"/outputs/{job_id}/html_quality.json",
            "script_url": f"/outputs/{job_id}/guide_script.txt",
            "audio_url": None,
            "template": template_bundle["selected_template"],
            "quality": quality_report,
            "providers": {
                "vision_model": self.settings.vision.model,
                "page_model": self.settings.page.model,
                "script_model": self.settings.script.model,
                "tts_enabled": self.settings.tts_enabled,
                "allow_external_assets": self.settings.allow_external_assets,
            },
            "mock": use_mock,
        }

    def _ensure_required_keys(self) -> None:
        missing: list[str] = []
        if not self.settings.vision.has_api_key:
            missing.append(self.settings.vision.api_key_hint)
        if not self.settings.page.has_api_key:
            missing.append(self.settings.page.api_key_hint)
        if not self.settings.script.has_api_key:
            missing.append(self.settings.script.api_key_hint)
        if missing:
            unique_missing = sorted(set(missing))
            raise WorkflowError("缺少新模型 API Key，请在 .env 中配置：" + "、".join(unique_missing) + "；也可以先勾选模拟运行。")

    def _analyze_images(self, image_data_urls: list[str], focus: str, grade_level: str) -> dict[str, Any]:
        vision_payload: dict[str, Any] = {
            "model": self.settings.vision.model,
            "messages": vision_messages(image_data_urls, focus, grade_level),
            "max_tokens": min(self.settings.max_vision_tokens, 900),
            "stream": False,
        }
        if "omni" in self.settings.vision.model.lower():
            vision_payload.update(
                {
                    "modalities": ["text"],
                    "stream": True,
                    "stream_options": {"include_usage": True},
                }
            )

        vision_response = self.vision_client.chat(vision_payload)
        qwen_summary = message_text(vision_response)
        if not qwen_summary:
            raise WorkflowError("Qwen 没有返回可用的截图识别摘要。")

        analysis_response = self.page_client.chat(
            {
                "model": self.settings.page.model,
                "messages": analysis_messages(qwen_summary, focus, grade_level),
                "max_tokens": max(self.settings.max_vision_tokens, 1800),
                "temperature": 0.15,
                "top_p": 0.9,
                "stream": False,
            }
        )
        analysis = parse_json_object(message_text(analysis_response))
        analysis.setdefault("qwen_summary", qwen_summary)
        return analysis

    def _generate_page(
        self,
        analysis: dict[str, Any],
        focus: str,
        grade_level: str,
        template_bundle: dict[str, Any],
    ) -> str:
        response = self.page_client.chat(
            {
                "model": self.settings.page.model,
                "messages": page_messages(analysis, focus, grade_level, template_bundle),
                "max_tokens": self.settings.max_page_tokens,
                "temperature": 0.35,
                "top_p": 0.9,
                "stream": False,
            }
        )
        return clean_html(message_text(response))

    def _repair_page(
        self,
        html: str,
        quality_report: dict[str, Any],
        analysis: dict[str, Any],
        template_bundle: dict[str, Any],
    ) -> str:
        response = self.page_client.chat(
            {
                "model": self.settings.page.model,
                "messages": page_repair_messages(html, quality_report, analysis, template_bundle),
                "max_tokens": self.settings.max_page_tokens,
                "temperature": 0.2,
                "top_p": 0.9,
                "stream": False,
            }
        )
        return clean_html(message_text(response))

    def _generate_script(self, analysis: dict[str, Any], focus: str, grade_level: str) -> str:
        response = self.script_client.chat(
            {
                "model": self.settings.script.model,
                "messages": guide_script_messages(analysis, focus, grade_level),
                "max_tokens": self.settings.max_script_tokens,
                "temperature": 0.5,
                "top_p": 0.9,
                "stream": False,
            }
        )
        script = message_text(response)
        return strip_code_fence(script).strip()


def mock_analysis(focus: str, grade_level: str) -> dict[str, Any]:
    profile = _mock_profile(focus)
    topic = profile["lesson_title"]
    return {
        "lesson_title": topic,
        "subject": "数学",
        "grade_level": grade_level or "小学中高年级",
        "screenshot_summary": profile["summary"],
        "extracted_text": profile["extracted_text"],
        "key_concepts": profile["key_concepts"],
        "learning_goals": profile["learning_goals"],
        "problem_types": profile["problem_types"],
        "template_id": profile["template_id"],
        "scene_type": profile["scene_type"],
        "teaching_sequence": profile["teaching_sequence"],
        "interaction_ideas": profile["interaction_ideas"],
        "visual_assets": profile["visual_assets"],
        "data_defaults": profile["data_defaults"],
        "common_misconceptions": profile["common_misconceptions"],
        "quality_constraints": ["不要只给静态文字", "实时显示操作反馈", "一次只展示一个探究项目"],
    }


def mock_script(analysis: dict[str, Any]) -> str:
    title = analysis.get("lesson_title", "今天的知识")
    return (
        f"同学们，今天我们一起研究{title}。先看屏幕上的目标头数和脚数，"
        "再拖动滑块改变鸡和兔的数量。每改变一次，请观察头数和脚数发生了什么变化。"
        "如果头数对了但脚数少了，可以把一只鸡换成一只兔，脚数会多二。"
        "最后请把自己的答案代回去验证，说清楚理由。"
    )


def mock_html(analysis: dict[str, Any]) -> str:
    title = analysis.get("lesson_title", "互动课件")
    scene_text = " ".join(
        str(analysis.get(key, ""))
        for key in ("lesson_title", "scene_type", "screenshot_summary", "summary")
    )
    if any(word in scene_text for word in ("租船", "大船", "小船", "空位", "载客")):
        return mock_boat_html(analysis)
    template_id = str(analysis.get("template_id", "")).strip()
    for template in TEMPLATES:
        if template.template_id == template_id:
            path = TEMPLATE_DIR / template.file_name
            if path.exists():
                return path.read_text(encoding="utf-8").replace("{{LESSON_TITLE}}", str(title))
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    :root {{ color-scheme: light; --ink:#1d2733; --muted:#667085; --line:#d8dee8; --blue:#2563eb; --green:#0f8b6f; --amber:#b45309; --red:#c2410c; --panel:#ffffff; --bg:#f4f7fb; }}
    * {{ box-sizing: border-box; }}
    body {{ margin:0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", sans-serif; color:var(--ink); background:var(--bg); }}
    .shell {{ min-height:100vh; display:grid; grid-template-rows:auto 1fr; gap:12px; padding:14px; }}
    header {{ display:flex; align-items:center; justify-content:space-between; gap:12px; }}
    h1 {{ margin:0; font-size:28px; letter-spacing:0; }}
    .tabs {{ display:flex; gap:8px; flex-wrap:wrap; }}
    button {{ min-height:40px; border:1px solid var(--line); border-radius:8px; padding:0 14px; background:white; font-weight:700; cursor:pointer; }}
    button.active {{ color:white; background:var(--blue); border-color:var(--blue); }}
    main {{ display:grid; grid-template-columns:1fr 330px; gap:12px; }}
    .stage, aside {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:14px; }}
    .stage {{ min-height:520px; display:grid; grid-template-rows:auto 1fr auto; gap:12px; }}
    .scoreboard {{ display:grid; grid-template-columns:repeat(4, minmax(110px, 1fr)); gap:10px; }}
    .metric {{ border:1px solid var(--line); border-radius:8px; padding:12px; background:#fbfcff; }}
    .metric strong {{ display:block; font-size:30px; color:var(--blue); }}
    .animals {{ align-content:start; display:grid; grid-template-columns:repeat(auto-fill, minmax(76px, 1fr)); gap:10px; padding:14px; border:1px dashed #b8c2d6; border-radius:8px; background:#f8fafc; }}
    .animal {{ display:grid; place-items:center; min-height:72px; border-radius:8px; background:white; border:1px solid var(--line); }}
    .animal img {{ width:56px; height:56px; }}
    aside {{ display:grid; align-content:start; gap:14px; }}
    label {{ display:grid; gap:8px; color:var(--muted); font-size:14px; }}
    input {{ width:100%; }}
    .feedback {{ min-height:58px; padding:14px; border-radius:8px; font-size:18px; font-weight:700; border:1px solid var(--line); background:#fff; }}
    .ok {{ color:var(--green); border-color:#7dd3bc; background:#effaf6; }}
    .warn {{ color:var(--amber); border-color:#f1c27d; background:#fff8eb; }}
    .bad {{ color:var(--red); border-color:#ffb199; background:#fff3ef; }}
    @media (max-width: 860px) {{ main {{ grid-template-columns:1fr; }} .scoreboard {{ grid-template-columns:1fr 1fr; }} }}
  </style>
</head>
<body>
  <div class="shell">
    <header>
      <h1>{title}</h1>
      <nav class="tabs">
        <button class="active" data-view="model">建立模型</button>
        <button data-view="replace">替换观察</button>
        <button data-view="challenge">练习挑战</button>
      </nav>
    </header>
    <main>
      <section class="stage">
        <div class="scoreboard" id="scoreboard"></div>
        <div class="animals" id="animals"></div>
        <div class="feedback" id="feedback"></div>
      </section>
      <aside>
        <label>目标头数 <input id="targetHeads" type="range" min="0" max="30" value="8"></label>
        <label>目标脚数 <input id="targetLegs" type="range" min="0" max="80" value="26"></label>
        <label>鸡的只数 <input id="chickens" type="range" min="0" max="20" value="3"></label>
        <label>兔的只数 <input id="rabbits" type="range" min="0" max="20" value="5"></label>
        <button id="voiceBtn" type="button">语音暂未生成</button>
      </aside>
    </main>
  </div>
  <script>
    const ASSETS = {{
      chicken: "/static/assets/math/chicken.svg",
      rabbit: "/static/assets/math/rabbit.svg"
    }};
    const ids = ["chickens", "rabbits", "targetHeads", "targetLegs"];
    const el = Object.fromEntries(ids.map(id => [id, document.getElementById(id)]));
    const animals = document.getElementById("animals");
    function render() {{
      const c = Number(el.chickens.value);
      const r = Number(el.rabbits.value);
      const targetHeads = Number(el.targetHeads.value);
      const targetLegs = Number(el.targetLegs.value);
      const heads = c + r;
      const legs = c * 2 + r * 4;
      scoreboard.innerHTML = [
        ["鸡", c], ["兔", r], ["头", heads + " / " + targetHeads], ["脚", legs + " / " + targetLegs]
      ].map(([name, value]) => `<div class="metric">${{name}}<strong>${{value}}</strong></div>`).join("");
      animals.innerHTML = "";
      for (let i = 0; i < c; i++) animals.insertAdjacentHTML("beforeend", `<div class="animal"><img src="${{ASSETS.chicken}}" alt="鸡"></div>`);
      for (let i = 0; i < r; i++) animals.insertAdjacentHTML("beforeend", `<div class="animal"><img src="${{ASSETS.rabbit}}" alt="兔"></div>`);
      feedback.className = "feedback";
      if (heads === targetHeads && legs === targetLegs) {{
        feedback.classList.add("ok");
        feedback.textContent = "完全匹配。头数和脚数都能代回题目验证。";
      }} else if (heads === targetHeads) {{
        feedback.classList.add("warn");
        const diff = targetLegs - legs;
        feedback.textContent = diff > 0 ? `脚数少 ${{diff}}，把一只鸡换成一只兔会多 2 只脚。` : `脚数多 ${{Math.abs(diff)}}，把一只兔换成一只鸡会少 2 只脚。`;
      }} else {{
        feedback.classList.add("bad");
        feedback.textContent = `先调整总只数，目标头数和现在相差 ${{Math.abs(targetHeads - heads)}}。`;
      }}
    }}
    ids.forEach(id => el[id].addEventListener("input", render));
    document.querySelectorAll(".tabs button").forEach(button => button.addEventListener("click", () => {{
      document.querySelectorAll(".tabs button").forEach(item => item.classList.toggle("active", item === button));
      render();
    }}));
    voiceBtn.addEventListener("click", () => alert("当前 TTS 已关闭，只有文字引导稿。"));
    render();
  </script>
</body>
</html>"""


def mock_boat_html(analysis: dict[str, Any]) -> str:
    title = analysis.get("lesson_title", "租船方案")
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    :root {{ color-scheme: light; --ink:#172033; --muted:#667085; --line:#d7deea; --blue:#2563eb; --green:#0f766e; --amber:#b45309; --red:#c2410c; --bg:#f6f8fb; --panel:#fff; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; min-height:100vh; color:var(--ink); background:var(--bg); font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif; }}
    .shell {{ min-height:100vh; display:grid; grid-template-rows:auto 1fr; gap:12px; padding:14px; }}
    header {{ display:flex; align-items:center; justify-content:space-between; gap:12px; }}
    h1 {{ margin:0; font-size:28px; letter-spacing:0; }}
    .tabs {{ display:flex; gap:8px; flex-wrap:wrap; }}
    button {{ min-height:40px; border:1px solid var(--line); border-radius:8px; padding:0 14px; background:#fff; color:var(--ink); font-weight:700; cursor:pointer; }}
    button.active {{ color:#fff; background:var(--blue); border-color:var(--blue); }}
    main {{ display:grid; grid-template-columns:minmax(0,1fr) 330px; gap:12px; }}
    .stage, aside {{ border:1px solid var(--line); border-radius:8px; background:var(--panel); padding:14px; }}
    .stage {{ min-height:520px; display:grid; grid-template-rows:auto 1fr auto; gap:12px; }}
    .metrics {{ display:grid; grid-template-columns:repeat(4,minmax(110px,1fr)); gap:10px; }}
    .metric {{ border:1px solid var(--line); border-radius:8px; padding:10px; background:#fbfdff; }}
    .metric strong {{ display:block; margin-top:4px; color:var(--blue); font-size:28px; line-height:1; }}
    .harbor {{ min-height:300px; display:grid; grid-template-columns:repeat(auto-fill,minmax(110px,1fr)); align-content:start; gap:12px; padding:14px; border:1px dashed #b8c2d6; border-radius:8px; background:#f8fafc; }}
    .boat-card {{ min-height:116px; display:grid; place-items:center; gap:6px; border:1px solid var(--line); border-radius:8px; background:#fff; padding:8px; text-align:center; font-weight:700; }}
    .boat-card img {{ width:86px; height:62px; object-fit:contain; }}
    .seat-row {{ display:flex; justify-content:center; gap:3px; flex-wrap:wrap; }}
    .seat-dot {{ width:12px; height:12px; border-radius:999px; background:#22c55e; border:2px solid #1f2937; }}
    .seat-dot.empty {{ background:#fff; }}
    aside {{ display:grid; align-content:start; gap:14px; }}
    label {{ display:grid; gap:8px; color:var(--muted); font-size:14px; }}
    input {{ width:100%; }}
    .feedback {{ min-height:70px; border:1px solid var(--line); border-radius:8px; background:#f8fafc; padding:12px; font-size:18px; font-weight:700; line-height:1.5; }}
    .ok {{ color:var(--green); background:#ecfdf5; border-color:#99f6e4; }}
    .warn {{ color:var(--amber); background:#fffbeb; border-color:#fde68a; }}
    .bad {{ color:var(--red); background:#fff7ed; border-color:#fed7aa; }}
    @media (max-width:900px) {{ main {{ grid-template-columns:1fr; }} h1 {{ font-size:22px; }} .metrics {{ grid-template-columns:repeat(2,1fr); }} .stage {{ min-height:420px; }} }}
  </style>
</head>
<body>
  <div class="shell">
    <header>
      <h1>{title}</h1>
      <nav class="tabs" aria-label="探究项目">
        <button class="active" data-view="plan">搭配方案</button>
        <button data-view="empty">检查空位</button>
        <button data-view="cost">费用比较</button>
      </nav>
    </header>
    <main>
      <section class="stage">
        <div class="metrics" id="metrics"></div>
        <div class="harbor" id="harbor"></div>
        <div class="feedback" id="feedback"></div>
      </section>
      <aside>
        <label>学生人数 <input id="people" type="range" min="12" max="48" value="32"></label>
        <label>大船数量 <input id="largeBoats" type="range" min="0" max="8" value="5"></label>
        <label>小船数量 <input id="smallBoats" type="range" min="0" max="8" value="1"></label>
        <label>大船租金 <input id="largePrice" type="range" min="20" max="60" value="30"></label>
        <label>小船租金 <input id="smallPrice" type="range" min="12" max="50" value="24"></label>
        <button id="resetBtn" type="button">重置</button>
      </aside>
    </main>
  </div>
  <script>
    const ASSETS = {{
      child: "/static/assets/math/child-student.svg",
      smallBoat: "/static/assets/math/boat-small.svg",
      largeBoat: "/static/assets/math/boat-large.svg",
      seat: "/static/assets/math/seat.svg",
      ring: "/static/assets/math/life-ring.svg"
    }};
    const ids = ["people", "largeBoats", "smallBoats", "largePrice", "smallPrice"];
    const el = Object.fromEntries(ids.map(id => [id, document.getElementById(id)]));
    let view = "plan";

    function value(id) {{
      return Number(el[id].value);
    }}

    function seatsFor(index, size, usedBefore, people) {{
      const occupied = Math.max(0, Math.min(size, people - usedBefore));
      return Array.from({{ length: size }}, (_, i) => `<span class="seat-dot ${{i >= occupied ? "empty" : ""}}"></span>`).join("");
    }}

    function renderBoat(type, index, usedBefore, people) {{
      const isLarge = type === "large";
      const size = isLarge ? 6 : 4;
      const label = isLarge ? "大船 6 人" : "小船 4 人";
      const src = isLarge ? ASSETS.largeBoat : ASSETS.smallBoat;
      return `<div class="boat-card"><img src="${{src}}" alt="${{label}}"><span>${{label}}</span><div class="seat-row">${{seatsFor(index, size, usedBefore, people)}}</div></div>`;
    }}

    function render() {{
      const people = value("people");
      const large = value("largeBoats");
      const small = value("smallBoats");
      const largePrice = value("largePrice");
      const smallPrice = value("smallPrice");
      const capacity = large * 6 + small * 4;
      const emptySeats = Math.max(0, capacity - people);
      const shortage = Math.max(0, people - capacity);
      const cost = large * largePrice + small * smallPrice;
      const avgLarge = (largePrice / 6).toFixed(1);
      const avgSmall = (smallPrice / 4).toFixed(1);

      metrics.innerHTML = [
        ["人数", people],
        ["座位", capacity],
        ["空位", emptySeats],
        ["费用", cost + " 元"]
      ].map(([name, val]) => `<div class="metric">${{name}}<strong>${{val}}</strong></div>`).join("");

      harbor.innerHTML = "";
      let usedBefore = 0;
      for (let i = 0; i < large; i++) {{
        harbor.insertAdjacentHTML("beforeend", renderBoat("large", i, usedBefore, people));
        usedBefore += 6;
      }}
      for (let i = 0; i < small; i++) {{
        harbor.insertAdjacentHTML("beforeend", renderBoat("small", i, usedBefore, people));
        usedBefore += 4;
      }}
      if (!large && !small) {{
        harbor.innerHTML = `<div class="boat-card"><img src="${{ASSETS.ring}}" alt="提示"><span>先选择船只</span></div>`;
      }}

      feedback.className = "feedback";
      if (shortage > 0) {{
        feedback.classList.add("bad");
        feedback.textContent = `还少 ${{shortage}} 个座位，先保证所有学生都能上船。`;
      }} else if (view === "cost") {{
        feedback.classList.add(avgLarge <= avgSmall ? "ok" : "warn");
        feedback.textContent = `大船平均每人 ${{avgLarge}} 元，小船平均每人 ${{avgSmall}} 元。先多用单人更便宜的船，再检查空位。`;
      }} else if (emptySeats === 0) {{
        feedback.classList.add("ok");
        feedback.textContent = `刚好坐满，没有空位。算式：${{large}} x 6 + ${{small}} x 4 = ${{capacity}}。`;
      }} else {{
        feedback.classList.add("warn");
        feedback.textContent = `能坐下，但有 ${{emptySeats}} 个空位。试着减少一条船或调换大小船。`;
      }}
    }}

    ids.forEach(id => el[id].addEventListener("input", render));
    document.querySelectorAll(".tabs button").forEach(button => button.addEventListener("click", () => {{
      document.querySelectorAll(".tabs button").forEach(item => item.classList.toggle("active", item === button));
      view = button.dataset.view;
      render();
    }}));
    resetBtn.addEventListener("click", () => {{
      Object.assign(el.people, {{ value: 32 }});
      Object.assign(el.largeBoats, {{ value: 5 }});
      Object.assign(el.smallBoats, {{ value: 1 }});
      Object.assign(el.largePrice, {{ value: 30 }});
      Object.assign(el.smallPrice, {{ value: 24 }});
      render();
    }});
    render();
  </script>
</body>
</html>"""


def _mock_profile(focus: str) -> dict[str, Any]:
    text = focus or ""
    if any(word in text for word in ("租船", "大船", "小船", "空位", "载客", "最省钱")):
        return {
            "lesson_title": focus.strip() or "租船方案：怎样最省钱？",
            "template_id": "application_reasoning",
            "scene_type": "租船方案优化与空位检查",
            "summary": "模拟识别：教材内容围绕大船、小船载客量、租金和最省钱方案展开。",
            "extracted_text": ["学生人数", "大船可坐6人", "小船可坐4人", "大船租金", "小船租金", "怎样租船最省钱"],
            "key_concepts": ["单人费用比较", "有余数除法", "方案枚举", "空位检查", "总价计算"],
            "learning_goals": ["能比较大小船单人费用", "能列出可行租船方案", "能通过空位和总价判断最优方案"],
            "problem_types": ["租船最优方案", "列表尝试", "有余数应用题"],
            "teaching_sequence": ["先保证坐得下", "再比较单人费用", "调整空位", "计算总价验证"],
            "interaction_ideas": [{"name": "租船方案调节器", "purpose": "让学生通过调节大小船数量比较空位和费用", "inputs": ["人数", "大船数量", "小船数量", "租金"], "feedback": "实时显示座位、空位、总价和下一步建议"}],
            "visual_assets": ["大船", "小船", "小朋友", "座位", "救生圈"],
            "data_defaults": {"numbers": ["32", "6", "4", "30", "24"], "labels": ["人数", "大船", "小船", "空位", "总价"]},
            "common_misconceptions": ["只比较船数不比较总价", "忘记检查是否坐得下", "空位太多导致不是最省钱"],
        }
    if any(word in text for word in ("人民币", "购物", "找零", "价格", "钟表", "时间")):
        return {
            "lesson_title": focus.strip() or "时间与人民币",
            "template_id": "time_money",
            "scene_type": "购物找零/经过时间",
            "summary": "模拟识别：教材内容围绕时间推算、人民币合计或找零展开。",
            "extracted_text": ["开始时间", "经过时间", "商品价格", "应付", "找回"],
            "key_concepts": ["经过时间", "人民币计算", "加减法验证"],
            "learning_goals": ["能推算结束时间", "能计算购物合计和找零", "能用算式验证"],
            "problem_types": ["时间应用题", "人民币应用题"],
            "teaching_sequence": ["读清题意", "找出已知量", "操作模型", "列式验证"],
            "interaction_ideas": [{"name": "购物和时间调节器", "purpose": "让学生通过调节金额或时间观察结果", "inputs": ["价格", "付出金额", "经过分钟"], "feedback": "显示合计、找零或结束时间"}],
            "visual_assets": ["钟面", "人民币", "购物篮"],
            "data_defaults": {"numbers": ["8:00", "45", "12", "8", "30"], "labels": ["开始", "经过", "应付", "找回"]},
            "common_misconceptions": ["没有分清开始时间和结束时间", "找零时把减数写反", "元角分进率混淆"],
        }
    if any(word in text for word in ("统计", "条形", "象形", "折线", "数据", "最多", "最少")):
        return {
            "lesson_title": focus.strip() or "数据整理与统计",
            "template_id": "data_statistics",
            "scene_type": "统计图读数与比较",
            "summary": "模拟识别：教材内容围绕数据整理、统计图读数和比较问题展开。",
            "extracted_text": ["最多", "最少", "合计", "相差", "条形统计图"],
            "key_concepts": ["分类计数", "统计图", "数据比较"],
            "learning_goals": ["能读出统计图数据", "能比较最多和最少", "能提出数学问题"],
            "problem_types": ["统计图读数", "数据比较"],
            "teaching_sequence": ["读图例", "读数据", "比较数量", "提出问题"],
            "interaction_ideas": [{"name": "可调统计图", "purpose": "让学生观察数据变化如何影响最多、最少和合计", "inputs": ["各组数据"], "feedback": "实时显示合计和相差"}],
            "visual_assets": ["条形统计图", "象形统计图", "折线统计图"],
            "data_defaults": {"numbers": ["6", "9", "4", "7"], "labels": ["一组", "二组", "三组", "四组"]},
            "common_misconceptions": ["没有看清一个图形代表几", "把最多和合计混淆", "比较时只看颜色不看高度"],
        }
    if any(word in text for word in ("厘米", "米", "毫米", "单位", "换算", "千克", "克", "角度", "量角器", "测量")):
        return {
            "lesson_title": focus.strip() or "测量与单位换算",
            "template_id": "measurement_units",
            "scene_type": "测量和单位进率",
            "summary": "模拟识别：教材内容围绕长度、质量、角度和单位进率展开。",
            "extracted_text": ["1米=100厘米", "1千克=1000克", "角度", "估测"],
            "key_concepts": ["单位进率", "测量工具", "估测与换算"],
            "learning_goals": ["能说出相邻单位进率", "能用工具读数", "能完成简单换算"],
            "problem_types": ["单位换算", "测量读数"],
            "teaching_sequence": ["看单位", "找进率", "操作工具", "换算验证"],
            "interaction_ideas": [{"name": "单位换算尺", "purpose": "让学生通过调节数量观察单位变化", "inputs": ["厘米数", "千克数", "角度"], "feedback": "实时显示换算结果和判断"}],
            "visual_assets": ["直尺", "卷尺", "秤", "量角器"],
            "data_defaults": {"numbers": ["120", "3", "500", "60"], "labels": ["厘米", "米", "千克", "克"]},
            "common_misconceptions": ["进率记错", "单位没有统一", "量角器从错误刻度读数"],
        }
    if any(word in text for word in ("分数", "等分", "分母", "分子")):
        template_id = "fractions"
        scene_type = "分数等分"
    elif any(word in text for word in ("面积", "周长", "方格", "平移", "旋转")):
        template_id = "geometry_2d"
        scene_type = "平面图形"
    elif any(word in text for word in ("立体", "体积", "表面积", "三视图", "长方体", "正方体")):
        template_id = "solid_geometry_3d"
        scene_type = "空间观察"
    elif any(word in text for word in ("加法", "减法", "乘法", "除法", "进位", "退位", "位值", "数轴")):
        template_id = "number_operations"
        scene_type = "数与运算"
    else:
        template_id = "application_reasoning"
        scene_type = "鸡兔同笼/数量关系"
    return {
        "lesson_title": "鸡兔同笼" if "鸡兔" in text else (focus.strip() or "小学数学互动探究"),
        "template_id": template_id,
        "scene_type": scene_type,
        "summary": "模拟识别：课本内容围绕数量关系、列表尝试和用算式验证答案展开。",
        "extracted_text": ["头的总数", "脚的总数", "鸡有2只脚", "兔有4只脚"],
        "key_concepts": ["一一对应", "假设法", "方程思想", "列表验证"],
        "learning_goals": ["理解头数和脚数代表的数量关系", "通过调节数量观察总脚数变化", "能用算式验证答案"],
        "problem_types": ["鸡兔同笼应用题", "数量关系推理"],
        "teaching_sequence": ["先观察头数", "再改变鸡和兔的数量", "最后用总脚数验证"],
        "interaction_ideas": [{"name": "数量调节器", "purpose": "让学生直观看到数量变化如何影响结果", "inputs": ["数量", "目标"], "feedback": "实时显示是否匹配目标"}],
        "visual_assets": ["鸡图标", "兔图标", "头数/脚数计数器", "替换提示条"],
        "data_defaults": {"numbers": ["8", "26", "3", "5"], "labels": ["头", "脚", "鸡", "兔"]},
        "common_misconceptions": ["只看一个条件", "答案没有回代验证"],
    }
