from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import ROOT_DIR


TEMPLATE_DIR = ROOT_DIR / "templates" / "math"


@dataclass(frozen=True)
class TemplateSpec:
    template_id: str
    name: str
    file_name: str
    description: str
    keywords: tuple[str, ...]
    preferred_assets: tuple[str, ...]


MATH_ASSETS: tuple[dict[str, str], ...] = (
    {"id": "chicken", "path": "/static/assets/math/chicken.svg", "use": "鸡兔同笼、动物计数、替换法"},
    {"id": "rabbit", "path": "/static/assets/math/rabbit.svg", "use": "鸡兔同笼、动物计数、替换法"},
    {"id": "unit_cube", "path": "/static/assets/math/unit-cube.svg", "use": "个位、体积单位、搭积木"},
    {"id": "ten_rod", "path": "/static/assets/math/ten-rod.svg", "use": "十位、进位、退位、位值"},
    {"id": "hundred_flat", "path": "/static/assets/math/hundred-flat.svg", "use": "百位、面积模型、位值"},
    {"id": "fraction_circle", "path": "/static/assets/math/fraction-circle.svg", "use": "分数认识、等分、比较"},
    {"id": "fraction_bar", "path": "/static/assets/math/fraction-bar.svg", "use": "分数大小、同分母分数、等值分数"},
    {"id": "balance_scale", "path": "/static/assets/math/balance-scale.svg", "use": "等量关系、方程、两边平衡"},
    {"id": "number_line", "path": "/static/assets/math/number-line.svg", "use": "加减法、数轴跳跃、小数位置"},
    {"id": "grid_paper", "path": "/static/assets/math/grid-paper.svg", "use": "面积、周长、方格计数、坐标"},
    {"id": "geometry_solids", "path": "/static/assets/math/geometry-solids.svg", "use": "立体图形、三视图、体积表面积"},
    {"id": "clock_face", "path": "/static/assets/math/clock-face.svg", "use": "认识钟表、时间经过"},
    {"id": "yuan_coin", "path": "/static/assets/math/yuan-coin.svg", "use": "人民币、购物、找零、价格计算"},
    {"id": "yuan_note", "path": "/static/assets/math/yuan-note.svg", "use": "人民币、购物、找零、价格计算"},
    {"id": "shopping_basket", "path": "/static/assets/math/shopping-basket.svg", "use": "购物情境、合计、找零"},
    {"id": "ruler", "path": "/static/assets/math/ruler.svg", "use": "长度测量、厘米、米、毫米"},
    {"id": "measuring_tape", "path": "/static/assets/math/measuring-tape.svg", "use": "长度测量、估测、单位换算"},
    {"id": "kitchen_scale", "path": "/static/assets/math/kitchen-scale.svg", "use": "质量、千克、克、估测"},
    {"id": "bar_chart", "path": "/static/assets/math/bar-chart.svg", "use": "条形统计图、数据比较"},
    {"id": "line_chart", "path": "/static/assets/math/line-chart.svg", "use": "折线统计图、变化趋势"},
    {"id": "pictograph", "path": "/static/assets/math/pictograph.svg", "use": "象形统计图、一图代表几"},
    {"id": "protractor", "path": "/static/assets/math/protractor.svg", "use": "角、量角器、角度比较"},
    {"id": "wooden_stick", "path": "/static/assets/math/wooden-stick.svg", "use": "小木棍、计数、凑十、平均分、长度比较"},
    {"id": "child_student", "path": "/static/assets/math/child-student.svg", "use": "学生人数、排队、分组、座位、租船乘客"},
    {"id": "children_pair", "path": "/static/assets/math/children-pair.svg", "use": "两人一组、合作探究、人数比较、分组"},
    {"id": "boat_small", "path": "/static/assets/math/boat-small.svg", "use": "租船问题、小船载客、方案比较、余数处理"},
    {"id": "boat_large", "path": "/static/assets/math/boat-large.svg", "use": "租船问题、大船载客、最优方案、座位利用"},
    {"id": "oar", "path": "/static/assets/math/oar.svg", "use": "划船情境、行程、船只搭配、活动装饰"},
    {"id": "life_ring", "path": "/static/assets/math/life-ring.svg", "use": "水上安全、租船情境、提示标记、错误预警"},
    {"id": "seat", "path": "/static/assets/math/seat.svg", "use": "座位、空位、载客量、排座、平均分"},
    {"id": "bus", "path": "/static/assets/math/bus.svg", "use": "乘车、行程、座位、载客量、时间应用题"},
    {"id": "apple", "path": "/static/assets/math/apple.svg", "use": "计数、平均分、分数、购物、简单应用题"},
    {"id": "pencil", "path": "/static/assets/math/pencil.svg", "use": "学习用品、长度估测、计数、文具购物"},
    {"id": "book_stack", "path": "/static/assets/math/book-stack.svg", "use": "书本数量、分类计数、统计、比较"},
    {"id": "toy_blocks", "path": "/static/assets/math/toy-blocks.svg", "use": "搭积木、位值、体积、空间观察、组合计数"},
)


