# 律策智枢 LawPilot —— 设置面板精简与功能扩充设计文档

- 日期：2026-08-11
- 状态：设计定稿（使用者已批准，直接实施）
- 关联：上一份设计 `2026-08-10-multi-user-accounts-design.md`（多用户账号体系，本设计在其基础上扩充设置面板）

---

## 1. 背景与目标

### 1.1 现状

设置面板（`SettingsModal.vue`）当前只有两项功能：全局默认模型选择、每用户 API Key。
存在三个问题：

1. 说明文字过多（模型价格/能力说明、API Key 四行说明、底部 Auto 提示框），不够简洁；
2. API Key 输入框 placeholder「留空 = 使用服务端配置的 Key」不直观；
3. 功能太少：settings store 里 `enableNli`、`nConsistencySamples` 字段已有但无界面；
   账户管理（改密码、清数据）与系统信息缺失。

### 1.2 目标

- 删除三处说明文字，界面保持简洁；
- API Key 占位符改为 Key 形式（`sk-*******`）；
- 新增四个功能区块：问答偏好、账户（改密码/清空数据）、关于。

### 1.3 已确认约束

| 决策点 | 结论 |
|---|---|
| 新增功能 | 修改密码、问答偏好（NLI/采样数）、清空全部个人数据、关于/系统信息（全选） |
| 清空范围 | 清会话/收藏/资料，**保留账号与 API Key** |
| 改密码安全 | 改密后吊销该用户其他设备的 Token（当前设备保持登录） |
| 布局 | 设置弹窗内分区（不新增路由页面），宽度 420→480px |

---

## 2. 后端设计（2 个新接口 + 2 个小改动）

### 2.1 `POST /api/auth/change-password` —— 修改密码

- 请求：`{token, old_password, new_password}`（沿用现有请求体风格）
- 逻辑：
  1. `session_manager.verify(token)` 取用户名，无效 → 401；
  2. `user_store.authenticate(username, old_password)`，失败 → 400「原密码错误」；
  3. `validate_password(new_password)`，过短 → 400「密码至少 6 位」；
  4. `user_store.change_password(username, new_password)`（重新哈希写入 users.json）；
  5. `session_manager.revoke_others(username, keep_token=token)`（吊销该用户其他 Token）。
- 返回：`{ok: true}`

### 2.2 `POST /api/user/clear` —— 清空全部个人数据

- 请求：`{token}`
- 逻辑：
  1. `session_manager.verify` 取用户名，无效 → 401；
  2. `user_data.clear_user_data(username)`：清空 sessions/favorites/profile，
     **保留 api_key 字段**（先读旧 profile 的 api_key，清空后写回）；
  3. 返回 `{ok: true}`
- 账号本身与注册表（users.json 的 api_key）不动。

### 2.3 `session_manager.py` 新增 `revoke_others(username, keep_token)`

- 遍历 Token 表，吊销 `username` 相同且 `token != keep_token` 的全部条目，落盘。
- 用途：改密码后踢掉其他设备；测试账号多端共存的场景仅此一处吊销。

### 2.4 `user_store.py` 新增 `change_password(username, new_password)`

- 生成新盐 + 哈希，更新 users.json。

### 2.5 `user_data.py` 新增 `clear_user_data(username)`

- 清空该用户数据文件的 sessions/favorites/profile，保留 profile.api_key（无则空）；
- 原子写；缓存同步更新。

---

## 3. 前端设计（`SettingsModal.vue` 分区重构）

### 3.1 布局（弹窗宽 480px，四个分区，分区标题 13px 加粗）

```
问答偏好
  引用核验（NLI）        [开关]    ← settings.enableNli
  自一致性采样次数       [2|3|5 下拉] ← settings.nConsistencySamples
模型与 API Key
  全局默认模型           [下拉]    （删除价格/能力说明小字）
  API Key               [sk-********]  （placeholder 改 Key 形式；删除四行说明）
账户
  修改密码               [按钮 → 展开表单：旧密码/新密码/确认新密码]
  清空全部个人数据        [红色危险按钮 → dialog.warning 二次确认]
关于
  当前账号 / 可用模型数 / 离线引擎状态 / 服务与法律库状态
```

