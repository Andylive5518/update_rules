#!/bin/bash

# 基础配置
readonly MOSDNS_RULES_DIR="./rules/mosdns"
readonly SINGBOX_RULES_DIR="./rules/sing-box"
readonly JSON_DIR="./rules/json"
readonly REQUIRED_COMMANDS=("sing-box" "jq" "curl")

# 远程URL配置
readonly LOYALSOLDIER_URL="https://raw.githubusercontent.com/Loyalsoldier/v2ray-rules-dat/release"
readonly SING_GEOSITE_URL="https://raw.githubusercontent.com/SagerNet/sing-geosite/rule-set"
readonly SING_GEOSITE_API="https://api.github.com/repos/SagerNet/sing-geosite/git/trees/rule-set"

# 基础规则文件配置
declare -rA BASE_RULES=(
    ["direct-list.txt"]="$LOYALSOLDIER_URL/direct-list.txt"
    ["proxy-list.txt"]="$LOYALSOLDIER_URL/proxy-list.txt"
    ["china-list.txt"]="$LOYALSOLDIER_URL/china-list.txt"
    ["gfw.txt"]="$LOYALSOLDIER_URL/gfw.txt"
)

# 错误处理函数
die() {
    echo "错误: $1"
    echo "脚本执行异常终止"
    exit 1
}

# 日志函数
log() {
    local level="$1"
    local message="${*:2}"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] [$level] $message"
}

# 检查命令是否存在
check_command() {
    local cmd="$1"
    command -v "$cmd" &>/dev/null || {
        case "$cmd" in
            "sing-box") die "请访问 https://github.com/SagerNet/sing-box/releases 下载安装 sing-box" ;;
            "jq") die "请安装 jq：'apt install jq' 或 'yum install jq'" ;;
            *) die "请安装 $cmd" ;;
        esac
    }
}

# 初始化环境
init_env() {
    log "INFO" "=== 开始执行规则更新脚本 ==="
    
    # 检查必需命令
    local cmd
    for cmd in "${REQUIRED_COMMANDS[@]}"; do
        check_command "$cmd"
        log "INFO" "检查命令 $cmd: 已安装"
    done

    # 创建必要目录
    local dir
    for dir in "$MOSDNS_RULES_DIR" "$SINGBOX_RULES_DIR" "$JSON_DIR"; do
        if [[ ! -d "$dir" ]]; then
            mkdir -p "$dir" || die "创建目录失败：$dir"
            log "INFO" "创建目录：$dir"
        fi
    done
}

# 下载文件
download_file() {
    local url="$1"
    local output="$2"
    local desc="$3"
    local base_name=$(basename "$output")
    
    log "INFO" "下载${desc}：$base_name ($url)"
    
    if curl -sSL --max-time 30 --retry 3 --retry-delay 2 "$url" -o "$output" && [[ -f "$output" ]]; then
        # 检查文件大小
        if [[ ! -s "$output" ]]; then
            log "ERROR" "下载的文件为空：$output"
            return 1
        fi
        return 0
    fi
    
    log "ERROR" "${desc}下载失败：$base_name"
    return 1
}

# 下载基础规则
download_base_rules() {
    log "INFO" "开始下载基础规则文件"
    local count=0
    local total_rules=0
    
    for file in "${!BASE_RULES[@]}"; do
        local url="${BASE_RULES[$file]}"
        if download_file "$url" "$MOSDNS_RULES_DIR/$file" "基础规则"; then
            local rule_count=$(wc -l < "$MOSDNS_RULES_DIR/$file")
            log "INFO" "基础规则下载完成：$file (共 $rule_count 条规则)"
            ((total_rules+=rule_count))
            ((count++))
        fi
    done
    
    log "INFO" "基础规则下载完成，共下载 $count 个规则文件，包含 $total_rules 条规则"
    return 0
}

