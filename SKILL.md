---
name: travel-planner
description: 旅游攻略与出行规划 + 公交实时查询 —— 按天数/预算/偏好生成每日行程、景点间高德地图导航路线(驾车/公交/步行)、目的地实时天气与未来3天预报、美食价格手册与省钱攻略、12306 火车票余票, 以及全国公交实时信息(某条线路车在哪、还有几站、几分钟到、某站有哪几路、起终点直达线路)。Use when the user asks 旅游攻略、旅游计划、出行规划、行程安排、景点推荐、省钱旅游、几日游、景点之间怎么走、公交/驾车路线、高德地图导航、查天气/天气预报/穿衣建议、火车票/余票/12306, 或问公交:几路车/有没有车/到哪了/还有几站/几分钟到/某站有哪几路/坐什么车/末班车/公交到站.
compatibility: "查实时公交需要能执行命令的环境(工具箱 U 盘,或 RikkaHub 工作区)。纯对话模式下仍可做行程规划、景点与美食推荐(读 references/),但查不了实时公交/天气/火车票。"
---

# 出行助手:旅游规划 + 公交实时

出行这件事分两块:**行程怎么安排**(去哪儿、吃什么、怎么走、天气如何),
和**到了当地怎么坐车**(几路车还有几分钟到)。这个技能两块都管。

---

## 0. 先判断你在哪个环境

两套环境,命令不同 —— **先确认,别瞎试**。

### 环境 A:工具箱 U 盘 / opencode(有 bash)

命令直接可用:

| 命令 | 干什么 |
| --- | --- |
| `travel` | 旅游攻略 / 行程规划 / 高德导航 / 天气 / 美食价格 |
| `train` | 12306 火车票余票 |
| `bus` | 公交实时车辆 / 到站预测 / 站点线路 / 直达线路 |

> `AMAP_KEY` 已经配在技能目录的 `.env` 里(`~/.config/opencode/skills/travel-planner/.env`),
> 脚本自己读,不用手动 export。

### 环境 B:RikkaHub / 手机工作区(只有 proot Linux)

工作区里没有 `bus`/`travel` 命令,但有 shell、python3 和网络 —— **跑同一个脚本**。

第一次用(或工作区是空的)先装:

```bash
# 1. 装依赖(工作区默认 apt;没装 git/python3 就装)
apt update && apt install -y git python3 python3-pip

# 2. 拉技能仓库(把 REPO 换成实际仓库地址)
git clone --depth 1 https://github.com/yao1987825/travel-planner.git

# 3. 高德 Key: 申请 https://lbs.amap.com/dev/key/app ,然后写进仓库根目录的 .env
echo 'AMAP_KEY=你的key' > travel-planner/.env

# 4. 自检
python3 travel-planner/scripts/bus_query.py lines 郴州 --limit 3
```

之后一律用:

```bash
python3 travel-planner/scripts/bus_query.py <子命令> [参数...]
```

> `bus_query.py` **只用 Python 标准库**, 不需要 pip 装任何东西。
> `amap_nav.py`(高德路线/天气)需要 `requests`:
> `pip install requests`。
> 没有工作区、也没有 shell 的纯聊天环境:见第 9 节「没有运行环境时能做什么」。

---

## 1. 公交实时查询

环境 A 用 `bus`,环境 B 用 `python3 .../bus_query.py` —— **子命令和参数完全一样**。
下面统一写成 `bus`,环境 B 把它换成 `python3 <仓库路径>/scripts/bus_query.py`。

| 用户说的 | 查法 | 命令 |
| --- | --- | --- |
| 「2 路有没有车」「到哪了」 | 按线路查实时车辆 | `bus live 郴州 2路` |
| 「到火车站还有几分钟」 | 按线路 + 目标站查**到站预测** | `bus live 郴州 2路 --to 湘南幼专` |
| 「五岭广场有几路车」 | 按站点查线路 | `bus station 郴州 五岭广场` |
| 「从五岭广场到火车站坐什么车」 | 查直达线路 + 方向 | `bus route 郴州 五岭广场 火车站` |
| 「郴州还有哪条线有车」 | 全城扫 | `bus scan 郴州 --limit 10` |
| 「有哪些线路」 | 列线路目录 | `bus lines 郴州` |

通用参数: `--src mygolbs|chelaile` 强制数据源, `--json` 输出原始 JSON, `--limit N` 限制条数。

