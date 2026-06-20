from __future__ import annotations

import configparser
import os
from dataclasses import dataclass
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class ProviderSettings:
    name: str
    api_key: str
    base_url: str
    model: str
    auth_header: str
    auth_scheme: str
    api_key_hint: str

    @property
    def has_api_key(self) -> bool:
        return bool(self.api_key)


@dataclass(frozen=True)
class AppSettings:
    vision: ProviderSettings
    page: ProviderSettings
    script: ProviderSettings
    request_timeout_seconds: int
    mock_mode: bool
    max_vision_tokens: int
    max_page_tokens: int
    max_script_tokens: int
    tts_enabled: bool
    enable_html_repair: bool
    allow_external_assets: bool

    @property
    def has_required_keys(self) -> bool:
        return self.vision.has_api_key and self.page.has_api_key and self.script.has_api_key


def _read_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


def _sections(parser: configparser.ConfigParser) -> list[configparser.SectionProxy | dict[str, str]]:
    sections: list[configparser.SectionProxy | dict[str, str]] = []
    for section_name in ("models", "openai_compatible"):
        if parser.has_section(section_name):
            sections.append(parser[section_name])
    sections.append({})
    return sections


def _get_config_value(
    sections: list[configparser.SectionProxy | dict[str, str]],
    keys: tuple[str, ...],
) -> str:
    for section in sections:
        for key in keys:
            value = section.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
    return ""


def _pick(
    dotenv_values: dict[str, str],
    sections: list[configparser.SectionProxy | dict[str, str]],
    env_names: tuple[str, ...],
    config_keys: tuple[str, ...],
    default: str,
) -> str:
    for name in env_names:
        value = os.environ.get(name)
        if value is not None and value.strip():
            return value.strip()
    for name in env_names:
        value = dotenv_values.get(name)
        if value is not None and value.strip():
            return value.strip()
    value = _get_config_value(sections, config_keys)
    return value if value else default


def _pick_int(
    dotenv_values: dict[str, str],
    sections: list[configparser.SectionProxy | dict[str, str]],
    env_names: tuple[str, ...],
    config_keys: tuple[str, ...],
    default: int,
) -> int:
    raw = _pick(dotenv_values, sections, env_names, config_keys, str(default))
    try:
        return int(raw)
    except ValueError:
        return default


def _pick_bool(
    dotenv_values: dict[str, str],
    sections: list[configparser.SectionProxy | dict[str, str]],
    env_names: tuple[str, ...],
    config_keys: tuple[str, ...],
    default: bool,
) -> bool:
    raw = _pick(dotenv_values, sections, env_names, config_keys, "true" if default else "false")
    return raw.lower() in {"1", "true", "yes", "on"}


def _provider(
    *,
    name: str,
    api_key: str,
    base_url: str,
    model: str,
    auth_header: str,
    auth_scheme: str,
    api_key_hint: str,
) -> ProviderSettings:
    return ProviderSettings(
        name=name,
        api_key=api_key,
        base_url=base_url.rstrip("/"),
        model=model,
        auth_header=auth_header,
        auth_scheme=auth_scheme,
        api_key_hint=api_key_hint,
    )


