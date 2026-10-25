# 计划：等级排行榜 与 出货排行榜

> 状态：**暂不实现（2026-10-25 决定）**，本文件仅记录调研结论与后续实现方案，避免下次重新取证。
> 相关版本：调研时插件为 v1.6.0（含 `世界在线`），后端 `TWRPGCloudBackend` 最新提交 `92b61a4`（2.3.0）。

## 一、需求原文

- **等级排行榜**：只看前十，展示云存档昵称 + 等级。
- **出货排行榜**：统计当月出货总数，以及每个阶段分别多少。

## 二、取证结论总览

| 需求 | 现在能否读取 | 说明 |
|------|--------------|------|
| 等级排行榜（全服 Top10） | ❌ 不能 | 后端没有任何排行榜端点；唯一能看别人的接口是 `/api/admin/online-users`，需管理员白名单且**不含等级字段** |
| 等级排行榜（近 7 天聊天近似） | ⚠️ 变通可行 | `GET /api/chat/messages` 的每条消息带 `nickname` + `level`，但只保留 7 天、单页 ≤100 条、只覆盖发过言的人 |
| 出货排行榜（个人） | ✅ 可读 | `GET /api/save-timeline?limit=2000`，条目含 `time` + `structuredItems[{itemId,name,delta}]`，itemId 可查本地 `items.json` 得到阶段 |
| 出货排行榜（全服） | ❌ 不能 | timeline 按 `userId` 分文件存储，`SaveTimelineService.list()` 只读自己那份，无跨用户聚合端点 |

## 三、后端取证细节

根目录：`H:\Hermes Project\TWRPGReader_beta\TWRPGCloudBackend\src\main\java\com\twrpg\cloud\`

### 3.1 没有任何排行榜端点

12 个 Controller 全量核对过（`AdminController`、`AuthController`、`ChatController`、`HealthController`、`ItemGoalsController`、`ReplaysController`、`SavesController`、`SaveTimelineController`、`ShareController`、`SoftwareSettingsController`、`StorageController`、`UpdateController`），无 `leaderboard` / `rank` / `ranking` 相关映射。

### 3.2 等级数据的存放与计算

- `entity/User.java`：`totalOnlineSeconds`（每 5 分钟心跳累加）、`bonusXpSeconds`（每日前 3 条聊天各 +8400 秒）、`nickname`、`status`。
- `util/ExperienceRules.java`：

```java
public static final int MAX_LEVEL = 109;
public static final double LEVEL_BASE = 1_800_000.0 / 5050.0;

public static int computeLevel(long totalXp) {
    if (totalXp <= 0) return 1;
    int level = (int) Math.floor((-1 + Math.sqrt(1 + 8.0 * totalXp / LEVEL_BASE)) / 2);
    return Math.max(1, Math.min(MAX_LEVEL, level));
}
```

- `AuthService`：`int totalXp = totalOnlineSeconds + bonusXpSeconds; int level = ChatService.computeLevel(totalXp);`

即等级是纯函数，可由 SQL 排序后计算，不需要额外存储。

### 3.3 唯一"能看到别人"的接口不可用

`controller/AdminController.java`：

```java
@GetMapping("/online-users")            // /api/admin/online-users
if (!adminWhitelistService.isAdmin(username)) return 403;
return Map.of("users", onlinePresenceService.listOnlineUsers(), "count", ...);
```

`OnlineUserDto` 字段只有 `username / ip / currentSaveName`，**无 level**，且需管理员白名单。

### 3.4 聊天记录（近似榜的唯一数据源）

`controller/ChatController.java` → `GET /api/chat/messages?limit=&beforeId=`（任何已登录用户可读）

`ChatMessageDto`：`id, userId, nickname, message, profession, stage, totalOnlineSecondsAtSend, createdAt, level`

`ChatService.getMessages` 用**用户表当前昵称**覆盖 `nickname`（改名后历史消息同步变），`level` 为发送时快照。

限制：

| 限制 | 值 / 出处 |
|------|-----------|
| 单页条数 | `limit` 必须 1..100，否则回落 `DEFAULT_PAGE_SIZE` |
| 记录保留 | 仅 7 天，`@Scheduled(cron = "0 0 2 * * ?")` 清理 |
| 覆盖人群 | 只有设置过昵称且发过言的账号 |
| 时效 | `level` 是发送时快照，玩家停止发言后不再更新 |

### 3.5 存档变更记录（出货统计的数据源）

`controller/SaveTimelineController.java`（`@RequestMapping(ApiPaths.SAVE_TIMELINE)`，即 `/api/save-timeline`）：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/save-timeline?saveName=&limit=` | `limit` 服务端钳制 1..2000，倒序返回（最新在前）；`saveName` 可选 |
| POST | `/api/save-timeline` | 读档器上报，`MAX_ITEMS = 20` |
| PATCH | `/api/save-timeline/{recordId}/replay` | 关联录像 |
| DELETE | `/api/save-timeline` | 清空 |

