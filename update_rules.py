#!/usr/bin/env python3

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

# ============================================================
# 配置
# ============================================================

DOWNLOAD_IP_DIR = "./clang/ip"
ROS_IP_DIR = "./clang/ros"
MOSDNS_RULES_DIR = "./rules/mosdns"
SINGBOX_RULES_DIR = "./rules/sing-box"
JSON_DIR = "./rules/json"

BASE_URL = "https://ispip.clang.cn"
SING_GEOSITE_URL = "https://raw.githubusercontent.com/SagerNet/sing-geosite/rule-set"
SING_GEOSITE_API = (
    "https://api.github.com/repos/SagerNet/sing-geosite/git/trees/rule-set"
)

SING_GEOIP_URLS = [
    "https://raw.githubusercontent.com/SagerNet/sing-geoip/refs/heads/rule-set/geoip-cn.srs",
    "https://raw.githubusercontent.com/SagerNet/sing-geoip/refs/heads/rule-set/geoip-hk.srs",
    "https://raw.githubusercontent.com/SagerNet/sing-geoip/refs/heads/rule-set/geoip-mo.srs",
]
SING_GEOIP_FILES = [
    "geoip-cn.srs",
    "geoip-hk.srs",
    "geoip-mo.srs",
]

IPV4_FILES = [
    "cn.txt",
    "hk.txt",
    "mo.txt",
    "chinatelecom.txt",
    "unicom_cnc.txt",
    "cmcc.txt",
]
IPV4_PATHS = [
    "all_cn.txt",
    "hk.txt",
    "mo.txt",
    "chinatelecom.txt",
    "unicom_cnc.txt",
    "cmcc.txt",
]

IPV6_FILES = [
    "cn_ipv6.txt",
    "hk_ipv6.txt",
    "mo_ipv6.txt",
    "chinatelecom_ipv6.txt",
    "unicom_cnc_ipv6.txt",
    "cmcc_ipv6.txt",
]
IPV6_PATHS = [
    "all_cn_ipv6.txt",
    "hk_ipv6.txt",
    "mo_ipv6.txt",
    "chinatelecom_ipv6.txt",
    "unicom_cnc_ipv6.txt",
    "cmcc_ipv6.txt",
]

IPV4_RESERVED = [
    "10.0.0.0/8",
    "100.64.0.0/10",
    "127.0.0.0/8",
    "169.254.0.0/16",
    "172.16.0.0/12",
    "192.168.0.0/16",
    "198.18.0.0/15",
    "224.0.0.0/4",
    "240.0.0.0/4",
    "255.255.255.255/32",
]
IPV6_RESERVED = ["::1/128", "fc00::/7", "fe80::/10", "ff00::/8"]

# ============================================================
# 工具函数
# ============================================================


def log(level, message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level}] {message}")


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def download_file(url, output_path, retry=3):
    for attempt in range(1, retry + 1):
        try:
            result = subprocess.run(
                [
                    "curl",
                    "-fsSL",
                    "--retry",
                    "3",
                    "--max-time",
                    "30",
                    url,
                    "-o",
                    output_path,
                ],
                capture_output=True,
                text=True,
            )
            if (
                result.returncode == 0
                and os.path.isfile(output_path)
                and os.path.getsize(output_path) > 0
            ):
                return True
            if attempt < retry:
                log("WARNING", f"下载失败，重试 ({attempt}/{retry}): {url}")
        except Exception as e:
            if attempt < retry:
                log("WARNING", f"下载异常，重试 ({attempt}/{retry}): {e}")
    log("ERROR", f"下载失败: {url}")
    return False


def run_command(cmd, check=True):
    result = subprocess.run(
        cmd, shell=isinstance(cmd, str), capture_output=True, text=True
    )
    if check and result.returncode != 0:
        log("ERROR", f"命令执行失败: {cmd}")
        if result.stderr:
            log("ERROR", result.stderr.strip())
        sys.exit(1)
    return result


# ============================================================
# IP去重模块
# ============================================================
import ipaddress


