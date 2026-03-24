#!/usr/bin/env python3

import json
import os
import shutil
import subprocess
import sys
import tempfile

from config import (
    BASE_URL,
    DOWNLOAD_IP_DIR,
    IPV4_FILES,
    IPV4_PATHS,
    IPV4_RESERVED,
    IPV6_FILES,
    IPV6_PATHS,
    IPV6_RESERVED,
    JSON_DIR,
    MOSDNS_RULES_DIR,
    ROS_IP_DIR,
    SING_GEOIP_FILES,
    SING_GEOIP_URLS,
    SINGBOX_RULES_DIR,
)
from ip_dedup import deduplicate_ip_list, merge_dedup_with_source
from utils import (
    check_required_commands,
    download_files_parallel,
    ensure_dir,
    log,
    read_ip_lines,
)


def init_env():
    log("INFO", "开始初始化环境...")
    for d in [
        DOWNLOAD_IP_DIR,
        ROS_IP_DIR,
        MOSDNS_RULES_DIR,
        SINGBOX_RULES_DIR,
        JSON_DIR,
    ]:
        if not os.path.isdir(d):
            log("INFO", f"创建目录: {d}")
            ensure_dir(d)

    check_required_commands(["curl", "jq", "sing-box"])
    log("INFO", "环境初始化完成")


def download_ip_lists():
    log("INFO", "开始下载IP地址列表...")

    tasks = []
    for i, fname in enumerate(IPV4_FILES):
        url = f"{BASE_URL}/{IPV4_PATHS[i]}"
        tasks.append((url, os.path.join(DOWNLOAD_IP_DIR, fname)))

    for i, fname in enumerate(IPV6_FILES):
        url = f"{BASE_URL}/{IPV6_PATHS[i]}"
        tasks.append((url, os.path.join(DOWNLOAD_IP_DIR, fname)))

    for i, url in enumerate(SING_GEOIP_URLS):
        tasks.append((url, os.path.join(SINGBOX_RULES_DIR, SING_GEOIP_FILES[i])))

    for url, _ in tasks:
        log("INFO", f"下载 {url}")

    failed = download_files_parallel(tasks)
    if failed:
        for url, _ in failed:
            log("ERROR", f"无法下载 {url}")
        sys.exit(1)

    log("INFO", "IP地址列表下载完成")


def _load_raw(filename, is_ipv6):
    filepath = os.path.join(DOWNLOAD_IP_DIR, filename)
    filter_flag = True if is_ipv6 else False
    return read_ip_lines(filepath, filter_ipv6=filter_flag)


def _load_all_ip_data():
    data = {}
    v4_keys = ["cn", "hk", "mo", "ctcc", "cucc", "cmcc"]
    v4_files = [
        "cn.txt",
        "hk.txt",
        "mo.txt",
        "ctcc.txt",
        "cucc.txt",
        "cmcc.txt",
    ]
    v6_keys = ["cn6", "hk6", "mo6", "ctcc6", "cucc6", "cmcc6"]
    v6_files = [
        "cn_ipv6.txt",
        "hk_ipv6.txt",
        "mo_ipv6.txt",
        "ctcc_ipv6.txt",
        "cucc_ipv6.txt",
        "cmcc_ipv6.txt",
    ]

    for key, fname in zip(v4_keys, v4_files):
        data[key] = _load_raw(fname, is_ipv6=False)
    for key, fname in zip(v6_keys, v6_files):
        data[key] = _load_raw(fname, is_ipv6=True)

    return data


def merge_ip_files(data):
    log("INFO", "开始合并IP文件...")

    regions = [
        ("cn", "cn6", "中国大陆"),
        ("hk", "hk6", "香港"),
        ("mo", "mo6", "澳门"),
    ]

    for v4_key, v6_key, name in regions:
        prefix = v4_key
        v4_dedup = deduplicate_ip_list(data[v4_key], is_ipv6=False)
        v6_dedup = deduplicate_ip_list(data[v6_key], is_ipv6=True)
        all_ips = v4_dedup + v6_dedup
        out_path = os.path.join(MOSDNS_RULES_DIR, f"{prefix}_all.txt")
        with open(out_path, "w") as f:
            f.write("\n".join(all_ips) + "\n")
        log(
            "INFO",
            f"{name}IP合并完成: IPv4: {len(v4_dedup)}, IPv6: {len(v6_dedup)} -> {out_path}",
        )

    log("INFO", "IP文件合并完成")


