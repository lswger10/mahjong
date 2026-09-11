# 麻将当前状态

2026-09-11。独立麻将子应用，来源 `zorrofox/mahjong@bd3842b37bf80460f273472f6347329cc09d6b06`。
施工分支 `codex/mahjong-game-room`；主克隆 `D:/Workspace/mahjong`，工作树
`D:/Workspace/tidal-echo-next/.worktrees/mahjong`。`upstream` 只指向原作者仓库，没有配置可写的用户远端。

本轮是**本地实现与验证**，未推送、未合并、未部署云端、未连接真实 ChatGPT；没有付费模型请求。
代码和证据随本轮本地提交保存。保留施工分支用于后续审阅/发布，不删除上游历史。

## 已实现的用户行为

- 昵称创建房间、房间码/邀请链接加入；最多四席，仅首次开局前接纳新成员（局末也不接管旧 AI），满员明确拒绝，不跳到别的房间。
- HttpOnly Guest Cookie 对应服务端随机身份；昵称不参与授权。每条 HTTP/WS 都从身份推导房间和座位。
- 仅返回自己的手牌，包含结算之后；猜测玩家 ID、跨房间、伪造出牌者、过期 revision 均拒绝。
- 刷新/断线/关闭页面保留身份及座位；进程重启从独立房间存档恢复。Cookie 有效期 30 天，清除 Cookie 或换设备不提供账号恢复。
- 创建时可开关 Local AI 补空位；关闭时须四人入座再开始。不支持中途接管 AI，不自动把断线真人或官端席位变成 AI。
- 单人退出撤销自己的访问，保留原座，原身份可重新加入；房主另有“结束房间”。退出后轮到该席位会等待其归来，既有吃碰胡响应仍有 30 秒时限。
- 官端椒椒使用独立 Mahjong MCP：`join_table/read_turn/wait_for_event/submit_action/leave_table`。邀请入座后与真人及 Local AI 同桌；不复用斗地主 lease。
- 各工具均写明下一跳。成功出牌继续 wait，同一活跃 response 不设人为总时长；平台取消、局末、等待超时不自动离席。没有 finished-response 后台唤醒。

## 组件状态

| 组件 | 代码与分支 | 本轮验证 | 部署状态 |
|---|---|---|---|
| Mahjong | 本分支；保留上游规则、AI、牌面与主要 UI | Python、前端、实际浏览器与 MCP HTTP/TCP，见 TEST_MATRIX | 未部署 |
| Tidal Web | `feat/gateway-model-execution-cache`，基线 `9b523c5` | 娱乐室麻将卡片、iframe 进入/返回；前缀代理浏览器验证 | 本地待发布；必须先部署麻将服务 |
| 独立斗地主 | `codex/guest-rooms@5c75cb9` | 原 `npm test` 全套复跑通过 | 本轮未推送/部署；原线上版本未重查 |
| Relay / Orchestrator / Gateway / PostgreSQL | 未修改 | 本轮不验收这些核心 | 未操作 |

## Owner 与数据

`RoomManager` 独占房间、稳定 seat 顺序、真人成员、AI 开关、积分、牌局及官端 lease 摘要；
`GameState` 继续负责规则，`api/websocket.py` 继续负责游戏推进。新增 `api/access.py` 是 HTTP/WS
的身份边界，`api/official.py` 是官端协议边界，两者都调用同一裁判。

`MAHJONG_DATA_DIR/guests.json` 保存随机 Cookie 的 SHA-256 摘要和 Guest 身份；
`MAHJONG_DATA_DIR/rooms/<room-id>.json` 分房保存完整私有牌局及成员。写临时文件、fsync、原子替换；
官端首次成员与 lease 同一次提交；存档失败时房间冻结为 storage_error，恢复存储并重启后读取最后成功存档。
这些文件不是网页资源，不入 Git/镜像。单进程单事件循环运行，禁止多个 worker/副本共同写目录。

## 尚未完成的发布验收

1. 在用户名下建立/选择麻将远端并发布施工分支；当前只配置原作者 `upstream`，不得直接推上游。
2. 新建独立 TEST Mahjong 服务、持久卷及独立 Secure MCP Tunnel；隧道凭据只放安全配置。
3. 先确认新服务 DNS/健康，再发布 Tidal nginx/网页；模板的 `next-mahjong` 地址在发布前必须存在。
4. 实测 Zeabur nginx、HTTPS Cookie/Origin、普通 ChatGPT 连续陪玩、朋友公网邀请、三星实机。
5. 安全/权限/邀请错误目前使用 message key；最终产品文案尚未定稿。

原作者授权及第三方素材归属见 README。启动和发布配置也以 README 的本分支说明为准。