TEMPLATES: tuple[TemplateSpec, ...] = (
    TemplateSpec(
        template_id="application_reasoning",
        name="数量关系/应用题探究",
        file_name="application_reasoning.html",
        description="适合鸡兔同笼、行程、工程、倍数、等量关系、列表尝试、假设法和替换法。",
        keywords=("鸡兔", "头数", "脚数", "假设", "替换", "行程", "工程", "倍数", "方程", "数量关系", "列表"),
        preferred_assets=("chicken", "rabbit", "boat_small", "boat_large", "seat", "child_student", "balance_scale"),
    ),
    TemplateSpec(
        template_id="number_operations",
        name="数与运算/位值教具",
        file_name="number_operations.html",
        description="适合数的组成、加减乘除、进位退位、数轴、计数块、位值模型。",
        keywords=("加法", "减法", "乘法", "除法", "进位", "退位", "数位", "位值", "计数", "数轴", "小数", "口算"),
        preferred_assets=("wooden_stick", "unit_cube", "ten_rod", "hundred_flat", "number_line", "apple", "toy_blocks"),
    ),
    TemplateSpec(
        template_id="fractions",
        name="分数/等分模型",
        file_name="fractions.html",
        description="适合分数意义、等分、分数大小比较、同分母加减、等值分数。",
        keywords=("分数", "几分之几", "等分", "分母", "分子", "通分", "约分", "比较大小", "同分母"),
        preferred_assets=("fraction_circle", "fraction_bar", "number_line", "apple"),
    ),
    TemplateSpec(
        template_id="geometry_2d",
        name="平面图形/方格探究",
        file_name="geometry_2d.html",
        description="适合周长、面积、方格计数、平移旋转、三角形和四边形拼组。",
        keywords=("周长", "面积", "方格", "平面图形", "长方形", "正方形", "三角形", "平行四边形", "圆", "坐标", "平移", "旋转"),
        preferred_assets=("grid_paper", "fraction_bar"),
    ),
    TemplateSpec(
        template_id="solid_geometry_3d",
        name="立体图形/空间观察",
        file_name="solid_geometry_3d.html",
        description="适合长方体、正方体、圆柱、圆锥、体积、表面积、三视图和搭积木。",
        keywords=("立体", "长方体", "正方体", "圆柱", "圆锥", "体积", "表面积", "三视图", "从前面看", "从上面看", "搭积木"),
        preferred_assets=("unit_cube", "toy_blocks", "geometry_solids", "grid_paper"),
    ),
    TemplateSpec(
        template_id="time_money",
        name="时间与人民币情境",
        file_name="time_money.html",
        description="适合认识钟表、经过时间、购物合计、人民币换算、找零和价格应用题。",
        keywords=("时间", "钟表", "时针", "分针", "经过时间", "开始时间", "结束时间", "人民币", "元", "角", "分", "购物", "价格", "找零", "付出", "应付"),
        preferred_assets=("clock_face", "yuan_coin", "yuan_note", "shopping_basket", "bus", "number_line"),
    ),
    TemplateSpec(
        template_id="measurement_units",
        name="测量与单位换算",
        file_name="measurement_units.html",
        description="适合长度、质量、角度、厘米米毫米、千克克、单位进率和估测。",
        keywords=("长度", "厘米", "米", "毫米", "分米", "千米", "单位换算", "进率", "质量", "千克", "克", "吨", "估测", "角", "角度", "量角器"),
        preferred_assets=("ruler", "measuring_tape", "kitchen_scale", "protractor", "pencil", "number_line"),
    ),
    TemplateSpec(
        template_id="data_statistics",
        name="数据整理与统计图",
        file_name="data_statistics.html",
        description="适合数据收集、分类计数、条形统计图、象形统计图、折线统计图和比较问题。",
        keywords=("统计", "数据", "条形统计图", "象形统计图", "折线统计图", "分类", "调查", "最多", "最少", "合计", "平均数", "图形表示"),
        preferred_assets=("bar_chart", "line_chart", "pictograph", "children_pair", "book_stack", "grid_paper"),
    ),
)


