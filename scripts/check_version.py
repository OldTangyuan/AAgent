#!/usr/bin/env python3
"""校验版本号一致性。

权威清单是仓库根的 ``version.json``；每个服务目录下的 ``VERSION`` 是镜像内副本；
``CHANGELOG.md`` 的最新版本标题必须等于 ``platform``。

用法::

    python scripts/check_version.py

退出码：0 = 全部一致；1 = 有不一致（明细打到 stderr）。

规则见 ``docs/版本与归属规范.md`` §5。
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

SEMVER_RE = re.compile(r"^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?$")
PROTOCOL_RE = re.compile(r"^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)$")
# Keep a Changelog 的版本标题：## [0.1.0] - 2026-10-11（日期可选）
CHANGELOG_RE = re.compile(r"^##\s*\[(\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?)\]")


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
    if not isinstance(platform, str) or not SEMVER_RE.match(platform):
        errors.append(f"version.json.platform 不是合法 SemVer：{platform!r}")
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
            if not isinstance(value, str) or not SEMVER_RE.match(value):
                errors.append(f"version.json.services.{name} 不是合法 SemVer：{value!r}")

    return platform


def check_service_files(platform: str, services: dict, errors: list[str]) -> None:
    for name in SERVICES:
        expected = services.get(name, platform)
        path = REPO_ROOT / name / "VERSION"
        if not path.is_file():
            errors.append(f"缺少 {name}/VERSION（按 version.json 应为 {expected}）")
            continue
        actual = path.read_text(encoding="utf-8").strip()
        if actual != expected:
            errors.append(f"{name}/VERSION 与 version.json 不一致：文件 {actual!r} / 期望 {expected!r}")


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
            check_service_files(platform, services if isinstance(services, dict) else {}, errors)
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
        f" services={len(SERVICES)} 个（VERSION 与 CHANGELOG 均一致）"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
