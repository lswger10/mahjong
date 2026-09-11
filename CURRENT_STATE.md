# 麻将当前状态

2026-09-11。独立麻将子应用，来源 `zorrofox/mahjong@bd3842b37bf80460f273472f6347329cc09d6b06`。
施工分支 `codex/mahjong-game-room`；主克隆 `D:/Workspace/mahjong`，工作树
`D:/Workspace/tidal-echo-next/.worktrees/mahjong`。`upstream` 指向原作者仓库；`origin` 指向本轮创建的公开 Fork `lswger10/mahjong`。

实现基线 `a1728df`，部署容器补充 `b236471`，均已推送用户 Fork 的 `codex/mahjong-game-room`；未合并。
用户已授权 TEST 发布。2026-09-11 发布进行中，尚未宣布上线；没有付费模型请求。

- TEST 项目：`6a79b1dbec01e16bfb336c60`，环境 `6a79b1db5f062718bc7b9024`。
- 新建 Mahjong 服务：`6aa407d16c9b434a99e0bbf5`，名称 `next-mahjong`，挂载 `mahjong-data` 到 `/data`。
- 已关联 GitHub App 的 `lswger10/mahjong:codex/mahjong-game-room`，移除 Arbitrary Git 来源；容器定义与 b236471 一致。9128584 对应部署 `6aa40b41c105f1543504cac1` 已实际运行，游戏健康接口通过。
- `/data` 持久卷已从容器 df 核验；私有 DNS 显式设为 `next-mahjong`，实际 Web 容器访问 `http://next-mahjong.zeabur.internal:8080/healthz` 成功。尚无真人房间；误建重复服务经用户明确授权删除，保留本服务和卷。
- 独立隧道 `tunnel_6aa4085c5ae48191a6a00b01b6818c32` 已配置；用户在安全界面填写仅 Tunnels Read+Use 的运行密钥，未读取密钥。日志确认已取到该隧道元数据，但首次 OAuth 发现早于私有 MCP 启动约 2 秒，readyz 失败；新增原生启动等待，待云端复验。
- 实际 Web pod 为 10.42.0.66，所属路由 10.42.0.0/24；`FORWARDED_ALLOW_IPS=127.0.0.1,10.42.0.0/24`。服务仍为单副本；有限崩溃重启次数设为 5。
- 用户已完成 GitHub 重新身份确认与麻将仓库授权，Zeabur 仓库列表和已保存分支均已核验。
- 旧斗地主、网页、Relay 和数据库没有被重启或改变流量。
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
| Mahjong | 本分支；保留上游规则、AI、牌面与主要 UI | Python、前端、实际浏览器与 MCP HTTP/TCP，见 TEST_MATRIX | TEST 9128584 运行；隧道启动顺序修复待发布 |
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

1. 发布隧道启动顺序修复并验证 readyz 与真实工具发现。
2. 游戏健康、持久卷和 Web 到麻将的私网访问已通过；仍须验证 HTTPS Cookie/WS。
3. 发布 Tidal nginx/网页；新服务 DNS/健康的前置门槛已通过。
4. 实测 Zeabur nginx、HTTPS Cookie/Origin、普通 ChatGPT 连续陪玩、朋友公网邀请、三星实机。
5. 安全/权限/邀请错误目前使用 message key；最终产品文案尚未定稿。

原作者授权及第三方素材归属见 README。启动和发布配置也以 README 的本分支说明为准。
