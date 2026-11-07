---
name: travel-planner
description: 旅游攻略与出行规划 + 公共交通实时查询 —— 把火车票(12306)、地铁换乘(55城)、公交实时(579城)、气象预报(中国天气网)串成一条完整出行时间线，并生成按天行程、景点与美食推荐、省钱攻略。Use when the user asks 旅游攻略、出行规划、行程安排、景点推荐、省钱旅游、几日游、从A到B怎么走/坐几号线/几路车/几点的车、地铁换乘、末班车赶得上吗、公交到站预测、火车票/余票/12306、天气/天气预报/穿衣建议，或问公交:几路车/有没有车/到哪了/还有几站/几分钟到/某站有哪几路/坐什么车。
compatibility: "需要能执行命令的环境(工具箱 U 盘 / opencode / RikkaHub 工作区)。全部脚本零第三方依赖、零 API Key, 只要有 python3 就能跑。纯对话模式下仍可读 references/ 做行程规划与景点美食推荐, 但查不了实时公交/地铁/天气/火车票。"
---

# 出行助手：把一次出行问明白

出行不是四个互不相干的功能，而是**一次旅程由若干段组成**：

```
出发地 ──[火车/高铁]──→ 到达站 ──[地铁/公交]──→ 目的地 ──[步行]──→ 景点
                            ↑                    ↑
                    首班/末班车卡点        天气、预警、票价
```

这个技能按这条主线组织：先拼出**完整时间线**，再用单项命令补细节。

| 段 | 数据源 | 脚本 |
|----|--------|------|
| 城际（火车/高铁/动车） | 12306 | `scripts/train_store.py` |
| 市内换乘（地铁） | 地铁通 metroman.cn，55 城 | `scripts/metro_query.py` |
| 市内接驳（公交实时） | 掌上公交 + 车来了，579 城 | `scripts/bus_query.py` |
| 天气 / 预警 / 穿衣 | 中国天气网 weather.com.cn | `scripts/weather_query.py` |
| **整段编排（主入口）** | 上面全部 | `scripts/transit.py` |
| 行程规划 / 景点 / 美食 | 本地参考库 | `scripts/generate_plan.py` |

---

## 1. 先判断：这次要查什么

| 用户在问 | 用什么 |
|----------|--------|
| 「从 A 到 B 怎么走」「坐几号线」「几路车」「几点出发能赶上」 | **transit.py journey**（主入口） |
| 「XX 地铁怎么坐」「XX 线经过哪些站」「XX 站末班车几点」 | `metro_query.py` |
| 「2 路到哪了」「还有几分钟」「某站有哪几路」 | `bus_query.py` |
| 「明天北京到上海还有票吗」 | `train_store.py` / `transit.py journey --mode train` |
| 「那边天气怎么样」「要穿什么」「有没有预警」 | `weather_query.py` |
| 「帮我排 3 天行程」「预算 2500 怎么玩」 | `generate_plan.py` + `references/` |

**不确定就问用户**，别瞎猜起点终点。

### 统一入口：`travel`（推荐）

所有能力都收在一个命令族下，装好命令后直接敲：

```bash
travel metro plan 上海 徐家汇 陆家嘴      # 地铁换乘
travel bus live 郴州 2路 --to 湘南幼专     # 公交到站预测
travel weather live 郴州                 # 天气
travel train 郴州 长沙 明天               # 火车票
travel journey --from 郴州西 --to 陆家嘴 --date 明天 --weather
travel plan --profile profile.json --output ./trip
travel price 上海                        # 本地价格参考（只读）
travel help                              # 完整清单
```

没装命令时，用等价的 `python3 scripts/<脚本>.py ...` 形式即可。

---

## 2. 主入口：拼一条完整出行时间线

```bash
python3 scripts/transit.py journey --from 郴州西 --to 陆家嘴 --date 明天 --weather
```

