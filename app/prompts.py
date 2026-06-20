from __future__ import annotations

import json
from typing import Any

from .template_library import template_bundle_to_prompt


SYSTEM_CN = (
    "你是小学数学互动课件设计与前端工程专家。"
    "你的输出必须服务于真实课堂投屏：结构清晰、操作具体、反馈即时、文字短句。"
)


def vision_messages(image_data_urls: list[str], focus: str, grade_level: str) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = []
    for data_url in image_data_urls:
        content.append({"type": "image_url", "image_url": {"url": data_url}})

    content.append(
        {
            "type": "text",
            "text": f"""
请阅读这些小学数学教材/练习截图，用中文提取信息。不要输出 JSON，不要 Markdown 表格。

重点：{focus or "从截图中提炼最适合做互动课件的知识点。"}
学段：{grade_level or "小学"}

请按短段落列出：
1. 题目原文或截图主要任务。
2. 所有关键数字、单位、公式、图形标注。
3. 教材已经给出的解题思路。
4. 这页适合做成什么互动教具。
5. 学生容易错在哪里。
""".strip(),
        }
    )

    return [{"role": "user", "content": content}]


def analysis_messages(qwen_summary: str, focus: str, grade_level: str) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "你是小学数学教材分析专家。"
                "请把截图识别摘要整理成后续生成互动 H5 所需的严格 JSON。"
                "只输出 JSON 对象，不要 Markdown，不要解释。"
            ),
        },
        {
            "role": "user",
            "content": f"""
用户重点关注：
{focus or "未指定"}

年级/学段：
{grade_level or "小学"}

Qwen 截图识别摘要：
{qwen_summary}

只输出一个 JSON 对象，字段如下：
{{
  "lesson_title": "适合投屏课堂展示的短标题",
  "subject": "数学",
  "grade_level": "根据截图和输入判断",
  "screenshot_summary": "截图内容摘要",
  "extracted_text": ["关键题目、数字、公式、图形标注"],
  "key_concepts": ["核心知识点"],
  "learning_goals": ["学生完成互动后应掌握什么"],
  "problem_types": ["题型或任务类型"],
  "template_id": "application_reasoning | number_operations | fractions | geometry_2d | solid_geometry_3d | time_money | measurement_units | data_statistics",
  "scene_type": "更细的教学场景",
  "teaching_sequence": ["建议课堂推进步骤，3 到 5 步"],
  "interaction_ideas": [
    {{
      "name": "互动名称",
      "purpose": "教学目的",
      "inputs": ["学生可操作的参数"],
      "feedback": "页面如何即时反馈"
    }}
  ],
  "visual_assets": ["页面中需要出现的教具、图形或表格"],
  "data_defaults": {{
    "numbers": ["题目中的关键数字或建议默认值"],
    "labels": ["需要显示的关键标签"]
  }},
  "common_misconceptions": ["容易错的地方"],
  "quality_constraints": ["生成 H5 时必须避免的问题"],
  "qwen_summary": "保留一段精简后的识图摘要"
}}

template_id 选择规则：
- 应用题、最优方案、租船、鸡兔同笼、行程、工程、倍数、方程、列表尝试：application_reasoning
- 数的组成、加减乘除、进位退位、位值、数轴、小数：number_operations
- 分数意义、等分、分数比较、同分母加减：fractions
- 周长、面积、方格、平面图形、平移旋转、坐标：geometry_2d
- 长方体、正方体、圆柱圆锥、体积表面积、三视图、搭积木：solid_geometry_3d
- 钟表、经过时间、人民币、购物、价格、找零：time_money
- 长度、质量、角、厘米米毫米、千克克、单位换算、估测：measurement_units
- 数据收集、分类、条形统计图、象形统计图、折线统计图、平均数：data_statistics
""".strip(),
        },
    ]


