# 法信通 LawTrust —— 多用户账号体系设计文档（阶段三 + 注册 + 每用户 API Key）

- 日期：2026-08-10
- 状态：设计定稿（使用者已批准，直接实施）
- 关联文档：`docs/项目改进指南.txt`（阶段三 服务端会话管理，v2.0）

---

## 1. 背景与目标

### 1.1 现状问题

1. **登出丢数据 + 需点两次**：`AppHeader.vue` 登出时 `sessions.$reset()` 立即清空并
   持久化（数据当场丢失）；`auth.logout()` 是异步的（先调后端接口才清登录态），
   `router.push('/login')` 同步执行先于登录态清除，路由守卫发现「仍登录」弹回聊天页，
   第二次点击才真正登出。
2. **数据全存浏览器 localStorage**：会话/收藏按用户名后缀隔离，但换设备/清缓存即丢失；
   个人资料存在全局 `lawtrust_auth_v2`（非按用户隔离）。
3. **Token 存内存字典**：服务重启即丢失、永不过期；无服务端数据接口。
4. **仅一个固定账号** `root/123456`（明文密码），无注册功能。
5. **API Key 仅服务端 `.env`**：`api_client.py` 构造函数已预留 `api_key` 覆盖参数
   （注释「后期前端传入用户自己的 Key 时用」），但模型调用链尚未透传。

### 1.2 目标

- 修复登出 bug：一次点击登出，**不丢数据**；数据存服务端，换设备/清缓存可恢复。
- 按改进指南「阶段三」落地服务端会话管理：Token TTL + JSON 持久化 + 数据读写接口。
- 新增用户名+密码注册；预置测试账号；每账号独立管理会话/收藏/资料。
- 每账号可配置自己的百炼 API Key；未配置时回退服务端 `.env` Key（root 天然如此）。

### 1.3 已确认约束（与使用者探讨确认）

| 决策点 | 结论 |
|---|---|
| 注册方式 | 用户名+密码（零外部依赖），预置测试账号 root/user1/user2（密码均 123456） |
| API Key 策略 | 账号未配置 → 回退服务端 `.env` Key；配置后该账号所有请求用自己的 Key |
| 同步范围 | 会话/收藏/资料/API Key 存服务端；主题、模型选择等设置留 localStorage |
| 多设备 | 多端共存（新登录不吊销旧 Token；适配测试人员公网共用场景） |
| 存储方案 | 方案 A：JSON 文件持久化（指南 3.1），不引入 SQLite/Redis |
| Token TTL | 24 小时，滑动续期（每次校验通过重置） |

---

## 2. 后端设计

### 2.1 新建 `web/backend/user_store.py` —— 用户注册表与密码安全

- 数据文件：`data/users/users.json`（**加入 .gitignore，不入库**）：
  ```json
  { "users": [
    { "username": "root", "password_hash": "...", "salt": "...",
      "display_name": "root", "api_key": null, "created_at": 1234567890 }
  ]}
  ```
- 密码哈希：`hashlib.pbkdf2_hmac("sha256", password, salt, 100_000)` + 每次注册生成
  随机 16 字节盐；`secrets.compare_digest` 恒时比对。零新依赖。
- 首次启动种子账号：`root/123456`、`user1/123456`、`user2/123456`（密码全部哈希存储）。
- 提供方法：`register(username, password, display_name)`（用户名规则校验：3-20 位
  字母/数字/下划线；密码 ≥ 6 位；重名抛 ValueError）、`authenticate(username, password)`
  → User 或 None、`get_user(username)`、`update_api_key(username, api_key)`。
- 内存缓存 + 原子写（tmp + rename）；JSON 损坏回退空表。

### 2.2 新建 `web/backend/session_manager.py` —— Token 会话管理（指南 3.1）

- Token：`secrets.token_urlsafe(32)`；记录 `{token: {username, expires_at}}`。
- TTL 24 小时（`Config.SESSION_TTL_SEC`，放 `src/config.py`）；每次 `verify` 通过自动续期。
- **多端共存**：不吊销旧 Token。
- Token 表持久化 `data/users/tokens.json`，服务启动时加载并清理过期项。
- 提供：`create(username) -> token`、`verify(token) -> Optional[str]`（返回 username，滑动续期）、
  `revoke(token)`。
- 内存缓存 + 原子写；损坏回退空表。

