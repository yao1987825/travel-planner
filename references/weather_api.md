# 天气数据接口逆向说明（weather.com.cn）

分析时间：2026-11。weather.com.cn **没有公开 API 文档**，但前端在服务端渲染的页面里挂了一组
JSONP 数据接口（`d1.weather.com.cn`），内容与页面完全一致，无需登录、无 Key。

抓取方式：普通 HTTP GET + `Referer: http://www.weather.com.cn/`。

---

## 1. 接口清单

### 1.1 实时天气 + 生活指数 + 预警（最全的一个）

```
GET http://d1.weather.com.cn/weather_index/{城市码}.html
```

响应是连续几个 `var` 赋值：

```js
var cityDZ ={"weatherinfo":{"city":"北京","cityname":"beijing","temp":"999","tempn":"4",
                            "weather":"晴转多云","wd":"西风转东北风","ws":"3-4级转<3级",
                            "weathercode":"d0","weathercoden":"n1","fctime":"202611060800"}};
var alarmDZ ={"w":[{"w1":"北京市","w2":"","w3":"","w4":"03","w5":"暴雪","w6":"02","w7":"黄色",
                    "w8":"2026-11-06 18:28","w9":"市气象台...发布分区暴雪黄色预警信号：...",
                    "w10":"202611061828545112暴雪黄色","w11":"10101-20261106182858-0302.html",
                    "w12":"2026-11-06 18:35","w13":"北京市发布暴雪黄色预警信号",
                    "w14":"Alert","w15":"2026-11-08 06:28:58","w16":"11000041600000_20261106182858"}]};
var dataSK ={"nameen":"beijing","cityname":"北京","city":"101010100",
             "temp":"5.9","tempf":"42.6","WD":"北风","wde":"N","WS":"0级","wse":"0km/h",
             "SD":"53%","sd":"53%","qy":"1025","njd":"18km","time":"19:40",
             "rain":"0","rain24h":"0","aqi":"32","aqi_pm25":"32",
             "weather":"晴","weathere":"Sunny","weathercode":"d00",
             "limitnumber":"4和9","date":"11月06日(星期五)"};
var dataZS ={"zs":{"date":"2026110618","lk_name":"路况指数","lk_hint":"干燥","lk_des_s":"...",
                   "cl_name":"晨练指数","cl_hint":"适宜","cl_des_s":"...",
                   "ct_name":"穿衣指数","ct_hint":"寒冷","ct_des_s":"建议着厚羽绒服等隆冬服装。",
                   "tr_name":"旅游指数","tr_hint":"适宜","tr_des_s":"...",
                   "yd_name":"运动指数","uv_name":"紫外线强度指数","gm_name":"感冒指数",
                   "xc_name":"洗车指数","co_name":"舒适度指数","pl_name":"空气污染扩散条件指数",
                   "gl_name":"太阳镜指数","ac_name":"空调开启指数","ag_name":"过敏指数", ...}};
```

| 变量 | 内容 | 关键字段 |
|------|------|----------|
| `cityDZ` | 今日天气 | `temp` 最高温、`tempn` 最低温、`weather` 天气、`wd` 风向、`ws` 风力 |
| `alarmDZ` | 气象预警 | `w5` 类型、`w7` 级别、`w8` 发布时间、`w9` 内容、`w13` 标题、`w15` 失效时间 |
| `dataSK` | 实况 | `temp` 温度、`WD/WS` 风向风力、`SD` 湿度、`qy` 气压、`njd` 能见度、`aqi` 空气质量、`rain24h` 24h 降水 |
| `dataZS` | 生活指数 | 约 30 项：`ct_*` 穿衣、`tr_*` 旅游、`yd_*` 运动、`uv_*` 紫外线、`gm_*` 感冒、`xc_*` 洗车、`cl_*` 晨练、`co_*` 舒适度… |

> ⚠️ `weather_index` 的 `cityDZ.temp` 有时是占位符 `"999"`（表示实时未更新），
> 这时用 `dingzhi` 接口的真实值补齐（见下）。

### 1.2 今日/明日白天夜间（文本最可靠）

```
GET http://d1.weather.com.cn/dingzhi/{城市码}.html
```

```js
var cityDZ101250501 ={"weatherinfo":{"city":"101250501","cityname":"郴州","fctime":"202611061800",
                                     "temp":"17℃","tempn":"14℃","weather":"小雨",
                                     "weathercode":"d7","weathercoden":"n7",
                                     "wd":"西北风转北风","ws":"<3级"}};
var alarmDZ101250501 ={"w":[]}
```

- 变量名带城市码（`cityDZ{code}` / `alarmDZ{code}`），解析时要用 `cityDZ101250501` 这种精确名；
- `temp` / `tempn` 是**带 ℃ 的字符串**，要正则剥数字；
- `weathercode` 以 `d` 开头是白天、`n` 开头是夜间。

### 1.3 空气质量（逐小时）

```
GET http://d1.weather.com.cn/aqi/{城市码}.html
→ setAirData({"station":"101010100","name":"北京","data":[{"time":"09","t1":"193","t2":"4",...}]})
```

