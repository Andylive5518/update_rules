#!/usr/bin/env python3

import ipaddress
from utils import log


def _parse_network(cidr_str):
    try:
        return ipaddress.ip_network(cidr_str, strict=False)
    except ValueError:
        return None


def deduplicate_ip_list(cidr_list, is_ipv6=False):
    """O(n log n) 去重：排序后线性扫描合并被包含的子网。"""
    networks = []
    invalid_count = 0

    for cidr in cidr_list:
        cidr = cidr.strip()
        if not cidr or cidr.startswith("#"):
            continue
        net = _parse_network(cidr)
        if net is not None:
            networks.append(net)
        else:
            invalid_count += 1

    if invalid_count > 0:
        log("WARNING", f"跳过 {invalid_count} 条无效CIDR")

    total_valid = len(networks)
    unique_networks = sorted(
        set(networks), key=lambda n: (n.network_address, n.prefixlen)
    )
    duplicate_count = total_valid - len(unique_networks)

    result = []
    subnet_count = 0
    for net in unique_networks:
        if result and net.subnet_of(result[-1]):
            subnet_count += 1
            continue
        result.append(net)

    log(
        "INFO",
        f"去重完成: {len(cidr_list)} -> {len(result)}"
        f" (完全重复 {duplicate_count}, 子网冗余 {subnet_count},"
        f" 无效 {invalid_count})",
    )
    return [str(n) for n in result]


def deduplicate_file(filepath, is_ipv6=False):
    import os

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


def merge_dedup_with_source(ip_sources, is_ipv6=False):
    """合并多个来源的 IP 列表并去重，保留来源标注。

    ip_sources: [(ip_list, source_tag), ...] 按优先级排列
    返回: [(address_str, comment), ...] 去重后的结果

    算法: O(n log n) — 收集所有条目后排序，线性扫描合并。
    """
    entries = []
    for ip_list, source_tag in ip_sources:
        for cidr in ip_list:
            net = _parse_network(cidr.strip())
            if net is None:
                continue
            entries.append((net, source_tag))

    entries.sort(key=lambda e: (e[0].network_address, e[0].prefixlen))

    merged = []
    duplicate_count = 0
    subnet_count = 0
    for net, tag in entries:
        if merged and net.subnet_of(merged[-1][0]):
            if net == merged[-1][0]:
                duplicate_count += 1
            else:
                subnet_count += 1
            existing_comments = merged[-1][1]
            if tag and tag not in existing_comments:
                existing_comments.add(tag)
            continue

        merged.append((net, {tag} if tag else set()))

    total_input = sum(len(ips) for ips, _ in ip_sources)
    log(
        "INFO",
        f"合并去重完成: {total_input} -> {len(merged)}"
        f" (完全重复 {duplicate_count}, 子网冗余 {subnet_count})",
    )

    result = []
    for net, tags in merged:
        comment = ",".join(sorted(tags)) if tags else ""
        result.append((str(net), comment))

    return result
