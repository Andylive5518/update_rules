# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

这是一个网络规则自动更新项目，每日通过 GitHub Actions 自动生成和更新中国大陆、香港、澳门的 IP 地址列表以及网站分类规则。项目支持多种输出格式：Mikrotik RouterOS (.rsc)、MosDNS (.txt)、Sing-Box (.srs) 和 JSON 格式。

## 核心架构

### 双脚本并行处理架构
项目采用两个独立的bash脚本并行处理不同类型的规则：

1. **`update_china_ip.sh`** - IP地址处理流水线：
   - 从 `https://ispip.clang.cn` 下载原始IP地址文件（中国大陆、香港、澳门、三大运营商）
   - 从 SagerNet 仓库下载预编译的IP规则集
   - 合并IPv4和IPv6地址生成统一列表
   - 转换为Mikrotik RouterOS地址列表格式
   - 编译为Sing-Box二进制规则集

2. **`update_mosdns_rules.sh`** - Geosite规则处理流水线：
   - 通过GitHub API获取SagerNet/sing-geosite的可用规则
   - 智能过滤避免下载重复的子集规则
   - 批量下载.srs格式的geosite规则
   - 反编译为JSON格式并提取域名规则
   - 转换为MosDNS可用的文本格式
   - 合并生成`geosite-all@cn`和`geosite-all@!cn`聚合规则

### 数据转换流程
```
原始数据 → 中间格式 → 目标格式
IP文本 → JSON → RouterOS(.rsc) + Sing-Box(.srs) + MosDNS(.txt)
Geosite(.srs) → JSON → MosDNS(.txt) + JSON存档
```

### GitHub Actions自动化流程
- **触发方式**：每日19:00 UTC定时执行 + 手动触发
- **执行环境**：Ubuntu Latest，45分钟超时
- **核心步骤**：环境准备 → 脚本执行 → 变更检测 → Release发布 → 旧版本清理
- **发布策略**：rules目录打包 + clang文件直接发布，自动清理3天前的release

## 规则分类体系

### IP地址分类
- **CN**: 中国大陆+港澳IP地址
- **CTCC/CUCC/CMCC**: 三大运营商专用IP段
- **NOCN**: 包含保留地址段的非中国IP列表

### Geosite规则分类
- **@cn**: 中国大陆可访问的域名
- **@!cn**: 需要代理访问的域名
- **category-**: 分类规则（AI、游戏、媒体、金融等）
- 智能去重机制避免子集规则重复下载

## 常用开发命令

### 手动执行更新
```bash
# 更新IP地址规则（需要sing-box、jq、curl）
chmod +x update_china_ip.sh
./update_china_ip.sh

# 更新Geosite规则
chmod +x update_mosdns_rules.sh  
./update_mosdns_rules.sh
```

### 规则验证与调试
```bash
# 验证JSON格式
jq empty rules/json/geosite-*.json

# 手动编译Sing-Box规则
sing-box rule-set compile input.json -o output.srs

# 手动反编译规则集
sing-box rule-set decompile input.srs -o output.json

# 检查规则数量
find rules/ -name "*.json" | wc -l
wc -l rules/mosdns/*.txt
```

### GitHub工作流调试
```bash
# 本地模拟工作流环境
mkdir -p rules/{mosdns,sing-box,json} clang/{ros,ip}

# 检查文件变更（工作流使用的命令）
git status --porcelain rules clang

# 手动触发工作流
gh workflow run "Update Network Rules"
```

## 关键技术细节

### 错误处理机制
- 所有网络请求都有重试机制（--retry 3）
- 文件下载后验证非空
- 脚本失败时立即退出，工作流会中断
- 临时文件自动清理

### 性能优化
- APT包缓存减少依赖安装时间
- 并行处理两类规则
- 智能规则去重避免重复下载
- GitHub API批量获取减少请求次数

### 文件命名约定
所有生成的文件都保持一致的命名模式，便于用户识别和程序处理。规则文件按类型和地区标识符组织，确保不同用途的规则易于区分。