# 获取并过滤sing-geosite规则
get_sing_rules() {
    # 获取规则列表
    local rules_list response
    response=$(curl -sSL --retry 3 --max-time 30 --retry-delay 2 \
        -H "Accept: application/vnd.github.v3+json" "$SING_GEOSITE_API") || {
        log "ERROR" "获取规则列表失败"
        return 1
    }

    rules_list=$(jq -r '.tree[].path | select(test("^geosite-.*\\.srs$"))' <<< "$response" 2>/dev/null) || {
        log "ERROR" "解析规则列表失败"
        return 1
    }

    [[ -z "$rules_list" ]] && {
        log "ERROR" "规则列表为空"
        return 1
    }

    # 先收集所有主规则
    local main_rules=()
    while IFS= read -r rule; do
        # 主规则格式：geosite-name@cn.srs 或 geosite-name@!cn.srs
        # 不包含额外连字符(-)的规则被视为主规则
        if [[ "$rule" =~ ^geosite-([^-]+)(@cn|@!cn)\.srs$ ]]; then
            main_rules+=("${BASH_REMATCH[1]}${BASH_REMATCH[2]}")
        fi
    done < <(echo "$rules_list")

    # 处理规则
    while IFS= read -r rule; do
        # 跳过不符合基本格式的规则
        if ! [[ "$rule" =~ ^geosite-(cn|geolocation-!cn|category.*!cn|.*@(cn|!cn))\.srs$ ]]; then
            continue
        fi

        # 检查是否为子集规则
        if [[ "$rule" =~ ^geosite-([^@]+)(@cn|@!cn)\.srs$ ]]; then
            local rule_base="${BASH_REMATCH[1]}"
            local rule_suffix="${BASH_REMATCH[2]}"
            
            # 如果规则名包含连字符，检查是否为子集
            if [[ "$rule_base" =~ ^([^-]+)-.*$ ]]; then
                local main_rule_name="${BASH_REMATCH[1]}${rule_suffix}"
                # 检查对应的主规则是否存在
                if [[ " ${main_rules[*]} " == *" $main_rule_name "* ]]; then
                    log "INFO" "跳过子集规则：$rule (属于主规则：geosite-$main_rule_name.srs)"
                    continue
                fi
            fi
        fi

        echo "$rule"
    done < <(echo "$rules_list") | sort -t@ -k1,1 -k2,2n
}

# 转换规则文件
convert_rule() {
    local srs_file="$1"
    local json_file="${srs_file%.*}.json"
    local txt_file="${srs_file%.*}.txt"
    local temp_dir

    # 检查源文件是否存在且非空
    if [[ ! -s "$SINGBOX_RULES_DIR/$srs_file" ]]; then
        log "ERROR" "源文件不存在或为空：$SINGBOX_RULES_DIR/$srs_file"
        return 1
    fi

    # 创建临时目录
    temp_dir=$(mktemp -d) || {
        log "ERROR" "创建临时目录失败"
        return 1
    }
    
    local temp_json="$temp_dir/$json_file"
    
    # 确保在函数退出时清理临时目录
    trap 'rm -rf "$temp_dir"' EXIT
    
    # 转换为JSON
    if ! sing-box rule-set decompile "$SINGBOX_RULES_DIR/$srs_file" -o "$temp_json" 2>/dev/null; then
        log "ERROR" "规则转换失败：$srs_file -> $json_file"
        return 1
    fi

    # 检查转换后的JSON文件是否有效
    if ! jq empty "$temp_json" 2>/dev/null; then
        log "ERROR" "转换后的JSON文件无效：$json_file"
        return 1
    fi
    
    # 移动临时文件到目标位置
    mv "$temp_json" "$JSON_DIR/$json_file"

    # 提取规则
    local jq_script='
    .rules[0] | 
    (if has("domain") then
        if (.domain | type) == "array" then .domain[] else .domain end
        | select(length > 0) | "full:" + .
    else empty end),
    (if has("domain_suffix") then
        if (.domain_suffix | type) == "array" then .domain_suffix[] else .domain_suffix end
        | select(length > 0) | "domain:" + .
    else empty end),
    (if has("domain_keyword") then
        if (.domain_keyword | type) == "array" then .domain_keyword[] else .domain_keyword end
        | select(length > 0) | "keyword:" + .
    else empty end),
    (if has("domain_regex") then
        if (.domain_regex | type) == "array" then .domain_regex[] else .domain_regex end
        | select(length > 0) | "regexp:" + .
    else empty end)'

    # 检查JSON文件是否有效
    if ! jq empty "$JSON_DIR/$json_file" &>/dev/null; then
        log "ERROR" "无效的JSON文件：$json_file"
        return 1
    fi

    # 提取规则
    if ! jq -r "$jq_script" "$JSON_DIR/$json_file" 2>/dev/null | grep . > "$MOSDNS_RULES_DIR/$txt_file"; then
        log "ERROR" "规则提取失败：$json_file -> $txt_file"
        return 1
    fi

    # 检查提取结果
    if [[ ! -s "$MOSDNS_RULES_DIR/$txt_file" ]]; then
        log "WARNING" "提取的规则文件为空：$txt_file"
        return 1
    fi
    
    local count=$(wc -l < "$MOSDNS_RULES_DIR/$txt_file")
    log "INFO" "规则转换完成：$txt_file (共 $count 条规则)"
    return 0
}