### 2.3 用户数据文件与读写接口（指南 3.2）

- 每用户一条 `data/users/{username}.json`：`{"sessions": [...], "favorites": [...], "profile": {...}}`
  （结构与前端完全一致，零转换）。
- 写盘原子写；内存按用户名缓存减少磁盘读写；损坏回退空数据。
- 接口（均 Token 鉴权，无效 401；统一从 `Authorization` 之外的请求体/查询参数取 token——
  本设计遵循现有「token 放请求体」的风格，聊天请求体也带 token）：

| 接口 | 说明 |
|---|---|
| `GET /api/user/data` | 返回该用户 `{sessions, favorites}`（文件不存在 → 空数据 + `exists: false` 标记） |
| `PUT /api/user/data` | 整包保存 `{sessions, favorites}` |
| `GET /api/user/profile` | 返回 `{display_name, bio, avatar_color, avatar_data, api_key}` |
| `PUT /api/user/profile` | 保存资料 + api_key |

- 资料与数据分开两个文件字段/接口：会话频繁保存不覆盖资料，避免并发互踩。

### 2.4 认证接口改造（`main.py`）

- `POST /api/auth/register`：新 schema `RegisterRequest{username, password}`；
  校验用户名规则与重名（409「用户名已被注册」）；成功后自动登录（直接发 token）。
- `POST /api/auth/login`：改为查 `user_store.authenticate`（哈希比对）；登录失败 401。
- `POST /api/auth/verify`：改查 `session_manager.verify`；返回 `valid/username/display_name`。
- `POST /api/auth/logout`：`session_manager.revoke(token)`。
- 删除内存 `_AUTH_USERS` 与 `_active_tokens`。

### 2.5 每用户 API Key 透传链路（核心新增）

- `ChatRequest` / `ChatStreamRequest` 增加可选 `token` 字段（沿用前端现有请求体风格）。
- `main.py` 解析：token → `session_manager.verify` → `user_store.get_user().api_key`；
  token 缺失/无效 → `api_key = None`（回退服务端 `.env`）。**不强制鉴权**（指南 3.4
  预留能力，答辩可讲；带 token 只为选对 Key）。
- 传递链（新增可选参数 `api_key: Optional[str] = None`，全部默认 None 向后兼容）：
  - `main.py chat/chat_stream` → `pipeline.run / run_fast / run_verification`
  - `answer_pipeline.py`：run/run_fast/run_verification 及内部各分支（`_run_non_legal`、
    `_run_contract_guidance`、`_run_validity`、主问答、`generate_answer_stream`）→
    `model.generate / generate_stream / generate_stream_messages / complete_with_tools`
  - `self_consistency.py check()`：接受 `api_key`，透传 `model.generate`（自一致性核验
    沿用所选 Key）
  - `verification_worker.run_verification_task`：新增 `api_key` 参数，透传
    `pipeline.run_verification`（异步 WS 核验沿用同一 Key）
- `qwen_model.py`：
  - `_get_api_client(spec, api_key)`：缓存键从 `base_url` 改为 `(base_url, api_key)`，
    构造 `APIClient(base_url=..., api_key=...)`（api_key 为 None 时 APIClient 内部
    回退环境变量——并发请求不串 Key）
  - `generate / generate_stream / generate_stream_messages / complete_with_tools /
    complete_stream_with_tools` 增加 `api_key` 参数并透传
- `src/config.py`：新增 `SESSION_TTL_SEC = 86400`；`USER_DATA_DIR` 指向
  `data/users/`（从 ROOT 解析）。

---

## 3. 前端设计

### 3.1 修复登出 bug（`AppHeader.vue`）

```js
await auth.logout()          // 先等登录态清完（含调后端吊销 Token）
router.push('/login')        // 再跳转
```
- 删除 `sessions.$reset()`——登出不再清数据；数据在服务端，重新登录恢复。
- 「清空对话记录」保留：清本地 + 同步清服务端（下一次防抖推送自然携带空列表）。

### 3.2 注册界面（`LoginView.vue`）

- 登录卡片增加「登录 / 注册」切换；注册表单：用户名/密码/确认密码（前端校验一致）。
- 注册成功自动登录（后端直接返回 token）→ 拉取/同步数据 → 进聊天页。
- 登录页底部提示测试账号：`root/123456`、`user1/123456`、`user2/123456`。
- 后端 409 冲突 → 前端显示「用户名已被注册」。

