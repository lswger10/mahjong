# 麻将测试矩阵

2026-09-11；Windows，Python 3.13.12，Node 24.17.0。全部人工身份/本地数据，0 次付费模型请求。
最终 Python 全套：419 passed / 1 skipped；前端：111 passed；pip check 无依赖冲突。

| 验证 | 证据 |
|---|---|
| 可选官端容器启动、失败联动退出与密钥不传裁判 | `bash scripts/test-container.sh`，本地 Git Bash 通过；真实镜像待云端构建 |
| 牌组、胡牌、计分、GameState、Local AI、RoomManager | 上游基础回归 307 passed / 1 skipped；规则文件未重写 |
| Guest、昵称与身份分离、自己手牌、跨身份/房间拒绝、刷新与 leave/end | `backend/tests/test_guest_rooms.py`，真实 FastAPI 路由和 WS |
| 局末拒绝新成员、错位绑定拒绝、存档失败不授予访问 | `backend/tests/test_guest_rooms.py` |
| 官端 join/read/wait/submit、重复出牌、最新 cursor、取消不离席、抢占与身份拒绝 | `backend/tests/test_official.py`，实际 MCP HTTP 编解码；平台元数据是人工 fixture |
| 出牌广播期间取消仍推进、官端成员和 lease 一次落盘 | `backend/tests/test_official.py` |
| 碰牌后立即弃牌、新旧响应窗交接及旧窗超时重叠、跨房间广播隔离 | 同上，真实规则/AI；不增加牌局旁路 |
| 三个对手回合与官端再次出牌 | 同上，同一个调用链多次 wait/read/act；不等同普通 ChatGPT 的模型行为验收 |
| Guest 与独立房间文件重启恢复 | 同上，重新构造 Guests/RoomManager 后比对牌局 |
| 两个 Local AI 房间自然结算、积分守恒、关闭不复活 | 同上，只缩短测试里的动画/claim 等待，不改牌规 |
| 吃/碰/杠/胡、抢杠、花牌补牌、响应窗、结算幂等、重开、排序 | 原 `tests/integration/`，更新为 server session 和 revision 协议；原覆盖继续保留 |
| 原生前端工具函数/排序/牌面/展示 | `npm test`，111 项 |
| 双独立浏览器、手机宽度、私牌、实际点击出牌、房主重开权限、刷新及进程重启 | `node tests/browser.mjs`，无头 Edge，真实本地 HTTP/WS；未用真人聊天 |
| 公网游戏端口不提供 MCP、私有 TCP MCP 拒绝 Origin、官端真实工具入座 | 同一浏览器回归的 TCP 检查 |
| 小家娱乐室进入/返回麻将 | 同一浏览器回归，设置 `TIDAL_WEB_ROOT`；标准库测试代理验证路径，不能替代真实 nginx 部署 |
| Tidal 缓存绕过与娱乐室登录边界 | `test_service_worker_push.py` + 娱乐室 session 用例，10 passed |
| 斗地主未退化 | `codex/guest-rooms@5c75cb9` 的 `npm test` 全套复跑通过，无代码修改 |

## 重跑

```powershell
.\.venv\Scripts\python -m pip install -r backend/requirements.txt -r backend/requirements-test.txt
.\.venv\Scripts\python -m pip check
.\.venv\Scripts\python -m pytest backend/tests tests/integration -q -o addopts=
npm ci --ignore-scripts
npm test
# PLAYWRIGHT_MODULE 指向已安装 Playwright 的 index.mjs；不新增生产浏览器依赖。
# 可选 TIDAL_WEB_ROOT 指向待验收的小家 web 目录。
node tests/browser.mjs
```

根 `conftest.py` 强制测试使用自己的 TemporaryDirectory；浏览器测试只启动/停止自己的 Python 子进程，
并核对其临时目录边界再删除。不会读取应用 data、调用云模型或操作用户正在玩的房间。

未验收：普通 ChatGPT、Secure MCP Tunnel 上云、朋友跨公网邀请、真实 nginx/TLS、三星实机、容器构建与多副本。
仓库原来已有一个 skipped 基础测试，本轮没有新增跳过或放宽牌规断言。
