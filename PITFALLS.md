# 麻将接续施工注意

- 上游 `GameState.to_dict(None)` 是内部全手牌调试接口，不能用于任何未知连接。公共传输只能经过已验证 member 的 `access.view`。
- 上游在结束时默认亮所有手牌；本分支传输层仍隐藏他人手牌。不要把恢复结果页当成绕过私有视角的理由。
- 上游 `/ws/{room}/{player_id}` 和 JSON `player_id` 协议已移除。不要为了旧测试添加兼容身份入口。
- `frontend/game.html` 内联函数覆盖 `game.js` 的部分渲染。昵称/手牌 UI 改动要同时检查两处。
- 每次状态推送可能刷新操作按钮；必须依据该快照的 `available_actions` 恢复吃碰胡按钮，不能只依赖一次性的 claim 通知。
- 旧 WebSocket 结束不能删除同座位的新连接。连接替换用对象身份比较，旧连接收到 4409 后停止重连。
- 独立房间的 AI/claim 任务必须登记；重开/关闭房间要取消旧任务。结算不得把已 closed 的房间重新标记 ended。
- 单文件存档不同于单一全局牌局；这里每个 room 一个文件。不要用多个 Uvicorn worker，共享目录也不提供多进程安全。
- MCP 私有端口和网页端口在同一进程内共享 RoomManager。另起一个 MCP Python 进程会制造第二个内存裁判。
- 120 秒是活跃控制器互斥保护，不是陪玩总时限。wait 每次最多 15 秒，不自动结束整条 response。
- 上游 README/CLAUDE 后半部分属于 bd3842b 历史说明，其中“无鉴权/纯内存/自动 AI 接管”不适用于本分支。
- Tidal nginx 新配置引用 `next-mahjong.zeabur.internal`。未先建好这个服务就发布 Web，nginx 可能因 DNS 解析失败启动不了；需从实际 Web 容器验证 DNS/健康。
- 测试的 Host/Origin、Cookie、前缀转发已在本地验证；尚未证明 Zeabur HTTPS 或普通 ChatGPT 实测通过。

- 局末不能新加入旧 AI 的索引；view 还必须校验 GameState player.id 与身份相符。首次开局以后只有原成员恢复。
- 一次出牌成功后，广播请求取消仍要推进。不要把必要调度仅放在网络 await 后面；正常帧顺序仍是 game_state → game_over。
- 碰/吃后立即弃牌会在旧 claim 的 100ms 等待间隙开新窗。必须识别既有 pending 集合的更换，旧窗不能吞掉新窗 AI 决策。
- 房主是唯一重开权限来源，不能再按“下一庄”禁用房主按钮；刷新不是修复权限 UI 的替代方法。
- 存档失败冻结当前房间，不继续暴露未落盘状态。首次官端入座成员和 lease 必须同一次落盘；分两次会留下僵尸席位。

- 浏览器验收不能假设“出牌后一定轮到下家”；AI 碰/杠会合法跳座。按实际私有快照等待稳定真人回合或自然结算。
- Zeabur SPA 的 Not Deployed/空日志可能滞后；先重新打开原服务核验，不要据此新建重复服务。Arbitrary Git 创建的服务可能没有 private DNS，必须显式检查。
- Zeabur Load from GitHub 曾加载旧 main Dockerfile；覆盖文件必须与实际施工分支比对，不能只信分支下拉框。
- tunnel-client 0.0.14 默认会立即做 OAuth 发现，早于 Python 私有监听启动时 readyz 可持续失败。使用客户端原生 `--mcp.startup-wait-timeout 30s` 等待；这是单次启动门槛，不是陪玩时长，也不引入 worker。