| 参数 | 说明 |
|------|------|
| `--from` / `--to` | 起点、终点。可以是**火车站名、地标、地铁站名** |
| `--date` | `今天` / `明天` / `后天` / `2026-11-08` |
| `--arrive-by 18:00` | **必须到达的时刻**，脚本反推最晚能坐哪班车 |
| `--depart-at 09:00` | 必须出发的时刻 |
| `--mode` | `auto`(默认) / `train` / `metro` / `bus` |
| `--city` | 市内行程时指定城市（跨城会自动推断） |
| `--weather` | 附带目的地天气；有预警会进警告 |
| `--json` | 结构化输出 |

脚本自动做的事：

1. **判断跨城还是市内** —— 认火车站名（12306 电报码）、认地铁城市、认地铁站名；
2. **城际段** —— 查 12306，挑车次（有 `--arrive-by` 时挑「能赶上且尽量晚出发」的那班）；
3. **到达站 ↔ 目的地** —— 用**铁路站↔地铁站映射**接上（`上海虹桥`→`虹桥火车站`，`长沙南`→`长沙火车南站`）；
4. **市内段** —— 地铁优先（准点、有票价、有首末班），地铁不覆盖再考虑公交；
5. **换乘缓冲** —— 火车→地铁至少 20 分钟，地铁站内换乘至少 4~8 分钟；
6. **末班车校验** —— 落地时地铁是否已经收班；跨日末班（次日 00:36）会算进去；
7. **天气校验** —— `--weather` 时把目的地天气与预警挂到时间线。

示例输出：

```
╭ 郴州西 → 陆家嘴 ╮
  2026-11-07（周六）

1. 火车   14:43 → 21:47   7小时4分钟   G1302 郴州西→上海
   G1302 次 · 高铁 · 商务座4、一等座有、二等座有
   ℹ️ 票价与余票以 12306 官网/App 为准（此处不估算票价）

2. 地铁   22:12 → 22:32   20分钟   3元   上海火车站 → 陆家嘴
   ▸ 1号线（莘庄方向） 上海火车站 22:12 上车 → 人民广场 22:17 下车（3站）
   ▸ 2号线（浦东1号2号航站楼方向） 人民广场 22:27 上车 → 陆家嘴 22:32 下车（2站）
   换乘1次
   ℹ️ 上海火车站 当天末班车 00:36（次日）

总计 7小时4分钟 · 约 ¥3 · 火车 + 地铁
```

### 用 journey 时的三条纪律

1. **先看警告**。⚠️ 里写着「末班车已过」「换乘时间不够」「没有能在 18:00 前到的车次」——这些必须转达给用户，别只报 happy path。
2. **不要自己编票价**。火车票价接口不给，脚本不估算，汇报时照实说「以 12306 为准」。
3. **末段走路**。地铁只到车站，站点到景点那一段脚本给不了路线，提示用户用地图 App。

---

## 3. 单项查询（补细节用）

### 3.1 地铁（55 城）

```bash
python3 scripts/metro_query.py plan 上海 徐家汇 陆家嘴
python3 scripts/metro_query.py plan 北京 "3号航站楼" "天安门东" --mode first --datetime 202611081043
python3 scripts/metro_query.py plan 上海 人民广场 虹桥火车站 --fare cash
python3 scripts/metro_query.py station 上海 徐家汇      # 各方向首末班车
python3 scripts/metro_query.py line 上海 1号线          # 途经站顺序
python3 scripts/metro_query.py lines 上海               # 线路清单
python3 scripts/metro_query.py stations 上海 --search 机场
python3 scripts/metro_query.py cities                   # 55 城市
```

- `--mode`：`now` / `depart` / `arrive` / `first` / `last`；非 `now` 必须带 `--datetime YYYYMMDDHHMM`
- `--fare`：`ic`（交通卡）/ `cash`（现金），票价不同
- **`--datetime` 必须是未来时间**（`YYYYMMDDHHMM`）——用过去的时间查询，服务端不会返回结果，表现为请求超时
- **口语地标已内置映射**：「首都机场」→`3号航站楼`、「虹桥机场」→`虹桥1号航站楼`、「白云机场」→`机场北(2号航站楼)`
- 车站名多个候选时脚本会列出来并要求 `--pick N` 确认

