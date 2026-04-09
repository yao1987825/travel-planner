---
name: travel-planner
description: >
  个性化旅游攻略自动规划 Skill。根据用户具体情况（天数、预算、偏好、体力、出发日期），
  自动生成每日行程安排，输出景点间高德地图导航路线（含驾车/公交/步行）、
  目的地天气预报（实时+未来3天+生活指数），并可选生成旅游系统数据库 SQL、
  RESTful API 定义、FastAPI 后端代码骨架。支持郴州、长沙、衡阳、上海四城（含美食价格手册）
read-when: >
  旅游攻略、旅游计划、出行规划、行程安排、景点推荐、必去景点、
  省钱旅游、自由行攻略、几日游、怎么安排、哪些值得去、哪些可以跳过、
  景点之间怎么走、交通方式、公交/驾车路线、高德地图导航、
  查询天气、出发前看天气、穿衣建议、紫外线指数
metadata: >
  {"openclaw":{"os":["linux","darwin","win32"],"requires":{"env":["AMAP_KEY"]},"note":"本 Skill 不执行脚本，所有功能通过 AI 直接调用 HTTP API 完成"}}
---

# Travel Planner Skill — 个性化旅游攻略自动规划

## 一、Skill 能力概览

本 Skill 在用户描述旅游需求时，**自动完成**以下全部工作：

| 输出类型 | 说明 |
|---------|------|
| 📅 **个性化行程** | 根据天数/预算/风格/体力，筛选景点并按天分组 |
| ⏭ **跳过说明** | 告知哪些景点因时间/偏好未纳入，及原因 |
| 💰 **省钱攻略** | 预算分配、免费景点推荐、门票优惠技巧 |
| 🗺️ **导航路线** | 高德地图 API 查询景点间最优路线（驾车/公交/步行） |
| 🌤️ **天气预报** | 高德天气 API，出发前查目的地实时+3天预报+穿衣/紫外线/舒适度指数 |
| 🗄 **数据库 SQL** | 5张核心表 DDL（含索引） |
| 🔌 **RESTful API** | 6个接口完整定义 |
| ⚡ **FastAPI 代码** | Pydantic 模型 + 路由骨架 |

---

## 二、支持城市

郴州、长沙、衡阳、上海（含周边联游）

---

## 三、信息收集

### 必收字段（缺一不可）

| 字段 | 说明 | 默认值 |
|------|------|--------|
| `dest_city` | 目的地城市 | — |
| `travel_days` | 出行天数 | — |
| `depart_date` | 出发日期 | 今天 |
| `budget_cny` | 总预算（元） | — |
| `travel_style` | 旅行风格（可多选） | 文化、美食 |
| `group_type` | 出行类型：solo/couple/family/friends | solo |
| `mobility` | 体力：high(4景点/天)/mid(3景点)/low(2景点) | mid |

### 可选字段（提升精细度）

| 字段 | 说明 |
|------|------|
| `budget_level` | budget / mid / luxury |
| `prefer_free` | 是否优先选择免费景点 |
| `avoid_crowded` | 是否避开高峰人流景点 |
| `include_disney` | 是否纳入迪士尼（需单独整天） |
| `origin_city` | 出发城市（影响交通建议） |
| `need_navi` | 是否需要景点间高德导航 |
| `need_weather` | 是否需要查目的地天气 |

---

## 四、执行步骤

### Step 1：收集信息，组装 profile

```json
{
  "dest_city": "上海",
  "travel_days": 3,
  "budget_cny": 3000,
  "budget_level": "mid",
  "depart_date": "2026-05-01",
  "travel_style": ["文化", "美食"],
  "group_type": "couple",
  "mobility": "mid",
  "need_navi": false,
  "need_weather": true
}
```

### Step 2：规划行程

```bash
python scripts/generate_plan.py --profile profile.json --output ./output
```

输出：
- `travel_plan.json` — 完整行程（含每日景点、时间、费用）
- `travel_schema.sql` — 数据库建表 SQL
- `travel_api.py` — FastAPI 代码骨架

### Step 3：天气预报（直接调用 API）

当用户询问目的地天气时，**直接构造 HTTP 请求**调用高德天气 API，不需要运行任何脚本。

#### 实时 + 未来3天 + 生活指数

```
GET https://restapi.amap.com/v3/weather/weatherInfo
  ?key={AMAP_KEY}
  &city=郴州
  &extensions=all
  &output=JSON
```

#### 仅实时天气