### 3.2 删除的文字（三处）

1. 全局默认模型下方的 `currentDefault.price_tier；capabilities` 小字；
2. API Key 下方的四行说明（`n-text depth=3`）；
3. 底部灰色提示框（Auto 跟随说明）。

### 3.3 问答偏好

- NLI 开关：`n-switch` 绑定 `settings.enableNli`（已有字段，buildChatPayload 已透传）；
- 采样次数：`n-select` 三档（2/3/5）绑定 `settings.nConsistencySamples`。
- 零后端改动。

### 3.4 账户——修改密码

- 默认收起；点「修改密码」展开三输入框（旧密码/新密码/确认新密码）+ 提交/取消；
- 提交调 `api/auth.ts` 新增 `changePassword(token, oldPassword, newPassword)`；
- 成功 → toast 提示「密码已修改，其他设备的登录已失效」并收起表单；
- 失败 → toast 显示后端中文 detail。

### 3.5 账户——清空全部个人数据

- 红色危险按钮；点击 → `dialog.warning` 二次确认（内容注明保留账号与 API Key）；
- 确认后调 `api/user.ts` 新增 `clearUserData(token)`（后端已清空服务端数据）；
- 成功 → 仅清空本地数据 state：`sessions.$reset()` + `favorites.$reset()` +
  `auth.updateProfile({displayName:'', bio:'', avatarColor:'', avatarData:null})`
  （**不调 auth.$reset()，否则会把用户登出**）；随后 useSync 的防抖 watcher 会把
  空状态再推一次服务端（幂等，无害）；
- 失败 → toast 提示，不动本地。

### 3.6 关于

- 当前账号显示名（auth store）；
- 可用模型数（models store apiModels.length）；
- 离线引擎状态（models.localEngine.available）；
- 服务/法律库状态：打开弹窗时调一次 `/api/health`，显示「服务正常 / 法律库已加载」或失败提示。

### 3.7 API 层

- `api/auth.ts`：新增 `changePassword(token, oldPassword, newPassword)`
- `api/user.ts`：新增 `clearUserData(token)`
- `api/types.ts`：无需新增类型（响应均 `{ok: true}`，可复用现有 `{ok: boolean}` 风格）

---

## 4. 错误处理

| 场景 | 行为 |
|---|---|
| 旧密码错误 | 400「原密码错误」，前端 toast 展示 |
| 新密码过短 | 400「密码至少 6 位」（前端同样预校验） |
| 改密后其他设备请求 | 401 → 前端跳登录页（预期行为） |
| 清空数据服务端失败 | toast 提示，本地数据不动 |
| `/api/health` 不可达 | 关于区块显示「无法获取」 |

## 5. 验证方式

1. 后端接口测试：改密成功/旧密码错/新密码短、改密后旧 token 失效、当前 token 有效；
   清空后 user/data 为空且 profile.api_key 保留；未登录 401。
2. 前端 `npm run build` 通过。
3. 服务端手工走查：设置面板四分区显示、三处文字已删、placeholder 为 `sk-*******`、
   改密流程、清空流程、关于信息显示。

## 6. 涉及文件清单

- **修改**：`web/backend/main.py`、`web/backend/schemas.py`（新增请求模型）、
  `web/backend/session_manager.py`、`web/backend/user_store.py`、`web/backend/user_data.py`、
  `web/frontend/src/components/common/SettingsModal.vue`、`web/frontend/src/api/auth.ts`、
  `web/frontend/src/api/user.ts`、`docs/修改日志.txt`
- **无需改动**：`api/types.ts`（无新类型）、聊天请求链（问答偏好字段已透传）