### 3.2 公交实时

```bash
python3 scripts/bus_query.py live 郴州 2路 --to 湘南幼专   # 到站预测
python3 scripts/bus_query.py live 郴州 2路                 # 实时车辆位置
python3 scripts/bus_query.py station 郴州 五岭广场          # 站点线路
python3 scripts/bus_query.py route 郴州 五岭广场 火车站     # 直达线路
python3 scripts/bus_query.py scan 郴州 --limit 10           # 全城扫
python3 scripts/bus_query.py lines 郴州                    # 线路目录
```

通用参数：`--src mygolbs|chelaile`、`--json`、`--limit N`。

**`--to` 是关键**：给了目标站才会去拿「还有几站 / 还有几分钟」的到站预测。

### 3.3 天气（中国天气网）

```bash
python3 scripts/weather_query.py live 郴州        # 实况 + AQI + 生活指数 + 预警
python3 scripts/weather_query.py forecast 郴州    # 7 天预报 + 逐小时 + 24 小时实况
python3 scripts/weather_query.py alerts 郴州      # 气象预警
python3 scripts/weather_query.py all 郴州 --json  # 全部
```

- 城市名支持「郴州」「北京」「上海」，自动转城市码（`references/weather_cities.json`，3137 个城市/区县）
- 生活指数含穿衣、旅游、运动、紫外线、感冒、洗车、晨练 —— 汇报时给**建议**（"穿衣寒冷，建议羽绒服"），不要只贴数字
- **预警必须转达**（暴雪/暴雨/台风预警会影响行程安排）
- **不支持历史天气**，用户问"上周天气"要直说查不到

### 3.4 火车票（12306）

```bash
python3 scripts/train_cli.py 郴州 长沙 明天
```

或直接用 `transit.py journey --mode train`。
中转票用 `train_store.train_transfer_query({'date':...,'from_station':...,'to_station':...})`。

- 站名要用**标准站名**（不带"市"字）
- 预售期一般只到今天起 15 天内
- **余票随时变，必须带一句「以 12306 官网/App 为准」**

---

## 4. 行程规划（多天）

```bash
python3 scripts/generate_plan.py --profile profile.json --output ./trip
```

`profile.json`：

```json
{
  "dest_city": "上海", "travel_days": 3, "budget_cny": 3000,
  "budget_level": "mid", "depart_date": "2026-05-01",
  "travel_style": ["文化", "美食"], "group_type": "couple",
  "mobility": "mid", "need_weather": true
}
```

| 字段 | 说明 | 默认 |
|------|------|------|
| `dest_city` | 目的地城市 | 必填 |
| `travel_days` | 天数 | 必填 |
| `budget_cny` | 总预算 | — |
| `travel_style` | 文化/美食/自然/亲子/文艺 | 文化、美食 |
| `group_type` | solo/couple/family/friends | solo |
| `mobility` | high(4个/天)/mid(3个)/low(2个) | mid |
| `budget_level` | budget/mid/luxury | mid |
| `need_weather` | 是否查天气 | — |

**缺的信息先问，别替用户假设**。只有天数和城市是硬性必需。

景点之间怎么走：用 `transit.py journey --city <城市> --from <景点> --to <景点>`，
市内默认走地铁；地铁到不了的（郊区、场馆）再用 `bus_query.py route`。

---

## 5. 景点 / 美食 / 参考资料

| 文件 | 内容 |
|------|------|
| `references/cities_attractions.md` | 五城景点库（门票、时长、省钱等级） |
| `references/food_guide.md` | 五城美食价格手册（必吃小吃、店铺、日均预算） |
| `references/money_saving.md` | 全链路省钱攻略 |
| `references/xiaohongshu_all_cities.md` | 五城小红书推荐合集（88 篇，含避坑） |
| `references/transit_link.md` | **多方式联动规则**（换乘缓冲、末班车卡点、天气决策） |
| `references/metro_api.md` | 地铁数据接口逆向说明 |
| `references/weather_api.md` | 天气数据接口逆向说明 |
| `references/bus_api.md` | 公交接口说明（掌上公交 + 车来了） |
| `references/travel_schema.md` / `travel_api.md` | 数据库表结构 / RESTful 接口定义 |

