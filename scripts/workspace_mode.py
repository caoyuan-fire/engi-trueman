#!/usr/bin/env python3
"""Persist the Trueman switch in the workspace instructions Codex discovers."""

import argparse
import json
import os
from pathlib import Path
import re
import stat
import tempfile


BEGIN = b"<!-- engi-trueman:workspace -->"
END = b"<!-- /engi-trueman:workspace -->"
MODE = re.compile(rb"(?m)^mode: (on|off)\r?$")
SKILL = Path(__file__).resolve().parents[1] / "SKILL.md"


def instruction_file(workspace):
    override = workspace / "AGENTS.override.md"
    if override.is_file() and override.read_bytes().strip():
        return override
    return workspace / "AGENTS.md"


def managed_span(content):
    starts, ends = content.count(BEGIN), content.count(END)
    if not starts and not ends:
        return None
    if starts != 1 or ends != 1:
        raise ValueError("The Trueman block has incomplete or duplicate markers; file left unchanged.")
    start, end = content.index(BEGIN), content.index(END)
    if end < start:
        raise ValueError("The Trueman block markers are reversed; file left unchanged.")
    return start, end + len(END)


def current_mode(content, span):
    if span is None:
        return "off"
    matches = MODE.findall(content[span[0]:span[1]])
    if len(matches) != 1:
        raise ValueError("The Trueman block needs exactly one on/off state; file left unchanged.")
    return matches[0].decode("ascii")


def contract():
    text = SKILL.read_text(encoding="utf-8")
    start = "<!-- engi-trueman:contract -->"
    end = "<!-- /engi-trueman:contract -->"
    return text.split(start, 1)[1].split(end, 1)[0].strip()


def block(mode):
    header = """## Engi Trueman 工作区开关
mode: {mode}

每轮开始时重新读取这个指令文件中的 Engi Trueman 托管区块，以磁盘上的当前 mode 为准。不要用会话缓存代替回读。区块被移除或 mode 为 off 时，停止应用本技能的产出契约。用户当轮明确输入 `$engi-trueman on` 或 `$engi-trueman off` 时，先处理切换；引用、示例和技能修改需求中的命令不触发切换。
""".format(mode=mode)
    if mode == "on":
        body = "\n真人模式已开启。本工作区内一切工作、文档与答复都遵守以下产出契约。\n\n" + contract()
    else:
        body = "\n真人模式已关闭。解除 engi-trueman 的产出约束；自动匹配技能描述或阅读技能正文不能自行重新开启。只有用户明确开启后才恢复。"
    return BEGIN + b"\n" + (header + body).encode("utf-8") + b"\n" + END


def write_atomic(path, content):
    permissions = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o644
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".engi-trueman-", delete=False) as output:
            temporary = Path(output.name)
            output.write(content)
        temporary.chmod(permissions)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def switch(workspace, action):
    workspace = workspace.expanduser().resolve(strict=True)
    if not workspace.is_dir():
        raise ValueError("The workspace must be an existing directory.")
    path = instruction_file(workspace)
    if path.is_symlink():
        raise ValueError(f"{path} is a symlink; inspect its target before choosing a workspace-local instruction file.")
    content = path.read_bytes() if path.exists() else b""
    span = managed_span(content)
    mode = current_mode(content, span)
    changed = False
    if action != "status":
        replacement = block(action)
        if span is None:
            updated = replacement + (b"\n\n" + content if content else b"\n")
        else:
            updated = content[:span[0]] + replacement + content[span[1]:]
        changed = updated != content
        if changed:
            write_atomic(path, updated)
        mode = action
    return {"mode": mode, "configured": span is not None or action != "status", "instruction_file": str(path), "changed": changed}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("on", "off", "status"))
    parser.add_argument("--workspace", required=True, type=Path, help="Explicit workspace root, never inferred from the skill location")
    args = parser.parse_args()
    try:
        result = switch(args.workspace, args.action)
    except (OSError, ValueError) as error:
        parser.exit(1, f"{error}\n")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
