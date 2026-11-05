---
name: travel-planner
description: 旅游攻略与出行规划 —— 按天数/预算/偏好生成每日行程、景点间高德地图导航路线(驾车/公交/步行)、目的地实时天气与未来3天预报、美食价格手册与省钱攻略, 并可查 12306 火车票余票。配套 `travel` / `train` 命令。Use when the user asks 旅游攻略、旅游计划、出行规划、行程安排、景点推荐、必去景点、省钱旅游、自由行攻略、几日游、怎么安排、哪些值得去、景点之间怎么走、公交/驾车路线、高德地图导航、查天气/天气预报/穿衣建议/紫外线、火车票/余票/12306/买票, or asks for a travel itinerary, directions between attractions, destination weather, or train ticket availability.
---

# 旅游攻略与出行规划

这台机器是 Omarchy 便携工具箱 U 盘,出行这块有两个命令:

| 命令 | 干什么 |
| --- | --- |
| `travel` | 旅游攻略 / 行程规划 / 高德导航 / 天气 / 美食价格 |
| `train` | 12306 火车票余票 |

> **支持城市**: 郴州、长沙、衡阳、上海、清远(含周边联游)
> **AMAP_KEY** 已经配在**本技能目录下的 `.env`** 里,脚本会自己读,不用手动 export。
> 要换成自己的 key,改那个文件即可(申请: https://lbs.amap.com/dev/key/app )。

---

## 一、信息收集(先问清楚再规划)

| 字段 | 说明 | 默认值 |
| --- | --- | --- |
| `dest_city` | 目的地城市 | — |
| `travel_days` | 出行天数 | — |
| `depart_date` | 出发日期 | 今天 |
| `budget_cny` | 总预算(元) | — |
| `travel_style` | 旅行风格(可多选): 文化/美食/自然/亲子/文艺 | 文化、美食 |
| `group_type` | solo / couple / family / friends | solo |
| `mobility` | 体力: high(4个/天) / mid(3个) / low(2个) | mid |
| `budget_level` | budget / mid / luxury | mid |
| `prefer_free` | 是否优先免费景点 | — |
| `avoid_crowded` | 是否避开高峰人流景点 | — |
| `include_disney` | 是否纳入迪士尼(需单独整天) | — |
| `origin_city` | 出发城市(影响交通建议) | — |

**缺的信息先问,别替用户假设**。只有天数和城市是硬性必需的,其他有合理默认值。

---

## 二、四种能力,怎么调

### 1. 生成行程

```bash
# 交互式(用户没给全信息时)
travel plan

# 按偏好 JSON 生成(信息齐了用这个)
travel plan --profile /tmp/profile.json --output /tmp/trip
```

`profile.json` 形状:

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

输出三个文件(在 `--output` 目录里):

| 文件 | 内容 |
| --- | --- |
| `travel_plan.json` | 完整行程(每日景点、时间、费用) |
| `travel_schema.sql` | 数据库建表 SQL(5 张表 + 索引) |
| `travel_api.py` | FastAPI 后端骨架(Pydantic 模型 + 路由) |

其他参数: `--sql-only`(只出 SQL)、`--interactive`。

### 2. 景点之间怎么走

```bash
travel nav --from 郴州西 --to 衡阳东 --mode driving   # 驾车
travel nav --from 橘子洲头 --to 岳麓山 --mode transit  # 公交(城内)
travel nav --from 外滩 --to 豫园 --mode walking       # 步行
travel nav --from A --to B --mode driving --city 长沙  # 公交查询指定城市
travel route --plan /tmp/trip/travel_plan.json          # 按行程批量规划路线
```

| `--mode` | 取值 |
| --- | --- |
| `driving` | 驾车(`--strategy 0` 速度优先 / `2` 距离优先) |
| `transit` | 公交/地铁(`--strategy 0` 最快捷 / `1` 最经济) |
| `walking` | 步行 |

> **注意**: 公交查询**必须给 `--city`**(填起点所在城市),不传会自动按起点推断,
> 但起点写得太泛时会兜底失败。

### 3. 天气

```bash
travel weather 郴州        # 实时 + 未来3天预报 + 生活指数(穿衣/紫外线/舒适度)
travel weather 上海
```

也可以只查实时:`python3 scripts/amap_nav.py --weather-live 郴州`。

**不支持历史天气** —— 高德只能查实时和未来预报。用户问"上周天气"要直说查不到。

### 4. 美食价格

```bash
travel price
```

采集五城食品价格,写到技能目录的 `data/` 下:

| 文件 | 内容 |
| --- | --- |
| `data/latest_prices.json` | 当天采集到的价格明细 |
| `data/latest_summary.md` | 人话摘要(给用户看这个) |
| `data/price_history.json` | 历史记录(保留 90 天) |

---

## 三、火车票(12306)

```bash
train 北京 上海                # 今天
train 北京 上海 2026-10-30     # 指定日期
train 北京 上海 明天           # 也支持 今天/后天/大后天/+3
train -g 北京 上海             # 只看高铁/城际(G/C)
train -d 北京 上海             # 只看动车(D)
train --json 北京 上海         # JSON 输出(给脚本用)
train --stations 北京          # 查车站名/车站码
```

- 筛车次:`-g` 高铁城际 / `-d` 动车 / `-t` 特快 / `-k` 快速 / `-z` 直达,可叠加;
- 预售期一般只到**今天起 15 天内**,超了会直接报错;
- **余票随时变**,要买票必须去 12306 官网/App 确认 —— 汇报时一定要带上这句。

---

## 四、直接调高德 API(需要精确控制时)

`travel` 命令覆盖不到的组合,直接打 API。key 从技能目录的 `.env` 读:

```bash
KEY=$(sed -n 's/^AMAP_KEY=//p' ~/.config/opencode/skills/travel-planner/.env | tail -1 | tr -d '"'"'"' \r')
```

| 用途 | 接口 |
| --- | --- |
| 地理编码(地名→经纬度) | `GET https://restapi.amap.com/v3/geocode/geo?key=&address=&city=` |
| 驾车路线 | `GET .../v3/direction/driving?origin=经度,纬度&destination=经度,纬度&strategy=0` |
| 公交路线 | `GET .../v3/direction/transit/integrated?origin=&destination=&city=&strategy=0` |
| 步行路线 | `GET .../v3/direction/walking?origin=&destination=` |
| 天气 | `GET .../v3/weather/weatherInfo?city=&extensions=all` |

**地理编码务必传 `city`** —— 不传会出现同名地点歧义,坐标全错,路线接口直接报 30001。

响应关键字段:

| 路线类型 | 关键路径 |
| --- | --- |
| 驾车/步行 | `route.paths[0].distance`(米) / `duration`(秒) |
| 公交 | `route.transits[0].duration`(秒) / `cost`(元) |

天气字段:`lives[0].weather` / `temperature` / `winddirection` / `humidity`,
`forecasts[0].casts[].dayweather` / `daytemp` / `nighttemp`,
`forecasts[0].index[].iname` / `detail`(生活指数)。

免费配额:个人开发者每日 5000 次。

---

## 五、规划逻辑(脚本内部就是这么算的)

### 景点评分

| 加分项 | 说明 |
| --- | --- |
| 基础优先级 | 必去指数 ★★★★★ 加 5 分 |
| 风格匹配 | 景点类别匹配用户风格 +2 分 |
| 标签匹配 | 标签含风格关键词 +1 分 |
| 亲子加分 | 带小孩时 category=亲子 +2 分 |
| 扣分项 | 需整天景点(迪士尼)、远郊景点(朱家角)扣出 |
| 预算限制 | budget 级别时高价景点扣 2 分 |

### 每天装几个景点

| 体力 | 每天上限 | 有效时间 |
| --- | --- | --- |
| high | 4 个 | 09:00–21:00(12h) |
| mid | 3 个 | 09:00–19:00(10h) |
| low | 2 个 | 10:00–18:00(8h) |

### 省钱保障

- 免费景点优先填充(五城都有大量免费/极低价景点,见 `references/cities_attractions.md`);
- 每日门票预算超了就自动替换成免费替代;
- 迪士尼/全天景点**单独安排**,不占用碎片时间;
- 餐饮按 4321 法则分配:住宿 30% / 门票 25% / 餐饮 25% / 交通 10% / 备用 10%。

---

## 六、五城景点省钱速查

### 郴州

| 景点 | 门票 | 类别 |
| --- | --- | --- |
| 东江湖 | ¥85 | 必去·自然 |
| 高椅岭 | ¥95 | 必去·丹霞 |
| 万华岩 | ¥47 | ⭐省钱·溶洞 |
| 板梁古村 | ¥35 | ⭐省钱·古村 |
| 苏仙岭 | **免费** | ⭐省钱·城市 |
| 裕后街 | **免费** | ⭐省钱·美食 |
| 白廊公路 | **免费** | ⭐省钱·拍照 |

### 长沙

| 景点 | 门票 | 类别 |
| --- | --- | --- |
| 橘子洲头 | **免费** | 必去·地标 |
| 岳麓山 | **免费** | 必去·山地 |
| 湖南省博物馆 | **免费**(需预约) | 必去·历史 |
| 太平老街 | **免费** | 必去·美食 |
| 岳麓书院 | ¥40 | 经典·文化 |
| 文和友 | **免费入场** | 网红打卡 |

### 衡阳

| 景点 | 门票 | 类别 |
| --- | --- | --- |
| 南岳衡山 | ¥80(中心景区) | 必去·名山 |
| 石鼓书院 | **免费** | 必去·历史 |
| 酃湖公园 | **免费** | ⭐省钱·城市公园 |
| 保卫里 | **免费** | ⭐省钱·文艺老街 |
| 回雁峰 | **免费** | ⭐省钱·城市公园 |
| 东洲岛 | **免费** | ⭐省钱·江心岛 |

### 上海

| 景点 | 门票 | 类别 |
| --- | --- | --- |
| 外滩 | **免费** | 必去·夜景 |
| 武康路 | **免费** | 必去·网红 |
| 田子坊 | **免费** | 必去·文艺 |
| 新天地 | **免费** | 必去·时尚 |
| 上海博物馆 | **免费**(需预约) | 必去·历史 |
| 豫园 | ¥40 | 经典·园林 |

---

## 七、参考文件索引

| 文件 | 内容 |
| --- | --- |
| `references/cities_attractions.md` | 五城景点库(门票、时长、省钱等级) |
| `references/food_guide.md` | 五城美食价格手册(必吃小吃、店铺、日均预算) |
| `references/xiaohongshu_all_cities.md` | 五城小红书推荐合集(88 篇,含避坑) |
| `references/xiaohongshu_qingyuan.md` | 小红书清远合集(17 篇,漂流/溶洞/民族文化/美食) |
| `references/money_saving.md` | 全链路省钱攻略(预算/时间/门票/餐饮/住宿/交通) |
| `references/amap_api.md` | 高德 Web API 参考(地理编码/驾车/公交/步行/天气) |
| `references/travel_schema.md` | 数据库表结构(5 张表 + 索引 + 示例) |
| `references/travel_api.md` | RESTful API 接口定义(6 个端点 + 错误码) |
| `scripts/generate_plan.py` | 行程规划器 |
| `scripts/amap_nav.py` | 高德客户端(路线 + 天气) |
| `scripts/food_price_scraper.py` | 美食价格采集 |

---

## 八、典型对话

**用户**: 我想去郴州玩3天,预算2500,带家人,主要看自然风光。
→ 1) 识别: dest_city=郴州, days=3, budget=2500, group_type=family, styles=[自然]
→ 2) 补问: 出发日期、孩子年龄(影响每天景点数)
→ 3) 从 `references/cities_attractions.md` 筛郴州景点,按评分 + 体力约束排序
→ 4) 组合: 东江湖(¥85)+高椅岭(¥95)+免费景点,3 日门票 ≤ ¥300
→ 5) 要天气就 `travel weather 郴州`

