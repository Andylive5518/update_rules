#!/bin/bash

# 设置输出目录和文件名
readonly ROS_IP_DIR="/opt/clang/ros"
readonly DOWNLOAD_IP_DIR="/opt/clang/ip"
readonly MOSDNS_RULES_DIR="/opt/rules/mosdns"
readonly SINGBOX_RULES_DIR="/opt/rules/sing-box"
readonly JSON_DIR="/opt/rules/$(date +%Y%m%d)"
readonly LOG_FILE="/var/log/update_china_ip.log"

# 日志函数
log() {
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "$timestamp $1" >> "$LOG_FILE"
}

# 1. 初始化目录和检查命令
init_env() {
    log "开始初始化环境..."
    
    # 检查并创建所需目录
    for dir in "$ROS_IP_DIR" "$DOWNLOAD_IP_DIR" "$MOSDNS_RULES_DIR" "$SINGBOX_RULES_DIR" "$JSON_DIR"; do
        if [ ! -d "$dir" ]; then
            log "创建目录: $dir"
            mkdir -p "$dir"
        fi
    done
    
    # 检查必需的命令
    local required_commands=("curl" "jq" "sing-box")
    for cmd in "${required_commands[@]}"; do
        if ! command -v "$cmd" &> /dev/null; then
            log "错误: 未找到 $cmd 命令"
            exit 1
        fi
    done
    
    log "环境初始化完成"
}

# 2. 下载IP地址列表
download_ip_lists() {
    log "开始下载IP地址列表..."
    
    # 定义基础URL
    local base_url="https://ispip.clang.cn"
    
    # 下载IPv4地址列表
    local ipv4_files=(
        "$DOWNLOAD_IP_DIR/cn.txt"
        "$DOWNLOAD_IP_DIR/hk.txt"
        "$DOWNLOAD_IP_DIR/mo.txt"
        "$DOWNLOAD_IP_DIR/chinatelecom.txt"
        "$DOWNLOAD_IP_DIR/unicom_cnc.txt"
        "$DOWNLOAD_IP_DIR/cmcc.txt"
    )
    
    local ipv4_paths=(
        "all_cn.txt"
        "hk.txt"
        "mo.txt"
        "chinatelecom.txt"
        "unicom_cnc.txt"
        "cmcc.txt"
    )
    
    # 下载IPv6地址列表
    local ipv6_files=(
        "$DOWNLOAD_IP_DIR/cn_ipv6.txt"
        "$DOWNLOAD_IP_DIR/hk_ipv6.txt"
        "$DOWNLOAD_IP_DIR/mo_ipv6.txt"
        "$DOWNLOAD_IP_DIR/chinatelecom_ipv6.txt"
        "$DOWNLOAD_IP_DIR/unicom_cnc_ipv6.txt"
        "$DOWNLOAD_IP_DIR/cmcc_ipv6.txt"
    )
    
    local ipv6_paths=(
        "all_cn_ipv6.txt"
        "hk_ipv6.txt"
        "mo_ipv6.txt"
        "chinatelecom_ipv6.txt"
        "unicom_cnc_ipv6.txt"
        "cmcc_ipv6.txt"
    )
    
    # 下载sing-box规则
    local singbox_urls=(
        "https://raw.githubusercontent.com/SagerNet/sing-geoip/refs/heads/rule-set/geoip-cn.srs"
        "https://raw.githubusercontent.com/SagerNet/sing-geoip/refs/heads/rule-set/geoip-hk.srs"
        "https://raw.githubusercontent.com/SagerNet/sing-geoip/refs/heads/rule-set/geoip-mo.srs"
    )
    
    local singbox_files=(
        "$SINGBOX_RULES_DIR/geoip-cn.srs"
        "$SINGBOX_RULES_DIR/geoip-hk.srs"
        "$SINGBOX_RULES_DIR/geoip-mo.srs"
    )
    
    # 下载所有文件
    for i in "${!ipv4_files[@]}"; do
        local url="${base_url}/${ipv4_paths[$i]}"
        log "下载 ${url}"
        if ! curl -fsSL --retry 3 --max-time 30 "${url}" > "${ipv4_files[$i]}"; then
            log "错误: 无法下载 ${url}"
            exit 1
        fi
    done
    
    for i in "${!ipv6_files[@]}"; do
        local url="${base_url}/${ipv6_paths[$i]}"
        log "下载 ${url}"
        if ! curl -fsSL --retry 3 --max-time 30 "${url}" > "${ipv6_files[$i]}"; then
            log "错误: 无法下载 ${url}"
            exit 1
        fi
    done
    
    for i in "${!singbox_urls[@]}"; do
        log "下载 ${singbox_urls[$i]}"
        if ! curl -fsSL --retry 3 --max-time 30 "${singbox_urls[$i]}" > "${singbox_files[$i]}"; then
            log "错误: 无法下载 ${singbox_urls[$i]}"
            exit 1
        fi
    done
    
    log "IP地址列表下载完成"
}