def page_messages(
    analysis: dict[str, Any],
    focus: str,
    grade_level: str,
    template_bundle: dict[str, Any],
) -> list[dict[str, str]]:
    analysis_text = json.dumps(analysis, ensure_ascii=False, indent=2)
    template_text = template_bundle_to_prompt(template_bundle)
    allow_external_assets = bool(template_bundle.get("external_assets", {}).get("allowed"))
    asset_rule = (
        "优先使用素材清单中的本地 SVG 路径；也可以补充使用稳定的 https 外部图片素材，但不要加载外部脚本 CDN。"
        if allow_external_assets
        else "优先使用素材清单中的 SVG 路径，例如 <img src=\"/static/assets/math/chicken.svg\" alt=\"鸡\">。不要依赖 emoji、外网图片或 CDN。"
    )
    network_rule = (
        "所有 JS 必须内联在页面中，能在 iframe sandbox=\"allow-scripts\" 内运行；可以加载 https 图片素材，但不要加载外部 JS。"
        if allow_external_assets
        else "所有 JS 必须内联在页面中，能在 iframe sandbox=\"allow-scripts\" 内运行；不要请求外部网络。"
    )
    return [
        {
            "role": "system",
            "content": (
                "你是资深小学数学互动课件前端工程师。"
                "你只输出完整 HTML 文档，不要 Markdown，不要解释。"
                "你擅长基于模板做具体化改造，而不是生成泛泛的表单页面。"
            ),
        },
        {
            "role": "user",
            "content": f"""
请根据截图识别分析、用户重点和模板素材，生成一个可直接投屏使用的互动课堂 H5。

用户重点关注：
{focus or "未指定"}

年级/学段：
{grade_level or analysis.get("grade_level") or "小学"}

截图识别 JSON：
{analysis_text}

模板与素材上下文：
{template_text}

硬性要求：
1. 只输出一个完整 HTML 文档，从 <!doctype html> 或 <html> 开始，不要输出代码围栏。
2. 以 selected_template.html_skeleton 为结构基底，但必须把题目、数字、交互项目、控件和反馈改成与截图知识点一致；不要照抄占位标题。
3. 必须设计 2 到 4 个探究项目，并用顶部按钮或分段控件切换；一次只展示一个项目，隐藏其他项目的说明、控件和对象。
4. 每个项目都要有真实互动：滑块、按钮、点击对象、拖动、选择、重置、即时算式反馈或可视化计算。不能只放文字说明。
5. {asset_rule}
6. 当前 TTS 关闭：不要展示 <audio controls>，不要假设 guidance.wav 存在。可以做一个隐藏的朗读按钮占位，但点击后只提示“语音暂未生成”。
7. 如果 template_id 是 application_reasoning 且场景是鸡兔同笼，必须包含鸡/兔对象、头数/脚数计数器、替换法或假设法动画、实时显示差多少和下一步建议。
8. 如果 template_id 是 number_operations，必须使用计数块、十根、百板或数轴表现数量变化，突出进位/退位/位值。
9. 如果 template_id 是 fractions，必须用分数条或圆形等分，并让分子/分母或比较对象可调。
10. 如果 template_id 是 geometry_2d，必须用方格或可变图形展示面积/周长/拼组变化。
11. 如果 template_id 是 time_money，必须有钟面、价格/付出/找零或经过时间的可调控件，并用清楚算式验证。
12. 如果 template_id 是 measurement_units，必须展示测量工具或单位进率，突出“先看进率，再换算/估测”。
13. 如果 template_id 是 data_statistics，必须有可调数据、统计图、最多/最少/合计/相差等即时反馈。
14. 如果 template_id 是 solid_geometry_3d，才使用 Three.js；必须通过 import("/static/vendor/three.module.js") 加载，canvas 默认非空白、模型完整可见，并提供加载失败提示。
15. 页面结构要克制：顶部标题和项目切换，中间大展示区，侧边或底部放当前项目控件和反馈。不要卡片套卡片。
16. 桌面和移动端都要可用；文字不要重叠，按钮文字不得溢出。font-size 不要用 vw 缩放。
17. {network_rule}
18. 输出质量目标：像一位优秀老师提前设计好的教具，而不是模型临时拼的页面。具体、可操作、投屏时一眼能看懂。
""".strip(),
        },
    ]


def guide_script_messages(analysis: dict[str, Any], focus: str, grade_level: str) -> list[dict[str, str]]:
    analysis_text = json.dumps(analysis, ensure_ascii=False, indent=2)
    return [
        {
            "role": "system",
            "content": "你是小学数学课堂引导老师。请只输出中文口语稿，不要标题，不要项目符号。",
        },
        {
            "role": "user",
            "content": f"""
请为这个互动课件写一段 120 到 180 字的课堂引导语。当前系统暂不生成 TTS 音频，这段文字会显示给老师参考。

年级/学段：{grade_level or analysis.get("grade_level") or "小学"}
重点关注：{focus or "未指定"}
识别分析：{analysis_text}

要求：
1. 直接面向学生说话。
2. 语气亲切、清楚，适合课堂开场和引导操作。
3. 引导学生观察、操作、说理由、验证答案。
4. 不要提到“截图识别”“模型生成”“DeepSeek”“Qwen”等后台流程。
""".strip(),
        },
    ]


def page_repair_messages(
    html: str,
    quality_report: dict[str, Any],
    analysis: dict[str, Any],
    template_bundle: dict[str, Any],
) -> list[dict[str, str]]:
    allow_external_assets = bool(template_bundle.get("external_assets", {}).get("allowed"))
    asset_repair_rule = (
        "可以保留稳定的 https 图片素材；不要引用外部脚本 CDN，Three.js 只能使用 /static/vendor/three.module.js。"
        if allow_external_assets
        else "不要引用外部网络资源，只能使用 /static/assets/math/ 和 /static/vendor/three.module.js。"
    )
    return [
        {
            "role": "system",
            "content": (
                "你是小学数学互动课件质量修复工程师。"
                "你只输出修复后的完整 HTML 文档，不要 Markdown，不要解释。"
            ),
        },
        {
            "role": "user",
            "content": f"""
下面的 HTML 是一个待修复的小学数学互动课件。请只修复质量报告指出的问题，同时保留原来的教学主题、交互结构和视觉风格。

截图识别 JSON：
{json.dumps(analysis, ensure_ascii=False, indent=2)}

模板上下文：
{template_bundle_to_prompt(template_bundle)}

质量报告：
{json.dumps(quality_report, ensure_ascii=False, indent=2)}

待修复 HTML：
{html}

修复要求：
1. 输出完整 HTML 文档。
2. {asset_repair_rule}
3. 当前 TTS 关闭，不要出现 <audio controls>。
4. 必须保留 2 到 4 个探究项目按钮，并确保一次只显示一个项目。
5. 必须保留至少一个真实操作控件和即时反馈。
6. font-size 不要使用 vw。
7. 非 solid_geometry_3d 不要使用 Three.js。
8. 不要输出解释。
""".strip(),
        },
    ]
