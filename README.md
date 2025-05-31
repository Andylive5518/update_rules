# IP、MOSDNS、Sing-Box规则每日自动更新项目

## 项目描述
本项目用于自动更新中国大陆、香港和澳门的 IP 地址列表，并生成 Mikrotik 路由器、MosDNS 和 Sing-Box 使用的规则文件。

## 功能
- 每日自动更新 IP 地址列表
- 生成 Mikrotik RouterOS 的地址列表 (.rsc 文件)
- 生成 MosDNS 和 Sing-Box 的规则文件 (JSON 格式)
- 支持 IPv4 和 IPv6 地址

## 文件结构
- `clang/ip/`: 原始 IP 地址文本文件
- `clang/ros/`: Mikrotik RouterOS 规则文件
- `rules/json/`: 网站分类规则 (geosite)
- `rules/mosdns/`: MosDNS 规则文件
- `rules/sing-box/`: Sing-Box 规则文件

## 自动更新
通过 GitHub Actions 每日自动更新规则文件，工作流配置见 `.github/workflows/update-rules.yml`

## 许可证
[MIT](LICENSE)