```
GET https://restapi.amap.com/v3/weather/weatherInfo
  ?key={AMAP_KEY}
  &city=郴州
  &extensions=base
  &output=JSON
```

#### 响应解析

| 字段路径 | 含义 |
|---------|------|
| `lives[0].weather` | 实时天气（如"多云"） |
| `lives[0].temperature` | 实时气温（如"26"） |
| `lives[0].winddirection` | 风向（如"东南"） |
| `lives[0].windpower` | 风力（如"≤3"） |
| `lives[0].humidity` | 湿度（如"74"） |
| `lives[0].report_time` | 数据更新时间 |
| `forecasts[0].casts[].date` | 预报日期 |
| `forecasts[0].casts[].dayweather` | 白天天气 |
| `forecasts[0].casts[].daytemp` | 白天最高温 |
| `forecasts[0].casts[].nighttemp` | 夜间最低温 |
| `forecasts[0].casts[].daywind` | 白天风向 |
| `forecasts[0].casts[].daypower` | 白天风力等级 |
| `forecasts[0].index[].iname` | 生活指数名称 |
| `forecasts[0].index[].detail` | 指数详情 |

#### 注意事项

- **不支持历史天气**：高德天气 API 只能查实时和未来预报，无法查询过去某一天的天气
- **城市名需准确**：使用城市中文全称，如"郴州""长沙""上海"
- **免费配额**：个人开发者每日 5000 次

### Step 4：导航规划（直接调用 API）

当用户询问景点间路线时，分两步：① 先调用地理编码 API 获取坐标，② 再调用路线规划 API。

#### 第一步：地理编码（地名 → 经纬度）

```
GET https://restapi.amap.com/v3/geocode/geo
  ?key={AMAP_KEY}
  &address=上海外滩
  &city=上海
```

响应中 `geocodes[0].location` 格式为 `经度,纬度`（如 `121.490,31.240`）。

#### 第二步：路线规划

**驾车路线**
```
GET https://restapi.amap.com/v3/direction/driving
  ?key={AMAP_KEY}
  &origin=121.490,31.240
  &destination=121.518,31.228
  &strategy=0        # 0=速度优先, 2=距离优先
  &extensions=base
```

**公交路线**（城内）
```
GET https://restapi.amap.com/v3/direction/transit/integrated
  ?key={AMAP_KEY}
  &origin=121.490,31.240
  &destination=121.518,31.228
  &city=上海
  &strategy=0        # 0=最快捷, 1=最经济
  &extensions=base
```

**步行路线**
```
GET https://restapi.amap.com/v3/direction/walking
  ?key={AMAP_KEY}
  &origin=121.490,31.240
  &destination=121.518,31.228
```

#### 响应解析

| 路线类型 | 关键路径 |
|---------|---------|
| 驾车 | `route.paths[0].distance`(m) / `duration`(s) |
| 公交 | `route.transits[0].duration`(s) / `cost`(元) |
| 步行 | `route.paths[0].distance`(m) / `duration`(s) |

#### 注意事项

- 地理编码时**务必传 city 参数**，否则同名地点会产生歧义
- 驾车策略 `strategy=0` 速度优先，`strategy=2` 距离优先
- 公交 `city` 参数填**起点所在城市**

---

## 五、核心规划逻辑

### 景点评分（决定去不去）

| 加分项 | 说明 |
|-------|------|
| 基础优先级 | 必去指数 ★★★★★ 加 5 分 |
| 风格匹配 | 景点类别匹配用户风格时加 2 分 |
| 标签匹配 | 标签含用户风格关键词时加 1 分 |
| 亲子加分 | 带小孩时 category=亲子 加 2 分 |
| **扣分项** | 需整天景点扣出（迪士尼）、远郊景点扣出（朱家角）|
| 预算限制 | budget 级别时高价景点扣 2 分 |

### 时间分配（决定去多少）

| 体力 | 每天景点上限 | 有效时间 |
|------|------------|---------|
| high | 4个 | 09:00–21:00（12h） |
| mid | 3个 | 09:00–19:00（10h） |
| low | 2个 | 10:00–18:00（8h） |

### 省钱保障

- **免费景点优先填充**：每个城市都有大量免费/极低价景点（详见 `references/cities_attractions.md`）
- **每日门票预算检查**：当日预估超过日均预算时，自动替换高价景点为免费替代
- **Disney/全天景点独立处理**：告知用户需单独安排，不占用碎片时间
- **餐饮分配**：预算按 4321 法则分配（住宿30%/门票25%/餐饮25%/交通10%/备用10%）

---