`t1` = AQI，`t2` = 首要污染物等级，其余为各污染物浓度。

### 1.4 7 天预报 + 逐小时 + 24 小时实况（服务端渲染页面）

```
GET http://www.weather.com.cn/weather/{城市码}.shtml
```

页面里含两块内嵌 JSON 和一块 HTML 列表：

```js
var hour3data ={"1d":["06日23时,n01,多云,3℃,东风,<3级,0","07日02时,..."],
                 "23d":[["07日08时,d01,多云,4℃,北风,<3级,2", ...], ...]};
var observe24h_data ={"od":{"od0":"202611061900","od1":"北京",
    "od2":[{"od21":"19","od22":"6.9","od23":"202","od24":"东北风",
            "od25":"1","od26":"0","od27":"47","od28":"32"}, ...]}};
```

- `hour3data` 每条格式：`日期时间,图标码,天气,温度,风向,风力,降水`
  - `1d` = 今天剩余时段，`23d` = 未来各天的数组
  - 图标码 `d07`/`n06` 里 `d`=白天 `n`=夜间，后两位是图标编号
- `observe24h_data.od2[]` 字段：`od21` 小时、`od22` 温度、`od23` 风向角、`od24` 风向、
  `od25` 风力、`od26` 降水、`od27` 湿度、`od28` 气压（**不确定，脚本不输出这一项**）

7 天预报的 HTML 块：

```html
<ul class="t clearfix">
  <li class="sky skyid lv2 on">
    <h1>6日（今天）</h1>
    <p title="多云" class="wea">多云</p>
    <p class="tem"><i>2℃</i></p>          <!-- 今天只有最低温 -->
    <p class="win"><em><span title="东北风" class="NE"></span></em><i><3级</i></p>
  </li>
  <li class="sky skyid lv3">
    <h1>7日（明天）</h1>
    <p title="雨夹雪" class="wea">雨夹雪</p>
    <p class="tem"><span>5℃</span>/<i>1℃</i></p>
    <p class="win"><em><span title="北风" class="N"></span></em><i><3级</i></p>
  </li>
  ...
</ul>
```

> ⚠️ 三个坑：
> 1. **今天那一格只有最低温**（`<i>2℃</i>`），最高温要拿 `dingzhi` 的 `temp` 补；
> 2. 风力是 `<i><3级</i>` —— 内容以 `<` 开头，正则要用 `<i>(.*?)</i>` 而不是 `[^<]*`；
> 3. `title` 属性里的风向是中文（`东北风`），`class` 里是英文缩写（`NE`）。

### 1.5 城市编码（AREAID）

| 来源 | 说明 |
|------|------|
| `http://j.i8tq.com/weather2020/search/city.js` | `var city_data = {省: {市: {区县: {AREAID, NAMECN}}}}`，3137 个城市/区县，已离线整理进 `references/weather_cities.json` |
| `http://toy1.weather.com.cn/search?cityname=北京` | 在线搜索兜底，返回 `([{"ref":"101010100~beijing~北京~Beijing~北京~Beijing~10~100000~BJ~北京"}])`，第 1 段是 AREAID |

---

## 2. 已失效 / 不再使用的路径

| 路径 | 状态 |
|------|------|
| `http://www.weather.com.cn/data/sk/{code}.html` | 301 → `https://e.weather.com.cn/`（新平台首页，无数据） |
| `http://www.weather.com.cn/data/cityinfo/{code}.html` | 同上，301 失效 |
| `http://www.weather.com.cn/find?searchWord=...` | 同上，301 失效 |
| `http://d1.weather.com.cn/calendar_new/...` | 302 失效 |
| `http://d1.weather.com.cn/observe24h/{code}.html` | 302 失效（24h 数据在页面里） |
| `http://d1.weather.com.cn/wap_40d/{code}.html` | 可用，但**天气现象是数字编码**（`005`/`006`/`007`/`008`），与页面文字对不上，容易解错，脚本不用 |

---

## 3. 实现要点

- 全部用标准库 `urllib` 实现，`Referer` 必带；
- 缓存 30 分钟（实况）/ 1 小时（预报页），缓存在 `~/.cache/weather_query`；
- 生活指数只挑常用 8 项输出（穿衣/旅游/运动/紫外线/感冒/洗车/晨练/舒适度），其余在 `--json` 里；
- 预警内容（`w9`）完整保留，汇报时截断到 120 字即可；
- **不支持历史天气** —— 接口只给当前与预报。

---

## 4. 换成别的数据源？

如果 weather.com.cn 的接口变动，`scripts/weather_query.py` 里每个函数对应一个数据源，
替换时保持函数签名不变即可：

| 函数 | 数据源 |
|------|--------|
| `resolve_area(city)` | `references/weather_cities.json` / `toy1.weather.com.cn/search` |
| `fetch_live(areaid)` | `d1.weather.com.cn/weather_index/` |
| `fetch_dingzhi(areaid)` | `d1.weather.com.cn/dingzhi/` |
| `fetch_forecast(areaid)` | `www.weather.com.cn/weather/` |
| `fetch_aqi(areaid)` | `d1.weather.com.cn/aqi/` |