def load_settings(config_path: Path | None = None, env_path: Path | None = None) -> AppSettings:
    config_file = config_path or ROOT_DIR / "config.ini"
    dotenv_values = _read_dotenv(env_path or ROOT_DIR / ".env")

    parser = configparser.ConfigParser()
    if config_file.exists():
        parser.read(config_file, encoding="utf-8")
    sections = _sections(parser)

    qwen_key = _pick(
        dotenv_values,
        sections,
        (
            "QWEN_API_KEY",
            "QWEN_ANSWER_API_KEY",
            "QWEN3_7_PLUS_API_KEY",
            "DASHSCOPE_API_KEY",
            "VISION_API_KEY",
        ),
        ("qwen_api_key", "vision_api_key"),
        "",
    )
    qwen_base_url = _pick(
        dotenv_values,
        sections,
        ("QWEN_BASE_URL", "QWEN_ANSWER_BASE_URL", "DASHSCOPE_BASE_URL", "VISION_BASE_URL"),
        ("qwen_base_url", "vision_base_url"),
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    qwen_model = _pick(
        dotenv_values,
        sections,
        ("QWEN_VISION_MODEL", "QWEN_ANSWER_MODEL", "QWEN_MODEL", "VISION_MODEL"),
        ("qwen_vision_model", "qwen_model", "vision_model"),
        "qwen3.5-omni-plus",
    )

    deepseek_key = _pick(
        dotenv_values,
        sections,
        ("DEEPSEEK_API_KEY", "DEEPSEEK_V4_API_KEY", "PAGE_API_KEY", "ANSWER_API_KEY", "ROUTER_API_KEY"),
        ("deepseek_api_key", "page_api_key"),
        "",
    )
    deepseek_base_url = _pick(
        dotenv_values,
        sections,
        ("DEEPSEEK_BASE_URL", "DEEPSEEK_V4_BASE_URL", "PAGE_BASE_URL", "ANSWER_BASE_URL", "ROUTER_BASE_URL"),
        ("deepseek_base_url", "page_base_url"),
        "https://api.deepseek.com/v1",
    )
    page_model = _pick(
        dotenv_values,
        sections,
        ("DEEPSEEK_MODEL", "DEEPSEEK_V4_MODEL", "PAGE_MODEL", "ANSWER_MODEL", "ROUTER_MODEL"),
        ("deepseek_model", "page_model"),
        "deepseek-v4-pro",
    )

    script_key = _pick(
        dotenv_values,
        sections,
        ("SCRIPT_API_KEY", "ANSWER_API_KEY", "ROUTER_API_KEY"),
        ("script_api_key",),
        deepseek_key,
    )
    script_base_url = _pick(
        dotenv_values,
        sections,
        ("SCRIPT_BASE_URL", "ANSWER_BASE_URL", "ROUTER_BASE_URL"),
        ("script_base_url",),
        deepseek_base_url,
    )
    script_model = _pick(
        dotenv_values,
        sections,
        ("SCRIPT_MODEL", "ANSWER_MODEL", "ROUTER_MODEL"),
        ("script_model",),
        page_model,
    )

    return AppSettings(
        vision=_provider(
            name="Qwen image understanding",
            api_key=qwen_key,
            base_url=qwen_base_url,
            model=qwen_model,
            auth_header=_pick(
                dotenv_values,
                sections,
                ("QWEN_AUTH_HEADER", "VISION_AUTH_HEADER"),
                ("qwen_auth_header", "vision_auth_header"),
                "Authorization",
            ),
            auth_scheme=_pick(
                dotenv_values,
                sections,
                ("QWEN_AUTH_SCHEME", "VISION_AUTH_SCHEME"),
                ("qwen_auth_scheme", "vision_auth_scheme"),
                "Bearer",
            ),
            api_key_hint="QWEN_API_KEY / DASHSCOPE_API_KEY",
        ),
        page=_provider(
            name="DeepSeek HTML generation",
            api_key=deepseek_key,
            base_url=deepseek_base_url,
            model=page_model,
            auth_header=_pick(
                dotenv_values,
                sections,
                ("DEEPSEEK_AUTH_HEADER", "PAGE_AUTH_HEADER"),
                ("deepseek_auth_header", "page_auth_header"),
                "Authorization",
            ),
            auth_scheme=_pick(
                dotenv_values,
                sections,
                ("DEEPSEEK_AUTH_SCHEME", "PAGE_AUTH_SCHEME"),
                ("deepseek_auth_scheme", "page_auth_scheme"),
                "Bearer",
            ),
            api_key_hint="DEEPSEEK_API_KEY",
        ),
        script=_provider(
            name="DeepSeek guide script",
            api_key=script_key,
            base_url=script_base_url,
            model=script_model,
            auth_header=_pick(
                dotenv_values,
                sections,
                ("SCRIPT_AUTH_HEADER", "DEEPSEEK_AUTH_HEADER"),
                ("script_auth_header", "deepseek_auth_header"),
                "Authorization",
            ),
            auth_scheme=_pick(
                dotenv_values,
                sections,
                ("SCRIPT_AUTH_SCHEME", "DEEPSEEK_AUTH_SCHEME"),
                ("script_auth_scheme", "deepseek_auth_scheme"),
                "Bearer",
            ),
            api_key_hint="SCRIPT_API_KEY / DEEPSEEK_API_KEY",
        ),
        request_timeout_seconds=_pick_int(
            dotenv_values,
            sections,
            ("REQUEST_TIMEOUT_SECONDS",),
            ("request_timeout_seconds",),
            180,
        ),
        mock_mode=_pick_bool(dotenv_values, sections, ("MOCK_MODE", "HACHI_MOCK_MODE"), ("mock_mode",), False),
        max_vision_tokens=_pick_int(dotenv_values, sections, ("MAX_VISION_TOKENS",), ("max_vision_tokens",), 1500),
        max_page_tokens=_pick_int(dotenv_values, sections, ("MAX_PAGE_TOKENS",), ("max_page_tokens",), 12000),
        max_script_tokens=_pick_int(dotenv_values, sections, ("MAX_SCRIPT_TOKENS",), ("max_script_tokens",), 1200),
        tts_enabled=False,
        enable_html_repair=_pick_bool(
            dotenv_values,
            sections,
            ("ENABLE_HTML_REPAIR",),
            ("enable_html_repair",),
            True,
        ),
        allow_external_assets=_pick_bool(
            dotenv_values,
            sections,
            ("ALLOW_EXTERNAL_ASSETS",),
            ("allow_external_assets",),
            True,
        ),
    )