def convert_to_mikrotik(data):
    log("INFO", "开始转换为Mikrotik格式...")

    # ========== china_ipv4.rsc ==========
    log("INFO", "开始生成IPv4地址列表...")
    cn_merged = merge_dedup_with_source(
        [
            (data["cn"], ""),
            (data["hk"], "CN_HK_IP"),
            (data["mo"], "CN_MO_IP"),
        ],
        is_ipv6=False,
    )

    lines = [
        "/ip firewall address-list remove [find list=CN]",
        "/ip firewall address-list remove [find list=CTCC]",
        "/ip firewall address-list remove [find list=CUCC]",
        "/ip firewall address-list remove [find list=CMCC]",
        "/ip firewall address-list",
    ]

    for ip, comment in cn_merged:
        if comment:
            lines.append(f"add address={ip} list=CN disabled=no comment={comment}")
        else:
            lines.append(f"add address={ip} list=CN disabled=no")
    for ip in data["ctcc"]:
        lines.append(f"add address={ip} list=CTCC disabled=no")
    for ip in data["cucc"]:
        lines.append(f"add address={ip} list=CUCC disabled=no")
    for ip in data["cmcc"]:
        lines.append(f"add address={ip} list=CMCC disabled=no")

    rsc_path = os.path.join(ROS_IP_DIR, "china_ipv4.rsc")
    with open(rsc_path, "w") as f:
        f.write("\n".join(lines) + "\n")

    ipv4_count = sum(1 for l in lines if l.startswith("add address="))
    log("INFO", f"中国IPv4地址列表(含港澳)生成完成: {rsc_path}, 共 {ipv4_count} 条规则")

    # ========== china_ipv6.rsc ==========
    log("INFO", "开始生成IPv6地址列表...")
    cn6_merged = merge_dedup_with_source(
        [
            (data["cn6"], ""),
            (data["hk6"], "CN_HK_IPv6"),
            (data["mo6"], "CN_MO_IPv6"),
        ],
        is_ipv6=True,
    )

    lines = [
        "/ipv6 firewall address-list remove [find list=CN6]",
        "/ipv6 firewall address-list remove [find list=CTCC6]",
        "/ipv6 firewall address-list remove [find list=CUCC6]",
        "/ipv6 firewall address-list remove [find list=CMCC6]",
        "/ipv6 firewall address-list",
    ]

    for ip, comment in cn6_merged:
        if comment:
            lines.append(f"add address={ip} list=CN6 disabled=no comment={comment}")
        else:
            lines.append(f"add address={ip} list=CN6 disabled=no")
    for ip in data["ctcc6"]:
        lines.append(f"add address={ip} list=CTCC6 disabled=no")
    for ip in data["cucc6"]:
        lines.append(f"add address={ip} list=CUCC6 disabled=no")
    for ip in data["cmcc6"]:
        lines.append(f"add address={ip} list=CMCC6 disabled=no")

    rsc_path = os.path.join(ROS_IP_DIR, "china_ipv6.rsc")
    with open(rsc_path, "w") as f:
        f.write("\n".join(lines) + "\n")

    ipv6_count = sum(1 for l in lines if l.startswith("add address="))
    log("INFO", f"中国IPv6地址列表(含港澳)生成完成: {rsc_path}, 共 {ipv6_count} 条规则")

    # ========== nocn_ipv4.rsc ==========
    log("INFO", "开始生成NOCN IPv4地址列表...")
    nocn_merged = merge_dedup_with_source(
        [
            (IPV4_RESERVED, "NOCN_Reserved_IP"),
            (data["cn"], ""),
            (data["hk"], "NOCN_HK_IP"),
            (data["mo"], "NOCN_MO_IP"),
            (data["ctcc"], "NOCN_CTCC_IP"),
            (data["cucc"], "NOCN_CUCC_IP"),
            (data["cmcc"], "NOCN_CMCC_IP"),
        ],
        is_ipv6=False,
    )

    lines = [
        "/ip firewall address-list remove [find list=NOCN]",
        "/ip firewall address-list",
    ]
    for ip, comment in nocn_merged:
        if comment:
            lines.append(f"add address={ip} list=NOCN disabled=no comment={comment}")
        else:
            lines.append(f"add address={ip} list=NOCN disabled=no")

    rsc_path = os.path.join(ROS_IP_DIR, "nocn_ipv4.rsc")
    with open(rsc_path, "w") as f:
        f.write("\n".join(lines) + "\n")

    nocn_ipv4_count = sum(1 for l in lines if l.startswith("add address="))
    log("INFO", f"NOCN IPv4地址列表生成完成: {rsc_path}, 共 {nocn_ipv4_count} 条规则")

    # ========== nocn_ipv6.rsc ==========
    log("INFO", "开始生成NOCN IPv6地址列表...")
    nocn6_merged = merge_dedup_with_source(
        [
            (IPV6_RESERVED, "NOCN_Reserved_IP"),
            (data["cn6"], ""),
            (data["hk6"], "NOCN_HK_IPv6"),
            (data["mo6"], "NOCN_MO_IPv6"),
            (data["ctcc6"], "NOCN_CTCC_IPv6"),
            (data["cucc6"], "NOCN_CUCC_IPv6"),
            (data["cmcc6"], "NOCN_CMCC_IPv6"),
        ],
        is_ipv6=True,
    )

    lines = [
        "/ipv6 firewall address-list remove [find list=NOCN6]",
        "/ipv6 firewall address-list",
    ]
    for ip, comment in nocn6_merged:
        if comment:
            lines.append(f"add address={ip} list=NOCN6 disabled=no comment={comment}")
        else:
            lines.append(f"add address={ip} list=NOCN6 disabled=no")

    rsc_path = os.path.join(ROS_IP_DIR, "nocn_ipv6.rsc")
    with open(rsc_path, "w") as f:
        f.write("\n".join(lines) + "\n")

    nocn_ipv6_count = sum(1 for l in lines if l.startswith("add address="))
    log("INFO", f"NOCN IPv6地址列表生成完成: {rsc_path}, 共 {nocn_ipv6_count} 条规则")


