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

    # 按 (network_address, prefixlen) 排序 — 大网段在前，子网紧随其后
    networks = sorted(set(networks), key=lambda n: (n.network_address, n.prefixlen))

    result = []
    for net in networks:
        # 如果当前网段被 result 最后一个大网段包含，跳过
        if result and net.subnet_of(result[-1]):
            continue
        result.append(net)

    original_count = len(cidr_list)
    final_count = len(result)
    removed = original_count - final_count
    log("INFO", f"去重完成: {original_count} -> {final_count} (移除 {removed} 条)")
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

    # 按 (network_address, prefixlen) 排序
    entries.sort(key=lambda e: (e[0].network_address, e[0].prefixlen))

    # 线性扫描：维护一个栈，栈顶为当前最大的覆盖网段
    merged = []  # [(network, combined_comments)]
    for net, tag in entries:
        if merged and net.subnet_of(merged[-1][0]):
            # 被栈顶网段包含，合并 tag
            existing_comments = merged[-1][1]
            if tag and tag not in existing_comments:
                existing_comments.add(tag)
            continue

        # 新的不被包含的网段（由于排序，不可能包含栈中已有的更小前缀网段
        # 但可能覆盖后续更大前缀的网段，栈式处理自然解决）
        merged.append((net, {tag} if tag else set()))

    result = []
    for net, tags in merged:
        comment = ",".join(sorted(tags)) if tags else ""
        result.append((str(net), comment))

    return result