# 下载和处理sing-geosite规则
process_sing_rules() {
    local rule url
    local count=0
    local total_rules=0
    local failed_rules=()
    
    while IFS= read -r rule; do
        [[ "$rule" =~ ^geosite-(cn|.*@cn|.*!cn)\.srs$ ]] || continue
        url="$SING_GEOSITE_URL/$rule"
        if download_file "$url" "$SINGBOX_RULES_DIR/$rule" "sing-geosite规则"; then
            # 检查下载的文件是否存在且非空
            if [[ ! -s "$SINGBOX_RULES_DIR/$rule" ]]; then
                log "ERROR" "下载的文件为空：$rule"
                rm -f "$SINGBOX_RULES_DIR/$rule"
                failed_rules+=("$rule")
                continue
            fi
            
            if convert_rule "$rule"; then
                local rule_count=$(wc -l < "$MOSDNS_RULES_DIR/${rule%.*}.txt")
                ((total_rules+=rule_count))
                ((count++))
            else
                failed_rules+=("$rule")
                rm -f "$SINGBOX_RULES_DIR/$rule"
            fi
        fi
    done < <(get_sing_rules)
    
    if [[ ${#failed_rules[@]} -gt 0 ]]; then
        log "WARNING" "以下规则处理失败：${failed_rules[*]}"
    fi
    
    if [[ $count -gt 0 ]]; then
        log "INFO" "sing-geosite规则下载完成，共下载并转换 $count 个规则文件，包含 $total_rules 条规则"
        return 0
    fi
    return 1
}

# 合并规则文件
merge_rules() {
    local types=("@cn" "@!cn")
    for type in "${types[@]}"; do
        local merged_json="$JSON_DIR/geosite-all${type}.json"
        local merged_srs="$SINGBOX_RULES_DIR/geosite-all${type}.srs"
        local search_pattern
        if [[ "$type" == "@!cn" ]]; then
            search_pattern="-name \"geosite-*@!cn.json\" -o -name \"geosite-*!cn.json\""
        else
            search_pattern="-name \"geosite-*${type}.json\""
        fi
        merge_rule_type "$merged_json" "$merged_srs" "$type" "$search_pattern" || return 1
    done
}

# 合并指定类型的规则文件
merge_rule_type() {
    local merged_json="$1" merged_srs="$2" rule_type="$3" search_pattern="$4"
    log "INFO" "开始合并 ${rule_type} 类型规则"

    # 1. 查找目标文件
    local files=()
    while IFS= read -r -d '' file; do
        [[ -f "$file" ]] && files+=("$file")
    done < <(eval "find \"$JSON_DIR\" \( $search_pattern \) \
        ! -name \"geosite-cn.json\" \
        ! -name \"geosite-geolocation-!cn.json\" \
        ! -name \"geosite-all${rule_type}.json\" \
        -type f -print0")

    # 2. 检查文件存在性
    if ((${#files[@]} == 0)); then
        log "WARNING" "未找到 ${rule_type} 类型的规则文件"
        return 1
    fi

    # 3. 执行合并操作
    log "INFO" "正在合并 ${#files[@]} 个规则文件"
    if ! jq -n '
        # 规范化字段值
        def normalize:
            if type == "array" then .[]
            elif type == "string" then .
            else empty end;

        # 合并规则
        reduce inputs.rules[0] as $rule (
            {
                domain: [],
                domain_suffix: [],
                domain_keyword: [],
                domain_regex: []
            };
            .domain += [($rule.domain | if . then normalize else empty end)] |
            .domain_suffix += [($rule.domain_suffix | if . then normalize else empty end)] |
            .domain_keyword += [($rule.domain_keyword | if . then normalize else empty end)] |
            .domain_regex += [($rule.domain_regex | if . then normalize else empty end)]
        ) |
        # 清理和去重
        to_entries |
        map(
            select(.value != null and .value != []) |
            .value |= (flatten | map(select(. != null and . != "")) | unique)
        ) |
        from_entries |
        # 构建最终输出
        {
            version: 1,
            rules: [.]
        }' "${files[@]}" > "$merged_json"; then
        log "ERROR" "规则合并失败，请检查JSON文件格式"
        return 1
    fi

    # 检查合并后的规则数量
    local merged_count
    merged_count=$(jq '.rules[0] | ([.domain, .domain_suffix, .domain_keyword, .domain_regex] | flatten | length)' "$merged_json") || {
        log "ERROR" "检查合并后的规则数量失败"
        return 1
    }
    if (( merged_count == 0 )); then
        log "ERROR" "合并后的规则文件为空"
        return 1
    fi
    log "INFO" "合并后的规则数量：$merged_count"

    # 4. 编译规则集
    log "INFO" "正在编译规则集: ${merged_json}"
    if ! sing-box rule-set compile "$merged_json" -o "$merged_srs"; then
        log "ERROR" "规则编译失败: $merged_srs"
        return 1
    fi

    # 5. 转换规则格式
    log "INFO" "正在转换规则格式: ${merged_srs}"
    if ! convert_rule "$(basename "$merged_srs")"; then
        log "ERROR" "规则转换失败: ${merged_srs%.*}.txt"
        return 1
    fi

    # 6. 替换旧文件
    log "INFO" "正在替换旧文件..."
    
    # 先检查是否有文件需要替换
    local files_to_replace=()
    if [[ "$rule_type" == "@!cn" ]]; then
        # 对于 !cn 规则，需要匹配两种可能的模式
        mapfile -t files_to_replace < <(find "$JSON_DIR" "$SINGBOX_RULES_DIR" "$MOSDNS_RULES_DIR" \
            \( -name "geosite-*@!cn.*" -o -name "geosite-*!cn.*" \) \
            ! -name "geosite-all@!cn.*" \
            ! -name "geosite-cn.*" \
            ! -name "geosite-geolocation-!cn.*" \
            ! -path "$merged_json" \
            ! -path "$merged_srs" \
            ! -path "${merged_srs%.*}.txt" \
            -type f 2>/dev/null)
    else
        # 对于其他规则，使用原来的匹配模式
        mapfile -t files_to_replace < <(find "$JSON_DIR" "$SINGBOX_RULES_DIR" "$MOSDNS_RULES_DIR" \
            -name "geosite-*${rule_type}.*" \
            ! -name "geosite-all${rule_type}.*" \
            ! -name "geosite-cn.*" \
            ! -name "geosite-geolocation-!cn.*" \
            ! -path "$merged_json" \
            ! -path "$merged_srs" \
            ! -path "${merged_srs%.*}.txt" \
            -type f 2>/dev/null)
    fi

    if (( ${#files_to_replace[@]} > 0 )); then
        log "INFO" "替换 ${#files_to_replace[@]} 个旧文件"
        for file in "${files_to_replace[@]}"; do
            rm -f "$file"
        done
    else
        log "INFO" "没有需要替换的文件"
    fi

    return 0
}

# 主程序
main() {
    if ! init_env; then
        log "ERROR" "初始化环境失败"
        exit 1
    fi
    if ! download_base_rules; then
        log "ERROR" "下载基础规则失败"
        exit 1
    fi
    if ! process_sing_rules; then
        log "ERROR" "处理 sing-geosite 规则失败"
        exit 1
    fi
    if ! merge_rules; then
        log "ERROR" "合并规则失败"
        exit 1
    fi
    
    log "INFO" "=== 规则更新完成 ==="
}

# 执行主程序
main