五城速查：郴州（苏仙岭、裕后街免费，东江湖 ¥85）、长沙（橘子洲、岳麓山免费，岳麓书院 ¥40）、
衡阳（石鼓书院、回雁峰免费，南岳衡山 ¥80）、上海（外滩、武康路免费，豫园 ¥40）。

---

## 6. 汇报规范

- **先给结论**：坐哪几段、换乘几次、多久、多少钱，再给细节；
- **必须转达警告**：末班车赶不上、换乘时间不够、天气预警；
- **逐站时刻**只在用户要「怎么坐」时展开，摘要里给线路和方向就够；
- 火车票**必须带「余票随时变，以 12306 为准」**；
- 公交查询给**车牌 + 还有几站/几分钟**，并提醒以实际站牌为准；
- 天气给**穿衣/出行建议**，不要只贴数字；
- 景点门票/开放时间会变，涉及预约的（博物馆、上海博物馆）提醒**提前预约**；
- 查不到就**照实说没查到**，绝不编线路、车次或时刻。

---

## 7. 环境说明

### 环境 A：工具箱 U 盘 / opencode（有 bash）

装一次，命令直接可用：

```bash
bash scripts/install.sh
```

它做两件事：把技能复制到 opencode 的技能目录（`~/.opencode/skills/`，没有则用
`~/.config/opencode/skills/`），并在 PATH 上的目录（优先 `~/.local/bin`）装好命令 wrapper：

| 命令 | 干什么 |
|------|--------|
| `travel` | 统一入口，下面五个都是它的子命令 |
| `train` | 12306 火车票余票 |
| `bus` | 公交实时车辆 / 到站预测 |
| `metro` | 地铁换乘 / 时刻表 |
| `journey` | 整段出行时间线（火车+地铁+公交+天气） |

装完自检：`bash scripts/preflight.sh`。
如果 `~/.local/bin` 不在 PATH 里，install.sh 会提示怎么加。

### 环境 B：RikkaHub / 手机工作区（proot Linux）

工作区里没有上面那些命令，但有 shell、python3 和网络 —— **跑同一个脚本**：

```bash
git clone --depth 1 https://github.com/yao1987825/travel-planner.git
bash travel-planner/scripts/setup_workspace.sh   # 一键装 + 自检
```

> ⚠️ **手机上不能直接用 HTTP 工具查公交**：掌上公交要求请求头带
> `Origin: https://h5.mygolbs.com`（不带就回 47 字节占位串），
> 车来了也要求 `Referer`（不带回 status=400）。
> 所以在 RikkaHub 里**必须用工作区的脚本跑**，别用普通网页抓取工具。

**本技能零第三方依赖、零 API Key**，装好 python3 就能跑，不需要 pip install。

### 环境 C：纯聊天（没 bash、没工作区）

✅ 行程规划、景点与美食推荐、省钱建议（读 `references/`）
❌ 实时公交、地铁方案与时刻、天气、火车票（必须联网调接口）

查不到就直说"这个需要联网接口"，别用记忆里的旧数据冒充实时结果。

---

## 8. 边界

- 地铁换乘方案来自地铁通（metroman.cn），是**推荐时刻表**结果，不含步行、接驳、安检进站时间；
- 火车票来自 12306，**只查不购**；
- 公交只做**直达**查询与**实时车辆**，不做公交换乘规划；
- 公交与天气数据都来自第三方源，**覆盖范围和实时性取决于对方**，不是官方承诺；
- **驾车与精确步行路线已移除**（原高德服务下线），市内出行用地铁/公交，末段步行请用地图 App；
- 请低频、善意使用接口。
