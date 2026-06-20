from __future__ import annotations

import re
from typing import Any


EXTERNAL_URL_RE = re.compile(r"""(?:src|href)=["'](https?://[^"']+)["']""", re.IGNORECASE)
FONT_VW_RE = re.compile(r"font-size\s*:[^;{}]*vw", re.IGNORECASE)


def analyze_html_quality(html: str, template_id: str, allow_external_assets: bool = False) -> dict[str, Any]:
    lowered = html.lower()
    external_urls = sorted(set(EXTERNAL_URL_RE.findall(html)))
    checks = {
        "has_html_document": "<html" in lowered and "</html>" in lowered,
        "has_viewport_meta": "name=\"viewport\"" in lowered or "name='viewport'" in lowered,
        "has_inline_script": "<script" in lowered and "</script>" in lowered,
        "has_interactive_buttons": len(re.findall(r"<button\b", lowered)) >= 2,
        "has_form_control": bool(re.search(r"<(input|select|textarea)\b", lowered)),
        "has_operation_control": bool(re.search(r"<(input|select|textarea|button)\b", lowered)),
        "has_audio_controls": bool(re.search(r"<audio\b[^>]*\bcontrols\b", lowered)),
        "has_external_urls": bool(external_urls),
        "uses_font_vw": bool(FONT_VW_RE.search(html)),
        "uses_static_math_assets": "/static/assets/math/" in html,
        "uses_three": "/static/vendor/three.module.js" in html or "new three." in lowered,
        "has_hidden_project_panels": "display:none" in lowered or ".hidden" in lowered or "hidden" in lowered,
    }

    issues: list[str] = []
    if not checks["has_html_document"]:
        issues.append("缺少完整 <html> 文档结构。")
    if not checks["has_viewport_meta"]:
        issues.append("缺少 viewport meta，移动端布局不可控。")
    if not checks["has_inline_script"]:
        issues.append("缺少内联脚本，互动无法运行。")
    if not checks["has_interactive_buttons"]:
        issues.append("探究项目切换按钮不足，不能满足 2 到 4 个项目要求。")
    if not checks["has_operation_control"]:
        issues.append("缺少按钮、input、select 或 textarea 等操作控件。")
    if checks["has_audio_controls"]:
        issues.append("出现原生 audio controls，但当前 TTS 关闭。")
    if checks["has_external_urls"] and not allow_external_assets:
        issues.append("引用了外部网络资源，iframe 预览和离线投屏不稳定。")
    if checks["uses_font_vw"]:
        issues.append("font-size 使用 vw，容易造成投屏和移动端文字溢出。")
    if template_id != "solid_geometry_3d" and checks["uses_three"]:
        issues.append("非立体几何场景不应使用 Three.js。")
    if template_id == "solid_geometry_3d" and not checks["uses_three"]:
        issues.append("立体几何模板缺少本地 Three.js 引入。")

    severe = [
        issue
        for issue in issues
        if any(marker in issue for marker in ("缺少", "外部网络", "audio controls", "不应使用 Three.js"))
    ]
    return {
        "passed": not severe,
        "template_id": template_id,
        "allow_external_assets": allow_external_assets,
        "checks": checks,
        "issues": issues,
        "severe_issues": severe,
        "external_urls": external_urls,
    }


def apply_html_safety_patches(html: str) -> str:
    html = re.sub(r"<audio\b([^>]*)\bcontrols\b([^>]*)>", r"<audio\1\2>", html, flags=re.IGNORECASE)
    html = re.sub(r"font-size\s*:\s*clamp\([^;{}]+vw[^;{}]+\)\s*;", "font-size:28px;", html, flags=re.IGNORECASE)
    html = re.sub(r"font-size\s*:\s*[^;{}]*vw[^;{}]*;", "font-size:28px;", html, flags=re.IGNORECASE)
    return html