def convert_to_singbox():
    log("INFO", "开始转换为sing-box格式...")

    regions = [
        ("cn_all", "中国大陆"),
        ("hk_all", "香港"),
        ("mo_all", "澳门"),
    ]

    for name, desc in regions:
        log("INFO", f"开始转换{desc}IP为sing-box格式...")
        txt_path = os.path.join(MOSDNS_RULES_DIR, f"{name}.txt")
        srs_path = os.path.join(SINGBOX_RULES_DIR, f"{name}.srs")

        raw_lines = read_ip_lines(txt_path)
        v4_lines = [l for l in raw_lines if ":" not in l]
        v6_lines = [l for l in raw_lines if ":" in l]
        v4_dedup = deduplicate_ip_list(v4_lines, is_ipv6=False)
        v6_dedup = deduplicate_ip_list(v6_lines, is_ipv6=True)
        ip_list = v4_dedup + v6_dedup

        rule_json = {"version": 1, "rules": [{"ip_cidr": ip_list}]}

        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".json")
        try:
            with os.fdopen(tmp_fd, "w") as f:
                json.dump(rule_json, f)
            log("INFO", f"{desc}IP JSON转换完成: 包含 {len(ip_list)} 条记录")
            log("INFO", f"编译{desc}IP规则集...")
            result = subprocess.run(
                ["sing-box", "rule-set", "compile", tmp_path, "-o", srs_path],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                log("INFO", f"{desc}IP规则集编译完成: {srs_path}")
            else:
                log("ERROR", f"编译{desc}IP规则集失败")
                json_path = os.path.join(JSON_DIR, f"{name}.json")
                shutil.copy2(tmp_path, json_path)
                sys.exit(1)
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    log("INFO", "sing-box格式转换完成")


def run_ip_update():
    init_env()
    download_ip_lists()
    data = _load_all_ip_data()
    merge_ip_files(data)
    convert_to_mikrotik(data)
    convert_to_singbox()