def parse_cidr(cidr_str, is_ipv6=False):
    try:
        if is_ipv6:
            net = ipaddress.IPv6Network(cidr_str, strict=False)
            return int(net.network_address), net.prefixlen
        else:
            net = ipaddress.IPv4Network(cidr_str, strict=False)
            return int(net.network_address), net.prefixlen
    except (ipaddress.AddressValueError, ipaddress.NetmaskValueError) as e:
        return None, None


def is_subnet_contained(child_cidr, parent_cidr, is_ipv6=False):
    child_net, child_prefix = parse_cidr(child_cidr, is_ipv6)
    parent_net, parent_prefix = parse_cidr(parent_cidr, is_ipv6)

    if child_net is None or parent_net is None:
        return False
    if child_prefix is None or parent_prefix is None:
        return False
    if child_prefix < parent_prefix:
        return False

    if is_ipv6:
        mask = (1 << 128) - (1 << (128 - parent_prefix))
    else:
        mask = (1 << 32) - (1 << (32 - parent_prefix))

    return (child_net & mask) == parent_net


def deduplicate_ip_list(cidr_list, is_ipv6=False):
    valid_cidrs = []
    invalid_count = 0

    for cidr in cidr_list:
        cidr = cidr.strip()
        if not cidr or cidr.startswith("#"):
            continue
        net, prefix = parse_cidr(cidr, is_ipv6)
        if net is not None:
            valid_cidrs.append(cidr)
        else:
            invalid_count += 1

    if invalid_count > 0:
        log("WARNING", f"跳过 {invalid_count} 条无效CIDR")

    unique_cidrs = list(set(valid_cidrs))

    def get_prefix_key(cidr):
        _, prefix = parse_cidr(cidr, is_ipv6)
        return prefix if prefix is not None else (128 if is_ipv6 else 32)

    unique_cidrs.sort(key=get_prefix_key, reverse=True)

    result = []
    for cidr in unique_cidrs:
        is_contained = False
        for existing in result:
            if is_subnet_contained(cidr, existing, is_ipv6):
                is_contained = True
                break
        if not is_contained:
            result.append(cidr)

    def sort_key(cidr):
        net, _ = parse_cidr(cidr, is_ipv6)
        return net if net is not None else 0

    result.sort(key=sort_key)

    original_count = len(cidr_list)
    final_count = len(result)
    removed = original_count - final_count
    log("INFO", f"去重完成: {original_count} -> {final_count} (移除 {removed} 条)")
    return result


def deduplicate_file(filepath, is_ipv6=False):
    if not os.path.isfile(filepath) or os.path.getsize(filepath) == 0:
        return
    with open(filepath, "r") as f:
        lines = [
            line.strip()
            for line in f
            if line.strip() and not line.strip().startswith("#")
        ]
    result = deduplicate_ip_list(lines, is_ipv6)
    with open(filepath, "w") as f:
        f.write("\n".join(result) + "\n")


# ============================================================
# China IP模块
# ============================================================


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

    for cmd in ["curl", "jq", "sing-box"]:
        if not shutil.which(cmd):
            log("ERROR", f"未找到 {cmd} 命令")
            sys.exit(1)
        log("INFO", f"检查命令 {cmd}: 已安装")

    log("INFO", "环境初始化完成")


def download_ip_lists():
    log("INFO", "开始下载IP地址列表...")

    for i, fname in enumerate(IPV4_FILES):
        url = f"{BASE_URL}/{IPV4_PATHS[i]}"
        dest = os.path.join(DOWNLOAD_IP_DIR, fname)
        log("INFO", f"下载 {url}")
        if not download_file(url, dest):
            log("ERROR", f"无法下载 {url}")
            sys.exit(1)

    for i, fname in enumerate(IPV6_FILES):
        url = f"{BASE_URL}/{IPV6_PATHS[i]}"
        dest = os.path.join(DOWNLOAD_IP_DIR, fname)
        log("INFO", f"下载 {url}")
        if not download_file(url, dest):
            log("ERROR", f"无法下载 {url}")
            sys.exit(1)

    for i, url in enumerate(SING_GEOIP_URLS):
        dest = os.path.join(SINGBOX_RULES_DIR, SING_GEOIP_FILES[i])
        log("INFO", f"下载 {url}")
        if not download_file(url, dest):
            log("ERROR", f"无法下载 {url}")
            sys.exit(1)

    log("INFO", "IP地址列表下载完成")