def build_template_bundle(
    analysis: dict[str, Any],
    focus: str,
    grade_level: str,
    allow_external_assets: bool = False,
) -> dict[str, Any]:
    selected = select_template(analysis, focus)
    template_html = _read_template(selected)
    if allow_external_assets:
        asset_rule = (
            "可以引用稳定的 https 外部图片或素材库资源作为补充，但本地 /static/assets/math/ SVG 仍应优先用于核心教具；"
            "不要依赖外部脚本 CDN。"
        )
        network_rule = "页面可加载 https 图片素材；JS 仍应内联，本地 Three.js 仍使用 /static/vendor/three.module.js。"
    else:
        asset_rule = "优先引用 asset_library 中的 SVG 路径，不要依赖 emoji 或外网图片。"
        network_rule = "页面必须能在 iframe sandbox=allow-scripts 中运行，不要请求外部网络资源。"
    return {
        "selected_template": {
            "id": selected.template_id,
            "name": selected.name,
            "description": selected.description,
            "preferred_assets": list(selected.preferred_assets),
            "html_skeleton": template_html,
        },
        "available_templates": [
            {
                "id": template.template_id,
                "name": template.name,
                "description": template.description,
                "keywords": list(template.keywords),
            }
            for template in TEMPLATES
        ],
        "asset_library": list(MATH_ASSETS),
        "lesson_context": {
            "focus": focus,
            "grade_level": grade_level or analysis.get("grade_level") or "小学",
        },
        "external_assets": {
            "allowed": allow_external_assets,
            "policy": asset_rule,
        },
        "generation_rules": [
            "以 selected_template.html_skeleton 为结构基底，但必须根据截图内容重写具体变量、控件、反馈和探究项目。",
            asset_rule,
            "一次只展示一个探究项目；切换项目时展示区、控件和反馈同步切换。",
            "生成页不得展示原生 audio controls；当前 TTS 关闭，不要假设 guidance.wav 一定存在。",
            network_rule,
        ],
    }


def select_template(analysis: dict[str, Any], focus: str) -> TemplateSpec:
    explicit = str(analysis.get("template_id") or analysis.get("scene_type") or "").strip()
    for template in TEMPLATES:
        if explicit == template.template_id:
            return template

    haystack = _analysis_text(analysis, focus)
    best_template = TEMPLATES[1]
    best_score = -1
    for template in TEMPLATES:
        score = sum(3 if keyword in haystack else 0 for keyword in template.keywords)
        if template.template_id == "solid_geometry_3d" and any(word in haystack for word in ("立体", "体积", "表面积", "三视图")):
            score += 5
        if score > best_score:
            best_template = template
            best_score = score
    return best_template


def template_bundle_to_prompt(bundle: dict[str, Any]) -> str:
    return json.dumps(bundle, ensure_ascii=False, indent=2)


def _read_template(template: TemplateSpec) -> str:
    path = TEMPLATE_DIR / template.file_name
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8")
    return text[:18000]


def _analysis_text(analysis: dict[str, Any], focus: str) -> str:
    parts: list[str] = [focus]
    for key, value in analysis.items():
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, list):
            parts.extend(_flatten_list(value))
        elif isinstance(value, dict):
            parts.extend(str(item) for item in value.values())
    return " ".join(parts)


def _flatten_list(values: list[Any]) -> list[str]:
    output: list[str] = []
    for value in values:
        if isinstance(value, str):
            output.append(value)
        elif isinstance(value, dict):
            output.extend(str(item) for item in value.values())
        elif isinstance(value, list):
            output.extend(_flatten_list(value))
    return output