### 标准作业流程

**第 1 步:识别城市** —— 脚本自己归一化:

- 「郴州」「郴州市」→ 郴州市
- 「桂阳」「桂阳县」→ 经 `references/districts.json` 映射到**郴州市**(公交归地级市管)
- 没写城市 → 默认郴州市
- 城市不在覆盖范围 → 脚本报「两个数据源都没覆盖」, **照实说没覆盖, 不要瞎编**

覆盖范围:掌上公交 **579** 城/县(`references/mygolbs_cities.json` 离线缓存),
车来了 **320** 城(`references/bus_cities.json` 有城市 ID)。

**第 2 步:识别查询类型** —— 对照上表。**不确定就问用户**。

**第 3 步:执行** —— `bus live 郴州 2路 --to 湘南幼专`

`--to` 是**关键**: 给了目标站才会去拿"还有几站 / 还有几分钟"的到站预测。

**第 4 步:组织回答**:

- **车牌、站名、分钟数、站数一律用接口返回的原值**, 不要自己换算
- 用户关心什么先说什么(问"还有几分钟"就先给分钟数)
- 没查到就**照实说没查到**, 不要编线路和车辆
- 「坐过去几分钟」是按里程/均速估算的, 说「约」

### 到站预测怎么来的(知道原理才不会用错)

掌上公交要**两跳**才能拿到"还有几站/几分钟":

1. `CMD=103` 拿线路站表 → 得到每个站的**站序**(`stationOrder`)
2. 用站序当 `STATIONORDER` 调 `CMD=104` → 返回 `routeOnStationRTimeInfoList`,
   里面有 `busToStationTime`(分钟)、`busToStationCount`(站数)、`busToStationDistance`(距离)

脚本已经自动串好这两跳, **你不用管**。但要知道:

- `--to` 的站名必须在该线路的站表里, 否则脚本报错并把前几个站名列出来 —— 那说明线路选错了
- 同一条线两个方向都有这个站时, 脚本默认选方向 1; 可以用 `--dir 2` 强制
- 每站最多给最近 2 辆车的预测

### 公交部分的注意事项

1. **一次查询只用一家数据源**:两家站名写法不一致,不合并站表。
   脚本默认掌上公交优先,掌上公交没覆盖的城市才退车来了。
2. **不做换乘规划**:`route` 只做直达线路求交集 + 按站序校验方向。
   用户要换乘方案就直说这个技能不支持,别硬凑。
3. **末班已开走**时要连带说首班时间(脚本会给出 `首班/末班`)。
4. **`hasReal=0`** 的城市(北京、上海、成都等)上游不给实时车辆位置,
   **不能当「没车」报**,要照实说「上游不给该城实时位置」。
5. **同名站有多个**(如「五岭广场」同名 4 个),脚本会列出全部,汇报时提一下让用户确认。
6. **距离为 0 通常是上游没给**,不是车就停在站口 —— 脚本显示「—」而不是「0米」。
7. 公交数据来自第三方源,**覆盖范围和实时性取决于对方**,提醒用户以实际站牌为准。

接口细节见 `references/bus_api.md`(按 2026-11-05 实测整理)。

---

## 2. 行程规划

### 信息收集(先问清楚再规划)

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

### 生成行程

环境 A:

```bash
travel plan                                   # 交互式
travel plan --profile /tmp/profile.json --output /tmp/trip
```

环境 B(工作区):