### 3.3 双写同步（新建 `composables/useSync.ts`）

- **登录后拉取**（`pull()`）：`GET /api/user/data` →
  - 返回 `exists: true` → 用服务端数据覆盖本地（`sessions.$hydrate` 等效赋值）并回写 localStorage
  - `exists: false`（首次登录该账号）→ 保留本地数据，并立即整包 `PUT` 回写服务端（老用户迁移）
  - 失败/不可达 → 降级用本地（不中断）
- **变更后推送**（`push()`）：watch sessions/favorites 状态，3 秒防抖后整包
  `PUT /api/user/data`；失败静默（记日志，下次变更再试），不阻塞界面。
- 资料/API Key 保存时 `PUT /api/user/profile`（设置面板直接调，不参与防抖）。
- 登出时停止 watch（清理计时器），避免登出后把空状态推上去。

### 3.4 设置面板 API Key（`SettingsModal.vue`）

- 新增「API Key（百炼）」输入框 + 说明文案：
  「留空 = 使用服务端配置的 Key（root 默认）；填写 = 本账号所有问答使用自己的 Key」。
- 保存 → `PUT /api/user/profile`；成功提示；失败提示（网络/401 跳登录页）。
- 已有资料弹窗（ProfileModal）不改。

### 3.5 API 层改动

- `api/types.ts`：`ChatRequest`/`ChatStreamRequest` 加 `token`；新增
  `RegisterRequest`/`RegisterResponse`、`UserDataResponse`、`UserProfileResponse/Request`。
- `api/auth.ts`：新增 `register()`。
- `api/chat.ts`：请求体带 `token`（登录后从 auth store 取；未登录不发）。
- 新增 `api/user.ts`：`fetchUserData / saveUserData / fetchProfile / saveProfile`。

---

## 4. 错误处理与降级

| 场景 | 行为 |
|---|---|
| Token 过期/无效 | 接口 401 → 前端跳登录页 |
| 用户 Key 无效/欠费 | 沿用现成中文报错「API Key 无效或已过期，请检查…」 |
| 服务端不可达 | localStorage 照常使用（降级不中断） |
| 数据 JSON 损坏 | 回退空数据/空表，不阻塞服务启动 |

## 5. 安全说明（竞赛级别）

- 密码 pbkdf2 + 盐哈希存储；Token 24h TTL；API Key 明文存服务端 JSON（文档注明
  「生产环境应加密存储或改读环境变量」）；「记住密码」明文存 localStorage 保持现状
  （测试阶段可接受，注释已标注）。

## 6. 兼容性

- 老用户本地已有会话/收藏：首次登录（服务端无该用户文件）→ 本地优先并回写服务端。
- 已清空过会话（服务端文件存在但空）→ 以服务端为准，避免旧数据复活。
- 旧 token 格式不兼容（重启后失效属预期，前端跳登录页）。

## 7. 验证方式

1. 后端接口 curl 验证：register 成功/重名/弱密码；login 成功/错误密码；verify 续期；
   logout 后 verify 失效；user/data 存取往返。
2. 前端 `npm run build` 通过（TS 类型检查）。
3. 启动服务手工验证：注册→问答；登出一次成功且数据不丢；重新登录恢复；
   换浏览器登录同账号恢复数据；设置面板填 Key 后请求成功、填错 Key 报中文错误；
   root 不填 Key 正常问答。

## 8. 涉及文件清单

- **新建**：`web/backend/user_store.py`、`web/backend/session_manager.py`、
  `web/frontend/src/api/user.ts`、`web/frontend/src/composables/useSync.ts`、
  `data/users/`（gitignore）
- **修改**：`web/backend/main.py`、`web/backend/schemas.py`、`web/backend/verification_worker.py`、
  `src/config.py`、`src/llm/qwen_model.py`、`src/llm/api_client.py`（如需要）、
  `src/pipeline/answer_pipeline.py`、`src/uncertainty/self_consistency.py`、
  `web/frontend/src/api/auth.ts`、`api/chat.ts`、`api/types.ts`、`views/LoginView.vue`、
  `components/layout/AppHeader.vue`、`components/common/SettingsModal.vue`、
  `stores/auth.ts`、`.gitignore`、`docs/法信通_LawTrust_项目介绍.txt`、
  `docs/修改日志.txt`、CLAUDE.md 进度表（阶段三状态）