# 3. 合并IPv4和IPv6文件
merge_ip_files() {
    log "开始合并IP文件..."
    
    # 合并中国大陆IP
    log "合并中国大陆IPv4和IPv6地址..."
    if cat "$DOWNLOAD_IP_DIR/cn.txt" "$DOWNLOAD_IP_DIR/cn_ipv6.txt" > "$MOSDNS_RULES_DIR/cn_all.txt"; then
        local cn_count=$(wc -l < "$MOSDNS_RULES_DIR/cn_all.txt")
        log "中国大陆IP合并完成: $DOWNLOAD_IP_DIR/cn.txt + $DOWNLOAD_IP_DIR/cn_ipv6.txt -> $MOSDNS_RULES_DIR/cn_all.txt, 共 $cn_count 条记录"
    else
        log "错误: 合并中国大陆IP失败"
        exit 1
    fi
    
    # 合并香港IP
    log "合并香港IPv4和IPv6地址..."
    if cat "$DOWNLOAD_IP_DIR/hk.txt" "$DOWNLOAD_IP_DIR/hk_ipv6.txt" > "$MOSDNS_RULES_DIR/hk_all.txt"; then
        local hk_count=$(wc -l < "$MOSDNS_RULES_DIR/hk_all.txt")
        log "香港IP合并完成: $DOWNLOAD_IP_DIR/hk.txt + $DOWNLOAD_IP_DIR/hk_ipv6.txt -> $MOSDNS_RULES_DIR/hk_all.txt, 共 $hk_count 条记录"
    else
        log "错误: 合并香港IP失败"
        exit 1
    fi
    
    # 合并澳门IP
    log "合并澳门IPv4和IPv6地址..."
    if cat "$DOWNLOAD_IP_DIR/mo.txt" "$DOWNLOAD_IP_DIR/mo_ipv6.txt" > "$MOSDNS_RULES_DIR/mo_all.txt"; then
        local mo_count=$(wc -l < "$MOSDNS_RULES_DIR/mo_all.txt")
        log "澳门IP合并完成: $DOWNLOAD_IP_DIR/mo.txt + $DOWNLOAD_IP_DIR/mo_ipv6.txt -> $MOSDNS_RULES_DIR/mo_all.txt, 共 $mo_count 条记录"
    else
        log "错误: 合并澳门IP失败"
        exit 1
    fi
    
    log "IP文件合并完成"
}

