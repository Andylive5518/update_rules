#!/usr/bin/env python3

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

from config import (
    JSON_DIR,
    MOSDNS_RULES_DIR,
    SING_GEOSITE_API,
    SING_GEOSITE_URL,
    SINGBOX_RULES_DIR,
)
from utils import download_file, download_files_parallel, log, read_ip_lines


def get_sing_rules():
    log("INFO", "获取sing-geosite规则列表...")
    result = subprocess.run(
        [
            "curl",
            "-sSL",
            "--retry",
            "3",
            "--max-time",
            "30",
            "--retry-delay",
            "2",
            "-H",
            "Accept: application/vnd.github.v3+json",
            SING_GEOSITE_API,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        log("ERROR", "获取规则列表失败")
        return []

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        log("ERROR", "解析规则列表失败")
        return []

    all_files = [
        item["path"]
        for item in data.get("tree", [])
        if re.match(r"^geosite-.*\.srs$", item.get("path", ""))
    ]

    if not all_files:
        log("ERROR", "规则列表为空")
        return []

    main_rules = set()
    for rule in all_files:
        m = re.match(r"^geosite-([^-]+)(@cn|@!cn)\.srs$", rule)
        if m:
            main_rules.add(f"{m.group(1)}{m.group(2)}")

    filtered = []
    for rule in all_files:
        if not re.match(
            r"^geosite-(cn|geolocation-!cn|category.*!cn|.*@(cn|!cn))\.srs$", rule
        ):
            continue

        m = re.match(r"^geosite-([^@]+)(@cn|@!cn)\.srs$", rule)
        if m:
            rule_base = m.group(1)
            rule_suffix = m.group(2)
            dash_match = re.match(r"^([^-]+)-.*$", rule_base)
            if dash_match:
                main_rule_name = f"{dash_match.group(1)}{rule_suffix}"
                if main_rule_name in main_rules:
                    log(
                        "INFO",
                        f"跳过子集规则：{rule} (属于主规则：geosite-{main_rule_name}.srs)",
                    )
                    continue

        filtered.append(rule)

    filtered.sort(key=lambda r: (r.split("@")[0] if "@" in r else r, r))
    return filtered


def convert_rule(srs_file):
    json_file = os.path.splitext(srs_file)[0] + ".json"
    txt_file = os.path.splitext(srs_file)[0] + ".txt"

    srs_path = os.path.join(SINGBOX_RULES_DIR, srs_file)
    if not os.path.isfile(srs_path) or os.path.getsize(srs_path) == 0:
        log("ERROR", f"源文件不存在或为空：{srs_path}")
        return False

    tmp_dir = tempfile.mkdtemp()
    tmp_json = os.path.join(tmp_dir, json_file)

    try:
        result = subprocess.run(
            ["sing-box", "rule-set", "decompile", srs_path, "-o", tmp_json],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            log("ERROR", f"规则转换失败：{srs_file} -> {json_file}")
            return False

        try:
            with open(tmp_json, "r") as f:
                json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            log("ERROR", f"转换后的JSON文件无效：{json_file}")
            return False

        shutil.move(tmp_json, os.path.join(JSON_DIR, json_file))
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    json_path = os.path.join(JSON_DIR, json_file)
    with open(json_path, "r") as f:
        data = json.load(f)

    rule = data.get("rules", [{}])[0] if data.get("rules") else {}
    output_lines = []

    for field, prefix in [
        ("domain", "full:"),
        ("domain_suffix", "domain:"),
        ("domain_keyword", "keyword:"),
        ("domain_regex", "regexp:"),
    ]:
        val = rule.get(field)
        if val is None:
            continue
        if isinstance(val, str):
            val = [val]
        for item in val:
            if item:
                output_lines.append(f"{prefix}{item}")

    txt_path = os.path.join(MOSDNS_RULES_DIR, txt_file)
    if not output_lines:
        log("WARNING", f"提取的规则文件为空：{txt_file}")
        return False

    with open(txt_path, "w") as f:
        f.write("\n".join(output_lines) + "\n")

    log("INFO", f"规则转换完成：{txt_file} (共 {len(output_lines)} 条规则)")
    return True


def process_sing_rules():
    rules = get_sing_rules()
    count = 0
    total_rules = 0
    failed_rules = []

    targets = [r for r in rules if re.match(r"^geosite-(cn|.*@cn|.*!cn)\.srs$", r)]

    download_tasks = []
    for rule in targets:
        url = f"{SING_GEOSITE_URL}/{rule}"
        dest = os.path.join(SINGBOX_RULES_DIR, rule)
        log("INFO", f"下载sing-geosite规则：{os.path.basename(dest)} ({url})")
        download_tasks.append((url, dest, rule))

    dl_failed = download_files_parallel(
        [(url, dest) for url, dest, _ in download_tasks]
    )
    dl_failed_paths = {dest for _, dest in dl_failed}

    for url, dest, rule in download_tasks:
        if dest in dl_failed_paths:
            failed_rules.append(rule)
            continue

        if not os.path.isfile(dest) or os.path.getsize(dest) == 0:
            log("ERROR", f"下载的文件为空：{rule}")
            if os.path.exists(dest):
                os.unlink(dest)
            failed_rules.append(rule)
            continue

        txt_file = os.path.splitext(rule)[0] + ".txt"
        if convert_rule(rule):
            txt_path = os.path.join(MOSDNS_RULES_DIR, txt_file)
            if os.path.isfile(txt_path):
                with open(txt_path, "r") as f:
                    rule_count = sum(1 for line in f if line.strip())
                total_rules += rule_count
            count += 1
        else:
            failed_rules.append(rule)
            if os.path.exists(dest):
                os.unlink(dest)

    if failed_rules:
        log("WARNING", f"以下规则处理失败：{' '.join(failed_rules)}")

    if count > 0:
        log(
            "INFO",
            f"sing-geosite规则下载完成，共下载并转换 {count} 个规则文件，包含 {total_rules} 条规则",
        )
        return True
    return False


def merge_rules():
    types = ["@cn", "@!cn"]
    for rule_type in types:
        merged_json = os.path.join(JSON_DIR, f"geosite-all{rule_type}.json")
        merged_srs = os.path.join(SINGBOX_RULES_DIR, f"geosite-all{rule_type}.srs")

        if not _merge_rule_type(merged_json, merged_srs, rule_type):
            log("ERROR", f"合并 {rule_type} 类型规则失败")
            sys.exit(1)


def _merge_rule_type(merged_json, merged_srs, rule_type):
    log("INFO", f"开始合并 {rule_type} 类型规则")

    files = []
    for fname in os.listdir(JSON_DIR):
        fpath = os.path.join(JSON_DIR, fname)
        if not os.path.isfile(fpath):
            continue
        if fname == "geosite-cn.json" or fname == "geosite-geolocation-!cn.json":
            continue
        if fname == f"geosite-all{rule_type}.json":
            continue

        if rule_type == "@!cn":
            if fname.endswith("@!cn.json") or fname.endswith("!cn.json"):
                if re.match(r"^geosite-.*\.json$", fname):
                    files.append(fpath)
        else:
            if fname.endswith(f"{rule_type}.json"):
                if re.match(r"^geosite-.*\.json$", fname):
                    files.append(fpath)

    if not files:
        log("WARNING", f"未找到 {rule_type} 类型的规则文件")
        return False

    log("INFO", f"正在合并 {len(files)} 个规则文件")

    merged = {
        "domain": [],
        "domain_suffix": [],
        "domain_keyword": [],
        "domain_regex": [],
    }

    for fpath in sorted(files):
        try:
            with open(fpath, "r") as f:
                data = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            continue

        rule = data.get("rules", [{}])[0] if data.get("rules") else {}
        for field in ["domain", "domain_suffix", "domain_keyword", "domain_regex"]:
            val = rule.get(field)
            if val is None:
                continue
            if isinstance(val, str):
                val = [val]
            merged[field].extend([v for v in val if v])

    for field in list(merged.keys()):
        merged[field] = sorted(set(merged[field]))
        if not merged[field]:
            del merged[field]

    merged_count = sum(len(v) for v in merged.values())
    if merged_count == 0:
        log("ERROR", "合并后的规则文件为空")
        return False

    output = {"version": 1, "rules": [merged]}
    with open(merged_json, "w") as f:
        json.dump(output, f, ensure_ascii=False)

    log("INFO", f"合并后的规则数量：{merged_count}")

    log("INFO", f"正在编译规则集: {merged_json}")
    result = subprocess.run(
        ["sing-box", "rule-set", "compile", merged_json, "-o", merged_srs],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        log("ERROR", f"规则编译失败: {merged_srs}")
        return False

    log("INFO", f"正在转换规则格式: {merged_srs}")
    if not convert_rule(os.path.basename(merged_srs)):
        log("ERROR", f"规则转换失败: {os.path.splitext(merged_srs)[0]}.txt")
        return False

    return True


def run_geosite_update():
    process_sing_rules()
    merge_rules()
