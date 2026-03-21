#!/usr/bin/env python3

import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime


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


def download_files_parallel(tasks, max_workers=8):
    """并发下载多个文件。

    tasks: [(url, output_path), ...]
    返回失败的 (url, output_path) 列表。
    """
    failed = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {
            executor.submit(download_file, url, path): (url, path)
            for url, path in tasks
        }
        for future in as_completed(future_map):
            url, path = future_map[future]
            try:
                if not future.result():
                    failed.append((url, path))
            except Exception:
                failed.append((url, path))
    return failed


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


def check_required_commands(commands):
    for cmd in commands:
        if not shutil.which(cmd):
            log("ERROR", f"未找到 {cmd} 命令")
            sys.exit(1)
        log("INFO", f"检查命令 {cmd}: 已安装")


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