# 4. 转换为Mikrotik格式
convert_to_mikrotik() {
    log "开始转换为Mikrotik格式..."
    
    log "开始生成IPv4地址列表..."
    # 创建IPv4脚本
    {
        log "添加IPv4防火墙规则..."
        echo "/ip firewall address-list remove [find list=CN]"
        echo "/ip firewall address-list remove [find list=HK]"
        echo "/ip firewall address-list remove [find list=MO]"
        echo "/ip firewall address-list"
        
        # 添加IPv4保留地址
        echo "add address=10.0.0.0/8 list=CN disabled=no comment=Reserved_IP"
        echo "add address=100.64.0.0/10 list=CN disabled=no comment=Reserved_IP"
        echo "add address=172.16.0.0/12 list=CN disabled=no comment=Reserved_IP"
        echo "add address=192.168.0.0/16 list=CN disabled=no comment=Reserved_IP"
        echo "add address=198.18.0.0/15 list=CN disabled=no comment=Reserved_IP"
        echo "add address=224.0.0.0/4 list=CN disabled=no comment=Reserved_IP"
        
        # 添加中国大陆IPv4
        grep -v ":" "$DOWNLOAD_IP_DIR/cn.txt" | while read -r line; do
            [ ! -z "$line" ] && echo "add address=$line list=CN disabled=no"
        done
        
        # 添加香港IPv4
        grep -v ":" "$DOWNLOAD_IP_DIR/hk.txt" | while read -r line; do
            [ ! -z "$line" ] && echo "add address=$line list=HK disabled=no"
        done
        
        # 添加澳门IPv4
        grep -v ":" "$DOWNLOAD_IP_DIR/mo.txt" | while read -r line; do
            [ ! -z "$line" ] && echo "add address=$line list=MO disabled=no"
        done
        
        # 添加中国电信IPv4
        grep -v ":" "$DOWNLOAD_IP_DIR/chinatelecom.txt" | while read -r line; do
            [ ! -z "$line" ] && echo "add address=$line list=CTCC disabled=no"
        done
        
        # 添加中国联通IPv4
        grep -v ":" "$DOWNLOAD_IP_DIR/unicom_cnc.txt" | while read -r line; do
            [ ! -z "$line" ] && echo "add address=$line list=CUCC disabled=no"
        done
        
        # 添加中国移动IPv4
        grep -v ":" "$DOWNLOAD_IP_DIR/cmcc.txt" | while read -r line; do
            [ ! -z "$line" ] && echo "add address=$line list=CMCC disabled=no"
        done
    } > "$ROS_IP_DIR/china_ipv4.rsc"
    
    # 统计IPv4规则数量
    local ipv4_count=$(grep -c "^add address=" "$ROS_IP_DIR/china_ipv4.rsc")
    log "IPv4地址列表生成完成: $DOWNLOAD_IP_DIR/{cn,hk,mo,chinatelecom,unicom_cnc,cmcc}.txt -> $ROS_IP_DIR/china_ipv4.rsc, 共 $ipv4_count 条规则"

    log "开始生成IPv6地址列表..."
    # 创建IPv6脚本
    {
        log "添加IPv6防火墙规则..."
        echo "/ipv6 firewall address-list remove [find list=CN6]"
        echo "/ipv6 firewall address-list remove [find list=HK6]"
        echo "/ipv6 firewall address-list remove [find list=MO6]"
        echo "/ipv6 firewall address-list"
        
        # 添加IPv6保留地址
        echo "add address=fc00::/8 list=CN6 disabled=no comment=Reserved_IP"
        echo "add address=fd00::/8 list=CN6 disabled=no comment=Reserved_IP"
        echo "add address=ff00::/8 list=CN6 disabled=no comment=Reserved_IP"
        
        # 添加中国大陆IPv6
        grep ":" "$DOWNLOAD_IP_DIR/cn_ipv6.txt" | while read -r line; do
            [ ! -z "$line" ] && echo "add address=$line list=CN6 disabled=no"
        done
        
        # 添加香港IPv6
        grep ":" "$DOWNLOAD_IP_DIR/hk_ipv6.txt" | while read -r line; do
            [ ! -z "$line" ] && echo "add address=$line list=HK6 disabled=no"
        done
        
        # 添加澳门IPv6
        grep ":" "$DOWNLOAD_IP_DIR/mo_ipv6.txt" | while read -r line; do
            [ ! -z "$line" ] && echo "add address=$line list=MO6 disabled=no"
        done
        
        # 添加中国电信IPv6
        grep ":" "$DOWNLOAD_IP_DIR/chinatelecom_ipv6.txt" | while read -r line; do
            [ ! -z "$line" ] && echo "add address=$line list=CTCC6 disabled=no"
        done
        
        # 添加中国联通IPv6
        grep ":" "$DOWNLOAD_IP_DIR/unicom_cnc_ipv6.txt" | while read -r line; do
            [ ! -z "$line" ] && echo "add address=$line list=CUCC6 disabled=no"
        done
        
        # 添加中国移动IPv6
        grep ":" "$DOWNLOAD_IP_DIR/cmcc_ipv6.txt" | while read -r line; do
            [ ! -z "$line" ] && echo "add address=$line list=CMCC6 disabled=no"
        done
    } > "$ROS_IP_DIR/china_ipv6.rsc"
    
    # 统计IPv6规则数量
    local ipv6_count=$(grep -c "^add address=" "$ROS_IP_DIR/china_ipv6.rsc")
    log "IPv6地址列表生成完成: $DOWNLOAD_IP_DIR/{cn,hk,mo,chinatelecom,unicom_cnc,cmcc}_ipv6.txt -> $ROS_IP_DIR/china_ipv6.rsc, 共 $ipv6_count 条规则"
}