def read_ip_lines(filepath, filter_ipv6=None):
    if not os.path.isfile(filepath):
        return []
    with open(filepath, "r") as f:
        lines = [line.strip() for line in f if line.strip()]
    if filter_ipv6 is True:
        lines = [l for l in lines if ":" in l]
    elif filter_ipv6 is False:
        lines = [l for l in lines if ":" not in l]
    return lines


def merge_ip_files():
    log("INFO", "开始合并IP文件...")

    regions = [("cn", "中国大陆"), ("hk", "香港"), ("mo", "澳门")]

    for prefix, name in regions:
        v4_file = os.path.join(DOWNLOAD_IP_DIR, f"{prefix}.txt")
        v6_file = os.path.join(DOWNLOAD_IP_DIR, f"{prefix}_ipv6.txt")

        v4 = read_ip_lines(v4_file, filter_ipv6=False)
        v6 = read_ip_lines(v6_file, filter_ipv6=True)

        v4_dedup = deduplicate_ip_list(v4, is_ipv6=False)
        v6_dedup = deduplicate_ip_list(v6, is_ipv6=True)

        all_ips = v4_dedup + v6_dedup

        out_path = os.path.join(MOSDNS_RULES_DIR, f"{prefix}_all.txt")
        with open(out_path, "w") as f:
            f.write("\n".join(all_ips) + "\n")

        log(
            "INFO",
            f"{name}IP合并完成: {prefix}.txt + {prefix}_ipv6.txt -> {out_path}, IPv4: {len(v4_dedup)}, IPv6: {len(v6_dedup)}",
        )

    log("INFO", "IP文件合并完成")


