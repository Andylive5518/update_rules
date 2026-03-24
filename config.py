#!/usr/bin/env python3
"""常量配置"""

# ============================================================
# 目录配置
# ============================================================

DOWNLOAD_IP_DIR = "./clang/ip"
ROS_IP_DIR = "./clang/ros"
MOSDNS_RULES_DIR = "./rules/mosdns"
SINGBOX_RULES_DIR = "./rules/sing-box"
JSON_DIR = "./rules/json"

# ============================================================
# URL 配置
# ============================================================

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

# ============================================================
# IP 文件映射
# ============================================================

IPV4_FILES = [
    "cn.txt",
    "hk.txt",
    "mo.txt",
    "ctcc.txt",
    "cucc.txt",
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
    "ctcc_ipv6.txt",
    "cucc_ipv6.txt",
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

# ============================================================
# 保留地址
# ============================================================

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