## 六、参考文件索引

| 文件 | 内容 |
|------|------|
| `references/cities_attractions.md` | 郴州/长沙/衡阳/上海四城景点数据库（含门票、时长、省钱等级） |
| `references/food_guide.md` | 四城美食价格手册（必吃小吃、推荐店铺、日均预算、省钱攻略） |
| `references/money_saving.md` | 全链路省钱攻略（预算分配、时间规划、门票/餐饮/住宿/交通） |
| `references/travel_schema.md` | 数据库表结构（5张表 + 索引 + 示例数据） |
| `references/travel_api.md` | RESTful API 接口定义（6个端点 + 错误码） |
| `references/amap_api.md` | 高德地图 Web API 参考（地理编码/驾车/公交/步行/天气） |
| `.env.example` | 环境变量示例（含 AMAP_KEY 配置说明） |

> ⚠️ **重要**：本 Skill **不通过脚本执行**。所有功能均通过 AI 直接调用 HTTP API 完成。
> `scripts/` 目录下的文件仅作参考实现，不作为执行入口。

---

## 七、五城景点省钱速查

### 郴州

| 景点 | 门票 | 类别 |
|------|------|------|
| 东江湖 | ¥85 | 必去·自然 |
| 高椅岭 | ¥95 | 必去·丹霞 |
| 万华岩 | ¥47 | ⭐省钱·溶洞 |
| 板梁古村 | ¥35 | ⭐省钱·古村 |
| 苏仙岭 | **免费** | ⭐省钱·城市 |
| 裕后街 | **免费** | ⭐省钱·美食 |
| 白廊公路 | **免费** | ⭐省钱·拍照 |

### 长沙

| 景点 | 门票 | 类别 |
|------|------|------|
| 橘子洲头 | **免费** | 必去·地标 |
| 岳麓山 | **免费** | 必去·山地 |
| 湖南省博物馆 | **免费**（需预约） | 必去·历史 |
| 太平老街 | **免费** | 必去·美食 |
| 岳麓书院 | ¥40 | 经典·文化 |
| 文和友 | **免费入场** | 网红打卡 |

### 衡阳

| 景点 | 门票 | 类别 |
|------|------|------|
| 南岳衡山 | ¥80（中心景区） | 必去·名山 |
| 石鼓书院 | **免费** | 必去·历史 |
| 酃湖公园 | **免费** | ⭐省钱·城市公园 |
| 保卫里 | **免费** | ⭐省钱·文艺老街 |
| 回雁峰 | **免费** | ⭐省钱·城市公园 |
| 东洲岛 | **免费** | ⭐省钱·江心岛 |

### 上海

| 景点 | 门票 | 类别 |
|------|------|------|
| 外滩 | **免费** | 必去·夜景 |
| 武康路 | **免费** | 必去·网红 |
| 田子坊 | **免费** | 必去·文艺 |
| 新天地 | **免费** | 必去·时尚 |
| 上海博物馆 | **免费**（需预约） | 必去·历史 |
| 豫园 | ¥40 | 经典·园林 |

---

## 八、典型对话示例

**用户**: 我想去郴州玩3天，预算2500元，带家人，5月出发，主要看自然风光，不知道怎么安排。

**处理流程**:
1. 识别：dest_city=郴州, days=3, budget=2500, group_type=family, styles=[自然]
2. 收集补充：出发日期、孩子年龄（影响景点数量）
3. 从 `references/cities_attractions.md` 中筛选郴州景点，按评分+体力约束排列
4. 推荐省钱组合：东江湖(¥85)+高椅岭(¥95)+免费景点组合，3日总门票≤¥300
5. 如用户需要天气：直接调用高德天气 API

**用户**: 帮我查下从橘子洲头到岳麓山怎么走最划算？

**处理流程**:
1. 识别：高德地图导航查询需求
2. 检查：AMAP_KEY 是否已在环境变量中配置
3. 调用地理编码 API：获取"橘子洲头"和"岳麓山"的经纬度
4. 调用公交路线 API（strategy=1 最经济模式）
5. 返回：公交方案（含地铁换乘说明、耗时、费用）

**用户**: 出发去郴州前，帮我看看那边天气怎么样？

**处理流程**:
1. 识别：天气预报查询需求（高德天气 API）
2. 调用高德天气 API（extensions=all），传入 city=郴州
3. 返回：实时天气 + 未来3天预报 + 穿衣指数/紫外线/舒适度
4. 额外建议：根据预报给出行程微调建议（如暴雨天改期高椅岭）