```bash
python3 travel-planner/scripts/generate_plan.py --profile profile.json --output ./trip
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

输出三个文件(在 `--output` 目录):`travel_plan.json`(完整行程)、
`travel_schema.sql`(5 张表建表 SQL)、`travel_api.py`(FastAPI 骨架)。
其他参数: `--sql-only`、`--interactive`。

### 景点之间怎么走

```bash
travel nav --from 郴州西 --to 衡阳东 --mode driving   # 驾车
travel nav --from 橘子洲头 --to 岳麓山 --mode transit  # 公交(城内)
travel nav --from 外滩 --to 豫园 --mode walking       # 步行
travel nav --from A --to B --mode driving --city 长沙  # 公交查询指定城市
travel route --plan /tmp/trip/travel_plan.json          # 按行程批量规划
```

工作区里换成 `python3 travel-planner/scripts/amap_nav.py --from ... --to ... --mode ...`。

| `--mode` | 取值 |
| --- | --- |
| `driving` | 驾车(`--strategy 0` 速度优先 / `2` 距离优先) |
| `transit` | 公交/地铁(`--strategy 0` 最快捷 / `1` 最经济) |
| `walking` | 步行 |

> **公交查询必须给 `--city`**(填起点所在城市),不传会自动按起点推断,
> 起点写得太泛时会兜底失败。

### 天气

```bash
travel weather 郴州        # 实时 + 未来3天预报 + 生活指数(穿衣/紫外线/舒适度)
```

**不支持历史天气** —— 高德只能查实时和未来预报。用户问"上周天气"要直说查不到。

### 美食价格

```bash
travel price
```

采集五城食品价格,写到技能目录的 `data/`:`latest_prices.json`(明细)、
`latest_summary.md`(人话摘要)、`price_history.json`(历史,保留 90 天)。

---

## 3. 火车票(12306)

```bash
train 北京 上海                # 今天
train 北京 上海 2026-10-30     # 指定日期
train 北京 上海 明天           # 也支持 今天/后天/大后天/+3
train -g 北京 上海             # 只看高铁/城际(G/C)
train -d 北京 上海             # 只看动车(D)
train --json 北京 上海         # JSON 输出
train --stations 北京          # 查车站名/车站码
```

- 预售期一般只到**今天起 15 天内**,超了会直接报错;
- **余票随时变**,要买票必须去 12306 官网/App 确认 —— 汇报时一定要带上这句。

---

## 4. 直接调高德 API(需要精确控制时)

`travel` 命令覆盖不到的组合,直接打 API。key 从技能目录的 `.env` 读:

```bash
KEY=$(sed -n 's/^AMAP_KEY=//p' travel-planner/.env | tail -1 | tr -d '"'"'"' \r')
```

| 用途 | 接口 |
| --- | --- |
| 地理编码(地名→经纬度) | `GET https://restapi.amap.com/v3/geocode/geo?key=&address=&city=` |
| 驾车路线 | `GET .../v3/direction/driving?origin=经度,纬度&destination=经度,纬度&strategy=0` |
| 公交路线 | `GET .../v3/direction/transit/integrated?origin=&destination=&city=&strategy=0` |
| 步行路线 | `GET .../v3/direction/walking?origin=&destination=` |
| 天气 | `GET .../v3/weather/weatherInfo?city=&extensions=all` |

**地理编码务必传 `city`** —— 不传会出现同名地点歧义,坐标全错,路线接口直接报 30001。

| 路线类型 | 关键路径 |
| --- | --- |
| 驾车/步行 | `route.paths[0].distance`(米) / `duration`(秒) |
| 公交 | `route.transits[0].duration`(秒) / `cost`(元) |

天气字段:`lives[0].weather` / `temperature` / `winddirection` / `humidity`,
`forecasts[0].casts[].dayweather` / `daytemp` / `nighttemp`,
`forecasts[0].index[].iname` / `detail`(生活指数)。免费配额:个人开发者每日 5000 次。

> ⚠️ **手机上直接用 HTTP 工具查不了掌上公交**:它要求请求头里带
> `Origin: https://h5.mygolbs.com`(不带就回 47 字节占位串),
> 车来了也要求 `Referer`(不带回 status=400)。
> 所以在 RikkaHub 里**必须用工作区的脚本跑**,别用普通网页抓取工具。

---

## 5. 规划逻辑(脚本内部就是这么算的)

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

## 6. 五城景点省钱速查

| 城市 | 免费/低价亮点 | 必去(付费) |
| --- | --- | --- |
| **郴州** | 苏仙岭、裕后街、白廊公路 | 东江湖 ¥85 / 高椅岭 ¥95 / 万华岩 ¥47 / 板梁古村 ¥35 |
| **长沙** | 橘子洲头、岳麓山、太平老街、湖南省博物馆(需预约) | 岳麓书院 ¥40 |
| **衡阳** | 石鼓书院、酃湖公园、保卫里、回雁峰、东洲岛 | 南岳衡山 ¥80 |
| **上海** | 外滩、武康路、田子坊、新天地、上海博物馆(需预约) | 豫园 ¥40 |

> 完整景点库(门票、时长、省钱等级)见 `references/cities_attractions.md`;
> 美食手册见 `references/food_guide.md`。

---