**用户**: 从橘子洲头到岳麓山怎么走最划算?
→ 1) 地理编码拿到两点经纬度(务必带 city=长沙)
→ 2) 公交路线接口,`strategy=1` 最经济
→ 3) 给出: 公交方案(含地铁换乘、耗时、费用)

**用户**: 明天去郴州,帮我看看天气。
→ 1) `travel weather 郴州`
→ 2) 实时 + 3 天预报 + 穿衣/紫外线/舒适度
→ 3) 根据预报给行程微调建议(暴雨天改期高椅岭)

**用户**: 郴州到衡阳明天还有票吗?
→ 1) `train 郴州 衡阳 明天`
→ 2) 汇报车次、出发/到达时间、余票
→ 3) **必须提醒**: 余票随时变,买票去 12306 确认

---

## 九、汇报给用户时

- 行程要给**按天分组**的清单,每项带**时间段 + 门票 + 大概耗时**;
- 被排除的景点要说明**为什么**(时间不够 / 超出预算 / 太远),别让用户以为漏了;
- 路线查询要给**距离 + 耗时 + 费用**,别只说"可以坐地铁";
- 天气查询给**穿衣建议**,不要只贴数字;
- 火车票**必须带上"余票随时变,以 12306 为准"**;
- 景点门票/开放时间会变,涉及预约的(博物馆、上海博物馆)提醒用户**提前预约**。
