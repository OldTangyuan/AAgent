#!/usr/bin/env python3
"""校验版本号一致性。

权威清单是仓库根的 ``version.json``；每个服务目录下的 ``version.json`` 是它的
服务级副本（``platform`` + ``protocol``，随镜像进容器）；``CHANGELOG.md`` 的最新版本标题必须等于 ``platform``。

用法::

    python scripts/check_version.py

退出码：0 = 全部一致；1 = 有不一致（明细打到 stderr）。

版本号语义（``MAJOR.MINOR.PATCH`` / ``MAJOR.MINOR``，非 SemVer）见 ``docs/版本控制.md``；
落地规则见 ``docs/版本与归属规范.md`` §5。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = REPO_ROOT / "version.json"
CHANGELOG_FILE = REPO_ROOT / "CHANGELOG.md"

SERVICES = (
    "agent",
    "webui_py",
    "manager_webui",
    "workflow_editor",
    "tool_server",
    "tool_provider",
    "qqbot",
    "qqbot_consumer",
)

PROTOCOL_KEYS = ("event", "workflow")

# 平台/服务版本：MAJOR.MINOR.PATCH（三段非负整数，无预发布、无 build metadata）
PLATFORM_RE = re.compile(r"^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)$")
# 协议版本：MAJOR.MINOR，只有两段
PROTOCOL_RE = re.compile(r"^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)$")
# Keep a Changelog 的版本标题：## [4.0.0] - 2026-10-11（日期可选）
CHANGELOG_RE = re.compile(r"^##\s*\[(\d+\.\d+\.\d+)\]")


def load_manifest(errors: list[str]) -> dict | None:
    if not VERSION_FILE.is_file():
        errors.append(f"缺少 {VERSION_FILE.relative_to(REPO_ROOT)}")
        return None
    try:
        return json.loads(VERSION_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"version.json 不是合法 JSON：{exc}")
        return None


def check_manifest(data: dict, errors: list[str]) -> str | None:
    platform = data.get("platform")
    if not isinstance(platform, str) or not PLATFORM_RE.match(platform):
        errors.append(f"version.json.platform 不是合法平台版本：{platform!r}")
        return None

    protocol = data.get("protocol")
    if not isinstance(protocol, dict) or set(protocol) != set(PROTOCOL_KEYS):
        errors.append("version.json.protocol 必须恰好包含 event 与 workflow 两个键")
    else:
        for name in PROTOCOL_KEYS:
            value = protocol[name]
            if not isinstance(value, str) or not PROTOCOL_RE.match(value):
                errors.append(f"version.json.protocol.{name} 不是合法 MAJOR.MINOR：{value!r}")

    services = data.get("services")
    if not isinstance(services, dict):
        errors.append("version.json.services 必须是对象（空对象表示全部服务跟随 platform）")
    else:
        for name in sorted(set(services) - set(SERVICES)):
            errors.append(f"version.json.services 含未登记服务：{name}")
        for name, value in sorted(services.items()):
            if not isinstance(value, str) or not PLATFORM_RE.match(value):
                errors.append(f"version.json.services.{name} 不是合法平台版本：{value!r}")

    return platform


def check_service_manifest(
    name: str, expected: str, platform: str, protocol: dict, errors: list[str]
) -> None:
    """校验服务目录下的 ``version.json``（根清单的服务级副本）。

    ``platform`` 必须等于根清单为该服务解析出的版本；与平台同步的服务，
    其 ``protocol`` 必须等于根协议（落后于平台的服务只校验格式）。
    """
    rel = f"{name}/version.json"
    path = REPO_ROOT / name / "version.json"
    if not path.is_file():
        errors.append(f"缺少 {rel}（按根 version.json 应为 {expected}）")
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"{rel} 不是合法 JSON：{exc}")
        return
    if set(data) != {"platform", "protocol"}:
        errors.append(f"{rel} 必须恰好包含 platform 与 protocol 两个键")
        return

    actual = data.get("platform")
    if not isinstance(actual, str) or not PLATFORM_RE.match(actual):
        errors.append(f"{rel}.platform 不是合法平台版本：{actual!r}")
    elif actual != expected:
        errors.append(f"{rel}.platform 与根 version.json 不一致：文件 {actual!r} / 期望 {expected!r}")

    service_protocol = data.get("protocol")
    if not isinstance(service_protocol, dict) or set(service_protocol) != set(PROTOCOL_KEYS):
        errors.append(f"{rel}.protocol 必须恰好包含 event 与 workflow 两个键")
        return
    for key in PROTOCOL_KEYS:
        value = service_protocol[key]
        if not isinstance(value, str) or not PROTOCOL_RE.match(value):
            errors.append(f"{rel}.protocol.{key} 不是合法 MAJOR.MINOR：{value!r}")
    if actual == platform and service_protocol != protocol:
        errors.append(f"{rel}.protocol 与根 version.json 不一致：{service_protocol!r} != {protocol!r}")


def check_service_manifests(
    platform: str, services: dict, protocol: dict, errors: list[str]
) -> None:
    for name in SERVICES:
        check_service_manifest(name, services.get(name, platform), platform, protocol, errors)


def check_changelog(platform: str, errors: list[str]) -> None:
    if not CHANGELOG_FILE.is_file():
        errors.append("缺少 CHANGELOG.md")
        return
    for line in CHANGELOG_FILE.read_text(encoding="utf-8").splitlines():
        match = CHANGELOG_RE.match(line.strip())
        if match:
            if match.group(1) != platform:
                errors.append(
                    f"CHANGELOG.md 最新版本 {match.group(1)} != version.json.platform {platform}"
                )
            return
    errors.append("CHANGELOG.md 未找到 '## [x.y.z]' 形式的版本标题")


def main() -> int:
    errors: list[str] = []
    data = load_manifest(errors)
    if data is not None:
        platform = check_manifest(data, errors)
        if platform is not None:
            services = data.get("services")
            protocol = data.get("protocol")
            check_service_manifests(
                platform,
                services if isinstance(services, dict) else {},
                protocol if isinstance(protocol, dict) else {},
                errors,
            )
            check_changelog(platform, errors)

    if errors:
        print("版本校验失败：", file=sys.stderr)
        for item in errors:
            print(f"  - {item}", file=sys.stderr)
        return 1

    protocol = data["protocol"]
    print(
        f"版本校验通过：platform={data['platform']}"
        f" protocol=event {protocol['event']} / workflow {protocol['workflow']}"
        f" services={len(SERVICES)} 个（version.json 与 CHANGELOG 均一致）"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
