#!/usr/bin/env python3

import argparse

from geosite_module import run_geosite_update
from ip_module import (
    run_ip_update,
    init_env,
    download_ip_lists,
    _load_all_ip_data,
    merge_ip_files,
    convert_to_mikrotik,
    convert_to_singbox,
)
from geosite_module import process_sing_rules, merge_rules
from utils import log


def main():
    parser = argparse.ArgumentParser(description="统一规则更新脚本")
    parser.add_argument("--ip-only", action="store_true", help="仅更新IP规则")
    parser.add_argument("--geosite-only", action="store_true", help="仅更新GeoSite规则")
    args = parser.parse_args()

    log("INFO", "=== 开始执行规则更新脚本 ===")

    if args.ip_only:
        run_ip_update()
    elif args.geosite_only:
        init_env()
        run_geosite_update()
    else:
        init_env()
        download_ip_lists()
        data = _load_all_ip_data()
        merge_ip_files(data)
        convert_to_mikrotik(data)
        convert_to_singbox()
        process_sing_rules()
        merge_rules()

    log("INFO", "=== 规则更新完成 ===")


if __name__ == "__main__":
    main()