# 5. 转换为sing-box格式
convert_to_singbox() {
    log "开始转换为sing-box格式..."
    
    # 转换中国大陆IP
    log "开始转换中国大陆IP为sing-box格式..."
    local china_json=$(mktemp)
    if cat "$MOSDNS_RULES_DIR/cn_all.txt" | jq -R -s 'split("\n") | map(select(length>0))' | \
       jq '{version:1,rules:[{ip_cidr:.}]}' > "$china_json"; then
        local cn_count=$(jq '.rules[0].ip_cidr|length' "$china_json")
        log "中国大陆IP JSON转换完成: $MOSDNS_RULES_DIR/cn_all.txt -> 临时文件, 包含 $cn_count 条记录"
        log "编译中国大陆IP规则集..."
        if sing-box rule-set compile "$china_json" -o "$SINGBOX_RULES_DIR/cn_all.srs"; then
            log "中国大陆IP规则集编译完成: 临时文件 -> $SINGBOX_RULES_DIR/cn_all.srs"
            rm "$china_json"
        else
            log "错误: 编译中国大陆IP规则集失败"
            mv "$china_json" "$JSON_DIR/cn_all.json"
            exit 1
        fi
    else
        log "错误: 转换中国大陆IP为JSON格式失败"
        exit 1
    fi
    
    # 转换香港IP
    log "开始转换香港IP为sing-box格式..."
    local hk_json=$(mktemp)
    if cat "$MOSDNS_RULES_DIR/hk_all.txt" | jq -R -s 'split("\n") | map(select(length>0))' | \
       jq '{version:1,rules:[{ip_cidr:.}]}' > "$hk_json"; then
        local hk_count=$(jq '.rules[0].ip_cidr|length' "$hk_json")
        log "香港IP JSON转换完成: $MOSDNS_RULES_DIR/hk_all.txt -> 临时文件, 包含 $hk_count 条记录"
        log "编译香港IP规则集..."
        if sing-box rule-set compile "$hk_json" -o "$SINGBOX_RULES_DIR/hk_all.srs"; then
            log "香港IP规则集编译完成: 临时文件 -> $SINGBOX_RULES_DIR/hk_all.srs"
            rm "$hk_json"
        else
            log "错误: 编译香港IP规则集失败"
            mv "$hk_json" "$JSON_DIR/hk_all.json"
            exit 1
        fi
    else
        log "错误: 转换香港IP为JSON格式失败"
        exit 1
    fi
    
    # 转换澳门IP
    log "开始转换澳门IP为sing-box格式..."
    local mo_json=$(mktemp)
    if cat "$MOSDNS_RULES_DIR/mo_all.txt" | jq -R -s 'split("\n") | map(select(length>0))' | \
       jq '{version:1,rules:[{ip_cidr:.}]}' > "$mo_json"; then
        local mo_count=$(jq '.rules[0].ip_cidr|length' "$mo_json")
        log "澳门IP JSON转换完成: $MOSDNS_RULES_DIR/mo_all.txt -> 临时文件, 包含 $mo_count 条记录"
        log "编译澳门IP规则集..."
        if sing-box rule-set compile "$mo_json" -o "$SINGBOX_RULES_DIR/mo_all.srs"; then
            log "澳门IP规则集编译完成: 临时文件 -> $SINGBOX_RULES_DIR/mo_all.srs"
            rm "$mo_json"
        else
            log "错误: 编译澳门IP规则集失败"
            mv "$mo_json" "$JSON_DIR/mo_all.json"
            exit 1
        fi
    else
        log "错误: 转换澳门IP为JSON格式失败"
        exit 1
    fi
    
    log "sing-box格式转换完成"
}

main() {
    init_env
    download_ip_lists
    convert_to_mikrotik
    merge_ip_files
    convert_to_singbox
    log "所有操作已完成"
}

main
