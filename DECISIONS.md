# 麻将工程决定

## 2026-09-11 — 独立子应用，不建立通用游戏平台

保留 `zorrofox/mahjong` 的香港麻将规则、计分、本地策略和原生网页。小家只增加娱乐室卡片、
同源前缀转发和缓存排除。麻将不读取小家聊天、记忆、Profile、数据库或 Relay 登录密钥。
斗地主继续自己的仓库和裁判，不共享可变状态、牌局文件或官端 lease。

## 服务端身份与稳定座位

访客身份由随机 HttpOnly Cookie 找到服务端记录，不能由 `player_id` 或昵称声明。
房间成员与 seat 顺序保存在同一 Room；HTTP、WS、MCP 最终都使用这个绑定和同一个规则入口。
不保留旧公开身份参数接口，不提供匿名全手牌 fallback。未知私有房间与无权房间统一拒绝。
仅首次开局前接纳新成员、空位补 AI；此阶段不做 Human↔AI takeover。离线是连接状态，不能改变席位类型。

## 房间运行与存档

使用标准库 JSON 原子替换，不引入数据库、总线、通用 Controller 接口或后台 worker。
独立房间文件和按房间登记的 AI/claim 任务是真实的隔离边界；结束房间取消它自己的任务。
读快照不改变游戏 revision；仅官端活动续期写入 lease 元数据时也不改变游戏 revision。
接受动作后的推进由广播 finally 保证调度，取消调用者不能丢失推进；已有 claim 任务按当前 pending 集合识别窗口交接。
官端首次成员与 lease 在同一候选 Room 中一次落盘，不产生无凭据的半个席位。
单进程是明确上限；需要多副本时先迁移为一个事务型状态 Owner，不能共享文件后直接扩容。

## 官端语义

仅信任同容器 loopback + OpenAI Secure MCP Tunnel 的平台身份元数据。
客户端自报元数据不是公网鉴权。缺少平台身份、跨 owner、跨房间、过期 lease 均拒绝。
每间房当前最多一个官端椒椒席位；活跃 controller 保护 120 秒，仅同 owner 能在其失活后恢复并旋转 lease。
没有固定总陪玩时长，没有自动离席；只有明确 leave 撤销自己的访问。
工具回执携带最新 revision/cursor/last_event_id，成功提交后明确转到 wait。
平台终止 response 只终止正在执行的工具链，不能保证后来自动唤醒。

## 用户可见安全文案

新增身份、权限、邀请及失败文案使用 `mahjong.*` / `entertainment.mahjong_unavailable` message key。
本轮不定稿最终高风险承诺；普通房间/昵称/开始/邀请按钮可以直接使用中文。
