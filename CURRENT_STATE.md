# 麻将当前状态

## 2026-10-12 小世界外观（本地、未推送/部署）

`14a7acf` 更新大厅、桌面、手牌操作、房间菜单与结算纸面风格，保留原牌规、
私牌/席位权限和 HTTP/WS。111 项前端测试及原真实浏览器链路通过，包含实际
出牌、手机刷新、进程重启恢复、房主重开与娱乐室返回；结算展示用合成 game_over
事件检查，不冒充完整真人牌局。以下旧 TEST 部署信息仍需发布前重新核验。

2026-09-11。独立麻将子应用，来源 `zorrofox/mahjong@bd3842b37bf80460f273472f6347329cc09d6b06`。
施工分支 `codex/mahjong-game-room`；主克隆 `D:/Workspace/mahjong`，工作树
`D:/Workspace/tidal-echo-next/.worktrees/mahjong`。`upstream` 指向原作者仓库；`origin` 指向本轮创建的公开 Fork `lswger10/mahjong`。

TEST 代码 `53fcd8a` 已推送用户 Fork 的 `codex/mahjong-game-room` 并部署；未合并 main。
2026-09-11 完成麻将网页、公网双浏览器和普通 ChatGPT 人工牌局验证；未调用付费供应商 API。

- TEST 项目：`6a79b1dbec01e16bfb336c60`，环境 `6a79b1db5f062718bc7b9024`。
- 新建 Mahjong 服务：`6aa407d16c9b434a99e0bbf5`，名称 `next-mahjong`，挂载 `mahjong-data` 到 `/data`。
- 已关联 GitHub App 的 `lswger10/mahjong:codex/mahjong-game-room`，移除 Arbitrary Git 来源；容器定义与 b236471 一致。最终部署 `6aa413c6c105f1543504cbd0`，代码 `53fcd8a`，游戏健康接口和隧道 readyz 均通过。
- `/data` 持久卷已从容器 df 核验；私有 DNS 显式设为 `next-mahjong`，实际 Web 容器访问 `http://next-mahjong.zeabur.internal:8080/healthz` 成功。3 个人工验收房间已明确结束，存档保留；误建重复服务经用户明确授权删除，保留本服务和卷。
- 独立隧道 `tunnel_6aa4085c5ae48191a6a00b01b6818c32` 已配置；用户在安全界面填写仅 Tunnels Read+Use 的运行密钥，未读取运行密钥。已修复启动先后与缺失 OAuth 路径错误返回 405 的问题；客户端初始化、轮询和 readyz 通过。
- ChatGPT 应用 `asdk_app_6aa41494c958819192fbfc7f4b38a0ce` 已创建连接，发现全部 5 个工具。普通 ChatGPT 只发一次邀请后保持同一回复，多次 wait/read/act，官端席位实际弃牌 4 次；公开弃牌计数为 `[3,4,2,4]`、revision 53。点击停止回答后 revision 与席位不变、official_left=false；之后房主显式关闭人工房间，revision 54、closed。
- 验收期间 ChatGPT 出现工具许可/安全检查暂停，使用仅本次人工对话的许可后继续；未设置全局始终允许。不能承诺平台永不拦截、无限 response 或结束回复后自动唤醒。
- 实际 Web pod 为 10.42.0.66，所属路由 10.42.0.0/24；`FORWARDED_ALLOW_IPS=127.0.0.1,10.42.0.0/24`。服务仍为单副本；有限崩溃重启次数设为 5。
- 用户已完成 GitHub 重新身份确认与麻将仓库授权，Zeabur 仓库列表和已保存分支均已核验。
- Web 已发布麻将入口和代理，Tidal 推送也触发同分支服务部署；未修改核心聊天代码。麻将步骤没有迁移旧斗地主；后续斗地主发布状态见下表。
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
| Mahjong | `codex/mahjong-game-room@53fcd8a` | 本地回归、公网双 Edge HTTP/WSS、普通 ChatGPT 人工陪玩 | TEST 已部署并验证 |
| Tidal Web | `feat/gateway-model-execution-cache@1ee5fd4` | 保留麻将代理，开放已迁移斗地主 Guest 路径，SW v37；两种游戏公网健康 200 | TEST 部署 6aa420ccc105f1543504cce1 |
| 独立斗地主 | `codex/guest-rooms@e1b2b7c` | 原完整回归、房主迁移、公开双浏览器/双房间验收通过 | TEST 已部署；细节归其 CURRENT_STATE / TEST_MATRIX |
| Relay / Orchestrator / Gateway / PostgreSQL | 核心代码未修改 | Relay 公网健康 200；本轮不做聊天/记忆验收 | Relay 随 Tidal 推送部署且 Running；其余部署版本不据此推断 |

## Owner 与数据

`RoomManager` 独占房间、稳定 seat 顺序、真人成员、AI 开关、积分、牌局及官端 lease 摘要；
`GameState` 继续负责规则，`api/websocket.py` 继续负责游戏推进。新增 `api/access.py` 是 HTTP/WS
的身份边界，`api/official.py` 是官端协议边界，两者都调用同一裁判。

`MAHJONG_DATA_DIR/guests.json` 保存随机 Cookie 的 SHA-256 摘要和 Guest 身份；
`MAHJONG_DATA_DIR/rooms/<room-id>.json` 分房保存完整私有牌局及成员。写临时文件、fsync、原子替换；
官端首次成员与 lease 同一次提交；存档失败时房间冻结为 storage_error，恢复存储并重启后读取最后成功存档。
这些文件不是网页资源，不入 Git/镜像。单进程单事件循环运行，禁止多个 worker/副本共同写目录。

## 剩余边界

1. 三星实机尚未验证；已通过 412px 手机视口的独立 Edge 测试，不等同真机。
2. 斗地主多人 Phase 1 已在后续独立步骤部署：确认大厅无官端占座后备份、绑定原房主，再开放朋友入口。不得用麻将文档复制管理它的房间/席位真相。
3. 安全/权限/邀请错误仍使用 message key；最终产品文案尚未定稿。
4. 此次文档收尾与已部署代码分开提交；不为文档更新重启正在使用的服务。

原作者授权及第三方素材归属见 README。启动和发布配置也以 README 的本分支说明为准。