## 7. 参考文件索引

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
| `references/bus_api.md` | 公交接口说明(掌上公交 + 车来了,按实测整理) |
| `references/mygolbs_cities.json` | 掌上公交 579 城(离线缓存) |
| `references/bus_cities.json` | 车来了城市 ID(320 城) |
| `references/districts.json` | 区县 → 地级市映射 |
| `scripts/generate_plan.py` | 行程规划器 |
| `scripts/amap_nav.py` | 高德客户端(路线 + 天气) |
| `scripts/food_price_scraper.py` | 美食价格采集 |
| `scripts/bus_query.py` | 公交查询(纯标准库,自带 AES 解密) |
| `scripts/preflight.sh` | 环境体检(依赖 / Key / 接口连通性) |
| `scripts/setup_workspace.sh` | 工作区一键安装与自检 |

---

## 8. 典型对话

**用户**: 我想去郴州玩3天,预算2500,带家人,主要看自然风光。
→ 1) 识别: dest_city=郴州, days=3, budget=2500, group_type=family, styles=[自然]
→ 2) 补问: 出发日期、孩子年龄(影响每天景点数)
→ 3) 读 `references/cities_attractions.md` 筛郴州景点,按评分 + 体力约束排序
→ 4) 组合: 东江湖(¥85)+高椅岭(¥95)+免费景点,3 日门票 ≤ ¥300
→ 5) 要天气就查天气 API; 要知道怎么去火车站 → `bus route 郴州 五岭广场 火车站`

**用户**: 明天从郴州坐火车去衡阳,还有票吗?到了怎么坐车去南岳?
→ 1) `train 郴州 衡阳 明天` → 汇报车次、余票,提醒以 12306 为准
→ 2) `bus live 衡阳 南岳1路 --to 南岳衡山` 或 `bus route 衡阳 衡阳站 南岳衡山`

**用户**: 2路到湘南幼专还有几分钟?
→ 1) `bus live 郴州 2路 --to 湘南幼专`
→ 2) 报:最近一辆 车湘LA8317,小于1分钟/即将到站/距150米;下一辆 7分钟/4站
→ 3) 提醒实时数据会变

**用户**: 从橘子洲头到岳麓山怎么走最划算?
→ 1) 地理编码拿到两点经纬度(务必带 city=长沙)
→ 2) 公交路线接口,`strategy=1` 最经济
→ 3) 返回:公交方案(含地铁换乘、耗时、费用)

**用户**: 出发去郴州前,帮我看看那边天气怎么样?
→ 1) 查天气 API(`extensions=all`)
→ 2) 实时 + 3 天预报 + 穿衣/紫外线/舒适度
→ 3) 根据预报给行程微调建议(暴雨天改期高椅岭)

---

## 9. 没有运行环境时能做什么

纯聊天环境(没 bash、没工作区)也能用这个技能的一大半:

- ✅ **行程规划**:读 `references/cities_attractions.md` + `food_guide.md` + `money_saving.md`,
  按第 5 节的评分/体力/预算规则自己排行程
- ✅ **景点与美食推荐**、省钱建议、小红书攻略摘要
- ✅ **解释性问答**(怎么坐公交、看懂站牌、怎么读高德接口)
- ❌ **查不了**:实时公交、到站预测、实时天气、火车票余票、精确路线
  —— 这些必须联网调接口,而且掌上公交/车来了都要求特定请求头,只能用脚本跑

查不到就直说"这个需要联网接口",别用记忆里的旧数据冒充实时结果。

---

## 10. 汇报给用户时

- 行程要给**按天分组**的清单,每项带**时间段 + 门票 + 大概耗时**;
- 被排除的景点要说明**为什么**(时间不够 / 超出预算 / 太远),别让用户以为漏了;
- 路线查询要给**距离 + 耗时 + 费用**,别只说"可以坐地铁";
- 天气查询给**穿衣建议**,不要只贴数字;
- 火车票**必须带上"余票随时变,以 12306 为准"**;
- 公交查询要给**车牌 + 还有几站/几分钟**,并提醒以实际站牌为准;
- 景点门票/开放时间会变,涉及预约的(博物馆、上海博物馆)提醒用户**提前预约**。

---

## 11. 边界

- 本技能只做**直达**公交查询与行程规划,**不做换乘规划**;
- 公交与天气数据都来自第三方源,**覆盖范围和实时性取决于对方**,不是官方承诺;
- 只查公交不做路线规划(跨城路线是高德 API 的活);
- 请低频、善意使用接口。