def convert_to_mikrotik():
    log("INFO", "开始转换为Mikrotik格式...")

    # 读取所有IPv4文件
    cn_ips = read_ip_lines(os.path.join(DOWNLOAD_IP_DIR, "cn.txt"), filter_ipv6=False)
    hk_ips = read_ip_lines(os.path.join(DOWNLOAD_IP_DIR, "hk.txt"), filter_ipv6=False)
    mo_ips = read_ip_lines(os.path.join(DOWNLOAD_IP_DIR, "mo.txt"), filter_ipv6=False)
    ctcc_ips = read_ip_lines(
        os.path.join(DOWNLOAD_IP_DIR, "chinatelecom.txt"), filter_ipv6=False
    )
    cucc_ips = read_ip_lines(
        os.path.join(DOWNLOAD_IP_DIR, "unicom_cnc.txt"), filter_ipv6=False
    )
    cmcc_ips = read_ip_lines(
        os.path.join(DOWNLOAD_IP_DIR, "cmcc.txt"), filter_ipv6=False
    )

    # 读取所有IPv6文件
    cn6_ips = read_ip_lines(
        os.path.join(DOWNLOAD_IP_DIR, "cn_ipv6.txt"), filter_ipv6=True
    )
    hk6_ips = read_ip_lines(
        os.path.join(DOWNLOAD_IP_DIR, "hk_ipv6.txt"), filter_ipv6=True
    )
    mo6_ips = read_ip_lines(
        os.path.join(DOWNLOAD_IP_DIR, "mo_ipv6.txt"), filter_ipv6=True
    )
    ctcc6_ips = read_ip_lines(
        os.path.join(DOWNLOAD_IP_DIR, "chinatelecom_ipv6.txt"), filter_ipv6=True
    )
    cucc6_ips = read_ip_lines(
        os.path.join(DOWNLOAD_IP_DIR, "unicom_cnc_ipv6.txt"), filter_ipv6=True
    )
    cmcc6_ips = read_ip_lines(
        os.path.join(DOWNLOAD_IP_DIR, "cmcc_ipv6.txt"), filter_ipv6=True
    )

    # 去重
    cn_ips_dedup = deduplicate_ip_list(cn_ips, is_ipv6=False)
    hk_ips_dedup = deduplicate_ip_list(hk_ips, is_ipv6=False)
    mo_ips_dedup = deduplicate_ip_list(mo_ips, is_ipv6=False)
    ctcc_ips_dedup = deduplicate_ip_list(ctcc_ips, is_ipv6=False)
    cucc_ips_dedup = deduplicate_ip_list(cucc_ips, is_ipv6=False)
    cmcc_ips_dedup = deduplicate_ip_list(cmcc_ips, is_ipv6=False)

    cn6_ips_dedup = deduplicate_ip_list(cn6_ips, is_ipv6=True)
    hk6_ips_dedup = deduplicate_ip_list(hk6_ips, is_ipv6=True)
    mo6_ips_dedup = deduplicate_ip_list(mo6_ips, is_ipv6=True)
    ctcc6_ips_dedup = deduplicate_ip_list(ctcc6_ips, is_ipv6=True)
    cucc6_ips_dedup = deduplicate_ip_list(cucc6_ips, is_ipv6=True)
    cmcc6_ips_dedup = deduplicate_ip_list(cmcc6_ips, is_ipv6=True)

    # 去重：HK、MO只添加不在CN中的IP
    cn_set = set(cn_ips_dedup)
    hk_set = set(hk_ips_dedup)
    mo_set = set(mo_ips_dedup)

    cn_list = cn_ips_dedup.copy()
    hk_list = [ip for ip in hk_ips_dedup if ip not in cn_set]
    mo_list = [ip for ip in mo_ips_dedup if ip not in cn_set and ip not in hk_set]

    # IPv6去重
    cn6_set = set(cn6_ips_dedup)
    hk6_set = set(hk6_ips_dedup)
    mo6_set = set(mo6_ips_dedup)

    cn6_list = cn6_ips_dedup.copy()
    hk6_list = [ip for ip in hk6_ips_dedup if ip not in cn6_set]
    mo6_list = [ip for ip in mo6_ips_dedup if ip not in cn6_set and ip not in hk6_set]

    # ========== china_ipv4.rsc ==========
    log("INFO", "开始生成IPv4地址列表...")
    lines = []
    lines.append("/ip firewall address-list remove [find list=CN]")
    lines.append("/ip firewall address-list remove [find list=CTCC]")
    lines.append("/ip firewall address-list remove [find list=CUCC]")
    lines.append("/ip firewall address-list remove [find list=CMCC]")
    lines.append("/ip firewall address-list")

    for ip in cn_list:
        lines.append(f"add address={ip} list=CN disabled=no")
    for ip in hk_list:
        lines.append(f"add address={ip} list=CN disabled=no comment=CN_HK_IP")
    for ip in mo_list:
        lines.append(f"add address={ip} list=CN disabled=no comment=CN_MO_IP")
    for ip in ctcc_ips_dedup:
        lines.append(f"add address={ip} list=CTCC disabled=no")
    for ip in cucc_ips_dedup:
        lines.append(f"add address={ip} list=CUCC disabled=no")
    for ip in cmcc_ips_dedup:
        lines.append(f"add address={ip} list=CMCC disabled=no")

    rsc_path = os.path.join(ROS_IP_DIR, "china_ipv4.rsc")
    with open(rsc_path, "w") as f:
        f.write("\n".join(lines) + "\n")

    ipv4_count = sum(1 for l in lines if l.startswith("add address="))
    log(
        "INFO",
        f"中国IPv4地址列表(含港澳)生成完成: $DOWNLOAD_IP_DIR/{{cn,hk,mo,chinatelecom,unicom_cnc,cmcc}}.txt -> {rsc_path}, 共 {ipv4_count} 条规则",
    )

    # ========== china_ipv6.rsc ==========
    log("INFO", "开始生成IPv6地址列表...")
    lines = []
    lines.append("/ipv6 firewall address-list remove [find list=CN6]")
    lines.append("/ipv6 firewall address-list remove [find list=CTCC6]")
    lines.append("/ipv6 firewall address-list remove [find list=CUCC6]")
    lines.append("/ipv6 firewall address-list remove [find list=CMCC6]")
    lines.append("/ipv6 firewall address-list")

    for ip in cn6_list:
        lines.append(f"add address={ip} list=CN6 disabled=no")
    for ip in hk6_list:
        lines.append(f"add address={ip} list=CN6 disabled=no comment=CN_HK_IPv6")
    for ip in mo6_list:
        lines.append(f"add address={ip} list=CN6 disabled=no comment=CN_MO_IPv6")
    for ip in ctcc6_ips_dedup:
        lines.append(f"add address={ip} list=CTCC6 disabled=no")
    for ip in cucc6_ips_dedup:
        lines.append(f"add address={ip} list=CUCC6 disabled=no")
    for ip in cmcc6_ips_dedup:
        lines.append(f"add address={ip} list=CMCC6 disabled=no")

    rsc_path = os.path.join(ROS_IP_DIR, "china_ipv6.rsc")
    with open(rsc_path, "w") as f:
        f.write("\n".join(lines) + "\n")

    ipv6_count = sum(1 for l in lines if l.startswith("add address="))
    log(
        "INFO",
        f"中国IPv6地址列表(含港澳)生成完成: $DOWNLOAD_IP_DIR/{{cn,hk,mo,chinatelecom,unicom_cnc,cmcc}}_ipv6.txt -> {rsc_path}, 共 {ipv6_count} 条规则",
    )

    # ========== nocn_ipv4.rsc ==========
    log("INFO", "开始生成NOCN IPv4地址列表...")
    lines = []
    lines.append("/ip firewall address-list remove [find list=NOCN]")
    lines.append("/ip firewall address-list")

    # 添加保留地址
    for reserved in IPV4_RESERVED:
        lines.append(
            f"add address={reserved} list=NOCN disabled=no comment=NOCN_Reserved_IP"
        )

    # 添加cn+hk+mo+chinatelecom+unicom_cnc+cmcc
    for ip in cn_list:
        lines.append(f"add address={ip} list=NOCN disabled=no")
    for ip in hk_list:
        lines.append(f"add address={ip} list=NOCN disabled=no comment=NOCN_HK_IP")
    for ip in mo_list:
        lines.append(f"add address={ip} list=NOCN disabled=no comment=NOCN_MO_IP")
    for ip in ctcc_ips_dedup:
        lines.append(f"add address={ip} list=NOCN disabled=no")
    for ip in cucc_ips_dedup:
        lines.append(f"add address={ip} list=NOCN disabled=no")
    for ip in cmcc_ips_dedup:
        lines.append(f"add address={ip} list=NOCN disabled=no")

    rsc_path = os.path.join(ROS_IP_DIR, "nocn_ipv4.rsc")
    with open(rsc_path, "w") as f:
        f.write("\n".join(lines) + "\n")

    nocn_ipv4_count = sum(1 for l in lines if l.startswith("add address="))
    log(
        "INFO",
        f"NOCN IPv4地址列表生成完成: $DOWNLOAD_IP_DIR/{{cn,hk,mo,chinatelecom,unicom_cnc,cmcc}}.txt -> {rsc_path}, 共 {nocn_ipv4_count} 条规则",
    )

    # ========== nocn_ipv6.rsc ==========
    log("INFO", "开始生成NOCN IPv6地址列表...")
    lines = []
    lines.append("/ipv6 firewall address-list remove [find list=NOCN6]")
    lines.append("/ipv6 firewall address-list")

    # 添加IPv6保留地址
    for reserved in IPV6_RESERVED:
        lines.append(
            f"add address={reserved} list=NOCN6 disabled=no comment=NOCN_Reserved_IP"
        )

    # 添加cn+hk+mo+chinatelecom+unicom_cnc+cmcc
    for ip in cn6_list:
        lines.append(f"add address={ip} list=NOCN6 disabled=no")
    for ip in hk6_list:
        lines.append(f"add address={ip} list=NOCN6 disabled=no comment=NOCN_HK_IPv6")
    for ip in mo6_list:
        lines.append(f"add address={ip} list=NOCN6 disabled=no comment=NOCN_MO_IPv6")
    for ip in ctcc6_ips_dedup:
        lines.append(f"add address={ip} list=NOCN6 disabled=no")
    for ip in cucc6_ips_dedup:
        lines.append(f"add address={ip} list=NOCN6 disabled=no")
    for ip in cmcc6_ips_dedup:
        lines.append(f"add address={ip} list=NOCN6 disabled=no")

    rsc_path = os.path.join(ROS_IP_DIR, "nocn_ipv6.rsc")
    with open(rsc_path, "w") as f:
        f.write("\n".join(lines) + "\n")

    nocn_ipv6_count = sum(1 for l in lines if l.startswith("add address="))
    log(
        "INFO",
        f"NOCN IPv6地址列表生成完成: $DOWNLOAD_IP_DIR/{{cn,hk,mo,chinatelecom,unicom_cnc,cmcc}}_ipv6.txt -> {rsc_path}, 共 {nocn_ipv6_count} 条规则",
    )


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
        json_path = os.path.join(JSON_DIR, f"{name}.json")

        ip_list = read_ip_lines(txt_path)
        rule_json = {"version": 1, "rules": [{"ip_cidr": ip_list}]}

        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".json")
        try:
            with os.fdopen(tmp_fd, "w") as f:
                json.dump(rule_json, f)
            log(
                "INFO",
                f"{desc}IP JSON转换完成: {txt_path} -> 临时文件, 包含 {len(ip_list)} 条记录",
            )
            log("INFO", f"编译{desc}IP规则集...")
            result = subprocess.run(
                ["sing-box", "rule-set", "compile", tmp_path, "-o", srs_path],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                log("INFO", f"{desc}IP规则集编译完成: 临时文件 -> {srs_path}")
            else:
                log("ERROR", f"编译{desc}IP规则集失败")
                shutil.copy2(tmp_path, json_path)
                sys.exit(1)
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    log("INFO", "sing-box格式转换完成")


# ============================================================
# GeoSite模块
# ============================================================


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
                data = json.load(f)
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

    for rule in rules:
        if not re.match(r"^geosite-(cn|.*@cn|.*!cn)\.srs$", rule):
            continue

        url = f"{SING_GEOSITE_URL}/{rule}"
        dest = os.path.join(SINGBOX_RULES_DIR, rule)
        log("INFO", f"下载sing-geosite规则：{os.path.basename(dest)} ({url})")

        if download_file(url, dest):
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

        if not merge_rule_type(merged_json, merged_srs, rule_type):
            log("ERROR", f"合并 {rule_type} 类型规则失败")
            sys.exit(1)


def merge_rule_type(merged_json, merged_srs, rule_type):
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


# ============================================================
# 主程序
# ============================================================


def main():
    parser = argparse.ArgumentParser(description="统一规则更新脚本")
    parser.add_argument("--ip-only", action="store_true", help="仅更新IP规则")
    parser.add_argument("--geosite-only", action="store_true", help="仅更新GeoSite规则")
    args = parser.parse_args()

    log("INFO", "=== 开始执行规则更新脚本 ===")
    init_env()

    if args.ip_only:
        download_ip_lists()
        merge_ip_files()
        convert_to_mikrotik()
        convert_to_singbox()
    elif args.geosite_only:
        process_sing_rules()
        merge_rules()
    else:
        download_ip_lists()
        merge_ip_files()
        convert_to_mikrotik()
        convert_to_singbox()
        process_sing_rules()
        merge_rules()

    log("INFO", "=== 规则更新完成 ===")


if __name__ == "__main__":
    main()