`SaveTimelineEntryDto`：`time, saveName, mode, replaySaved, items[], recordId, job, gameVersion, structuredItems[], localReplayPath, cloudReplayPath, replayUploadState`

`TimelineItemChangeDto`：`itemId, name, delta, oldQuantity, newQuantity, source`

`SaveTimelineService`（`service/SaveTimelineService.java`）关键点：

- 文件路径 `timelineFile(userId)` → `CloudUserPathService.getSaveChangesDir(userId)/save-timeline.log`，**按用户隔离**
- `list(Long userId, String saveName, int limit)` 只读当前用户文件 → 无全服聚合
- `schemaVersion >= 2` 写 JSON 行（带 `structuredItems`）；否则写 TSV（`time \t saveName \t mode \t replaySaved \t items`），`parseJson` 对 `< 2` 返回 null
- `time` 即 `occurredAt`，ISO_LOCAL_DATE_TIME（旧记录为 `yyyy-MM-dd HH:mm:ss`）

## 四、若实现：方案与工作量

### 4.1 等级排行榜

**方案 A —— 近似榜（零后端改动）**

- 新增 `CloudSyncClient.get_chat_messages(limit=100, before_id=None)` 调 `/api/chat/messages`
- 拉 N 页（建议 3~5 页，即 300~500 条），按 `userId` 去重取 `max(level)`，按等级倒序取前 10，输出 `昵称 LvN`
- 指令：`世界等级榜`（别名 `界等级榜`）；`priority=CLOUD_CMD_PRIORITY`，同时加进 `CLOUD_RESERVED_PREFIXES`
- 文案必须注明「统计自近 7 天聊天记录，只含发过言的玩家」
- 缺点：覆盖不全，可能凑不满 10 人；玩家改昵称后历史会跟随（这一行为反而有利）

**方案 B —— 精确榜（推荐，但需部署后端）**

- 后端新增：`controller/LeaderboardController.java`

```java
@RestController
@RequestMapping(ApiPaths.API + "/leaderboard")
public class LeaderboardController {
    @GetMapping("/level")
    public ResponseEntity<List<Map<String, Object>>> level(@RequestParam(defaultValue = "10") int limit) {
        // userRepository 按 (totalOnlineSeconds + bonusXpSeconds) DESC 取前 limit
        // nickname 为空的账号过滤或回落 username
        // 等级用 ExperienceRules.computeLevel(totalXp)
        // 只回 {"nickname": ..., "level": ...}，不暴露 username / ip / 在线时长
    }
}
```

- `UserRepository` 增加排序查询（`findTop10ByStatusOrderByTotalOnlineSecondsDesc` 之类，`bonusXpSeconds` 需在 SQL 里相加，建议用 `@Query`）
- `ApiPaths` 增加 `LEADERBOARD = API + "/leaderboard"`；SecurityConfig 无需改（`/api/**` 已要求 authenticated）
- 部署：`81.71.72.19:8080` 需重启生效
- 插件端：`get_level_leaderboard(limit=10)` + `世界等级榜` 指令，与方案 A 的指令一致

### 4.2 出货排行榜

