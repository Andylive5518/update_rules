# 规则更新说明

## 概述

本项目用于自动更新中国大陆、香港、澳门的 IP 地址列表，并生成 Mikrotik RouterOS、MosDNS 和 Sing-Box 使用的规则文件。

## 脚本说明

### update_rules.py（推荐）

统一的 Python 脚本，整合了原有两个 bash 脚本的所有功能。

```bash
# 全部更新
python3 update_rules.py

# 仅更新IP规则
python3 update_rules.py --ip-only

# 仅更新GeoSite规则
python3 update_rules.py --geosite-only
```

### 原有脚本（保留）

- `update_china_ip.sh` - 更新中国IP段（IPv4/IPv6）
- `update_mosdns_rules.sh` - 更新GeoSite域名规则

---

## 功能模块

### 1. China IP 模块

| 功能 | 说明 |
|------|------|
| 下载IP段 | 从 ispip.clang.cn 下载 CN/HK/MO 的 IPv4 和 IPv6 地址 |
| IP去重 | 基本去重 + 子网包含检测（如 10.0.0.0/8 包含 10.0.1.0/24） |
| 合并文件 | 合并 IPv4 和 IPv6 到统一文件 |
| 格式转换 | 生成 Mikrotik (.rsc) 和 Sing-Box (.srs) 格式 |

**输出文件：**

| 类型 | 路径 | 说明 |
|------|------|------|
| 原始IP | `clang/ip/*.txt` | 下载的原始IP段 |
| MosDNS | `rules/mosdns/*_all.txt` | 合并后的IP列表 |
| Mikrotik | `clang/ros/china_ipv4.rsc` | IPv4 地址列表 |
| Mikrotik | `clang/ros/china_ipv6.rsc` | IPv6 地址列表 |
| Mikrotik | `clang/ros/nocn_ipv4.rsc` | 非中国大陆IPv4 |
| Mikrotik | `clang/ros/nocn_ipv6.rsc` | 非中国大陆IPv6 |
| Sing-Box | `rules/sing-box/cn_all.srs` | 中国大陆规则集 |
| Sing-Box | `rules/sing-box/hk_all.srs` | 香港规则集 |
| Sing-Box | `rules/sing-box/mo_all.srs` | 澳门规则集 |

### 2. GeoSite 模块

| 功能 | 说明 |
|------|------|
| 获取规则列表 | 从 GitHub API 获取 sing-geosite 规则 |
| 过滤子集 | 自动跳过子集规则（如已有 google@cn 则跳过 google-adsense@cn） |
| 格式转换 | .srs → .json → .txt |
| 合并规则 | 合并所有 @cn 和 @!cn 规则 |

**输出文件：**

| 类型 | 路径 | 说明 |
|------|------|------|
| JSON | `rules/json/geosite-*.json` | 规则JSON文件 |
| MosDNS | `rules/mosdns/geosite-*.txt` | MosDNS格式规则 |
| Sing-Box | `rules/sing-box/geosite-*.srs` | Sing-Box规则集 |
| 合并 | `rules/json/geosite-all@cn.json` | 合并后的@cn规则 |
| 合并 | `rules/json/geosite-all@!cn.json` | 合并后的@!cn规则 |

---

## IP去重算法

### 基本去重
- 去除完全相同的 IP 段

### 子网包含检测
- 如果一个 IP 段被另一个更大的 IP 段包含，则去除冗余的子网
- 例如：`10.0.0.0/8` 包含 `10.0.1.0/24`，后者会被去除

### 算法流程
```
1. 读取所有IP段
2. 使用 set() 基本去重
3. 按前缀长度倒序排列（/32 > /24 > /16 > /8 > ...）
4. 依次检查每个IP段是否被已保留的IP段包含
5. 不被包含的IP段加入结果集
6. 按网络地址排序输出
```

### Mikrotik规则去重
在生成 Mikrotik 规则时，同一 IP 段可能来自多个数据源（如 cn.txt 和 hk.txt 都有相同的 IP）。去重逻辑：

- **CN list**：优先使用 CN 的条目，HK 和 MO 只添加不在 CN 中的
- **优先级**：CN > HK > MO

例如：
- cn.txt 有 `27.0.132.0/22`
- hk.txt 也有 `27.0.132.0/22`
- 生成规则时只保留 CN 的条目，不重复添加

---

## 目录结构

```
/opt/update_rules/
├── update_rules.py              # 统一更新脚本
├── update_china_ip.sh           # 保留：原IP更新脚本
├── update_mosdns_rules.sh       # 保留：原GeoSite更新脚本
├── update.md                    # 本说明文件
├── README.md
├── .github/workflows/
│   └── update-rules.yml         # GitHub Actions 配置
├── clang/
│   ├── ip/                      # 原始IP文件
│   │   ├── cn.txt
│   │   ├── cn_ipv6.txt
│   │   ├── hk.txt
│   │   ├── hk_ipv6.txt
│   │   └── ...
│   └── ros/                     # Mikrotik规则文件
│       ├── china_ipv4.rsc
│       ├── china_ipv6.rsc
│       ├── nocn_ipv4.rsc
│       └── nocn_ipv6.rsc
└── rules/
    ├── json/                    # JSON规则文件
    ├── mosdns/                  # MosDNS规则文件
    └── sing-box/                # Sing-Box规则文件
```

---

## 依赖要求

| 依赖 | 说明 |
|------|------|
| python3 | 脚本运行环境 |
| jq | JSON处理 |
| curl | 网络下载 |
| sing-box | 规则集编译/反编译 |

---

## GitHub Actions 自动更新

项目配置了 GitHub Actions 每日自动执行：

- **触发时间**：每天 19:00 UTC
- **触发方式**：`workflow_dispatch` 手动触发

自动执行流程：
1. 安装依赖（python3, jq, curl, sing-box）
2. 运行 `python3 update_rules.py`
3. 检查文件是否有变化
4. 如有变化，创建 GitHub Release
5. 清理7天前的旧 Release

### 更新日志

#### 2025-03-20
- 修复 APT 缓存路径验证错误：将 "Cache APT archives" 步骤移至 "Install dependencies" 步骤之后，确保缓存时目录已存在
- 升级 `softprops/action-gh-release@v1` → `v2`，解决 Node.js 20 弃用警告

---

## 常见问题

### Q: 如何手动触发更新？

在 GitHub 仓库页面进入 Actions 标签页，选择 "Update Network Rules" 工作流，点击 "Run workflow"。

### Q: 去重可以减少多少规则？

根据实际数据，去重通常可以减少 5%-15% 的规则数量，主要取决于数据源的重叠程度。

### Q: 为什么需要保留原有的 bash 脚本？

保留原脚本是为了兼容性和备份。如果 Python 脚本出现问题，可以回退使用 bash 版本。