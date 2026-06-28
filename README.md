# astrbot_plugin_twrpg_query

世界RPG（TWRPG）离线物品查询 AstrBot 插件。

## 用法

在群聊或私聊中发送（无需 `/` 前缀）：

```
世界 洞悉·真理之瞳
界 太阳石
```

插件会以图片卡片展示以下信息（有数据才显示对应区块）：

- **佩戴限定**：武器类型限定（通用/近战/远程/法杖/枪支/背包）及英雄专属效果
- **属性**：物品描述与数值
- **合成方式**：合成所需材料
- **可合成物品**：以该物品为材料的合成目标
- **来源**：BOSS 掉落（仅显示 BOSS 掉落，不含其他来源）

## 安装

```bash
cd AstrBot/data/plugins
git clone <本仓库地址> astrbot_plugin_twrpg_query
```

依赖：`Pillow`（安装插件时自动安装）

## 数据

插件自带 `data/twrpg_query/` 离线数据，来源于 `twrpg_data_tools/extracted_data/`。

更新数据时，将以下文件复制到 `data/twrpg_query/`：

- `items.json`
- `makes.json`
- `drops.json`
- `bosses.json`
- `heros.json`
- `exclusives.json`

## 开发调试

1. 将插件放入 `AstrBot/data/plugins/`
2. 启动 AstrBot
3. WebUI → 插件管理 → 重载插件