**A. 个人版（建议先做，能验证数据质量）**

- `CloudSyncClient.get_save_timeline(limit=2000, save_name=None)` → 解析 `time/structuredItems`
- 新纯逻辑模块 `loot_stats.py`：

```
LootRecord(time, save_name, job, item_id, name, delta)
parse_timeline_entries(raw) -> list[LootRecord]
aggregate(records, *, month="2026-10", store) -> LootSummary
LootSummary { month, total_count, total_kinds, by_stage: {1..9: count}, top_items: [(name, count, stage)],
              by_save: [(save_name, count)], records, truncated }
```

- `item_id` → 阶段：`store.item_stage(item_id)`（已存在，返回 0..9），配合 `store.stage_label()` 输出 `四大 / 君主` 等
- 旧记录无 `structuredItems` 时按 `items` 名称回退（`store.resolve_item_by_name`）
- 指令：`世界出货 [YYYY-MM]`（默认当月），别名 `界出货`；`priority=CLOUD_CMD_PRIORITY`
- 渲染：新增 `loot_renderer.py`，复用 `card_renderer` 的 header/段落样式（标题 + 摘要三行 + 阶段条 + TopN 列表）

**B. 全服版（工作量大，暂不做）**

- 后端新增聚合端点，例如 `GET /api/leaderboard/loot?month=2026-10&stage=`，实现要点：遍历用户目录的 `save-timeline.log`、按月份与 `structuredItems.itemId` 聚合、结果缓存
- 需要处理：文件量大时的扫描开销、按阶段需要的 itemId→stage 映射（后端目前没有 items 数据，需引入或只按 itemId 返回让前端映射）

### 4.3 已知数据限制（会直接影响榜单质量）

| 限制 | 影响 |
|------|------|
| `MAX_ITEMS = 20` / 次 | 单局掉落超过 20 件时被截断 |
| `limit` 上限 2000 且无游标 | 重肝玩家单月记录可能读不全，无法翻页补齐 |
| `schemaVersion < 2` 无 itemId | 只能按名称回退匹配，可能匹配不到或误配 |
| 只有"新增"物品 | 材料消耗、兑换不入账，统计的是"进账"而非净变化 |
| 依赖读档器上传 | 未同步到云端的记录不在统计范围内 |
| 后端无 items 数据 | 阶段映射只能放在插件端（用自带 `items.json`） |

## 五、待确认事项 / 前置条件

1. **等级榜选 A 还是 B**：B 需要你确认可以修改并部署 `TWRPGCloudBackend`（含重启 `81.71.72.19:8080`）。
2. **出货榜范围**：先做个人版；全服版需要后端聚合，工作量与服务器开销都更大。
3. **数据质量验证**：做个人版之前，建议先用一个真实账号拉一次 `/api/save-timeline?limit=2000`，确认：
   - 是否有 `structuredItems`（即读档器已在传 `schemaVersion >= 2`）
   - 单月记录条数是否接近 2000 上限
   - `time` 格式是否统一
4. **排行口径**：出货按「件数」还是「次数」？是否合并同名物品？是否排除低阶段（粉末/小四）材料？

## 六、相关既有资产（实现时可直接复用）

- `core/cloud_client.py`：`_request_json` / `_AUTH_FAILURE_STATUSES`（401+403 都算登录过期）、`MSG_SESSION_EXPIRED`
- `core/cloud_service.py`：`_client_for(binding)`、`_pick_primary_save`、`online_status`（新增接口的写法模板）
- `core/cloud_commands.py`：`CLOUD_CMD_PRIORITY`、`CLOUD_RESERVED_PREFIXES`、`cloud_command_usage`
- `data_loader.py`：`item_stage` / `item_icon` / `stage_label` / `resolve_item_by_name`
- 渲染：`card_renderer.save_card_png`、`_draw_header`、`COLORS`；网格类统计可用 `inventory_renderer.generate_inventory_grid`
- 测试桩：`tests/test_cloud_online.py` 里的 `_install_astrbot_stub()` + `httpx.MockTransport` 模式
