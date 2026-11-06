# 接口逆向清单（metroman.cn · 地铁通）

分析时间：2026-11；站点版本：ASP.NET MVC 5.3 / IIS 10；数据版本号：20261028。

实现见 `scripts/metroman/`（纯标准库：无 requests / 无 lxml，用自带的迷你 HTML 解析器）。

## 结论速览

metroman.cn 是**服务端渲染**站点，核心数据（换乘方案、时刻表、线网拓扑）直接嵌在 HTML 中，**没有公开的 JSON REST 接口**（`/api/*` 一律返回 404）。

唯一的 JSON 接口是线网地图页为了前端交互而暴露的**路线查询接口**：

```
GET https://www.metroman.cn/network/{city}/routes?from={stationSlug}&to={stationSlug}
→ application/json
```

其余数据通过解析页面获得。所有接口均为 `GET`、无鉴权、无频率限制，响应均带 `Content-Type: text/html; charset=utf-8`（JSON 接口为 `application/json`）。

## 1. 城市列表

```
GET /
```

首页 `<script id="home-data" type="application/json">` 内含全部 55 个城市：

```json
{
  "initialCity": "sh",
  "cities": [{
    "id": "bj", "key": "beijing", "name": "北京", "secondary": "Beijing",
    "search": "beijing|bj|...|北京|...",
    "title": "北京地铁", "logo": "...", "map": "...", "map2x": "...",
    "plannerUrl": "/planner/beijing", "mapUrl": "/maps/beijing",
    "networkUrl": "/network/beijing", "cityUrl": "/cities/beijing",
    "length": "888", "lines": "26", "stations": "515"
  }],
  "text": { "found": "找到 {0} 个城市", ... }
}
```

- `id`：短代码（`bj`、`sh`），用于内部标识
- `key`：URL 路径用（`beijing`、`shanghai`）
- `length` / `lines` / `stations`：里程（km）、线路数、车站数

## 2. 城市车站索引（车站搜索数据源）

```
GET /planner/{city}
```

返回换乘查询页，页面内 `<li data-key="..." data-station-name="..." data-station-slug="...">` 列出该城市**全部车站**（上海 541 条 / 北京 540 条）。

- `data-station-slug`：URL 友好标识，如 `xujiahui`、`3-hao-hangzhanlou-terminal-3`
- `data-station-name`：中文站名
- `data-key`：以 `|` 分隔的检索别名，依次为
  `slug | 简体名 | 英文名 | 繁体名 | 繁体异体 | 拼音 | 缩写 | (空) | (空)`
  例：`xujiahui|徐家汇|xujiahui|徐家汇|徐家匯|徐家匯|xujiahui|xjh||`
- `.planner-station-modal__item-subname`：英文名

同一 slug 会在页面中重复出现（按线路分组），需按 slug 去重。

## 3. 换乘方案（HTML，服务端渲染）

```
GET /planner/{city}/{fromSlug}-to-{toSlug}?mode={now|depart|arrive|first|last}&fare={ic|cash}&datetime=YYYYMMDDHHMM
```

- `mode=now` 时不需要 `datetime`；其余模式必须带 `datetime`（12 位）
- `fare=ic` 交通卡 / `fare=cash` 现金，票价不同

### 页面结构

```
div.planner-results
  p.planner-results__query          查询条件（日期、时间、计费方式）
  section[data-planner-panel]       推荐 / 早到达 / 少换乘 / 省票价 四个面板
    article.planner-result-card[data-plan-id][data-plan-index]
      h3.planner-result-card__title                     路线 1
      .planner-result-card__summary-time-main           出发 → 到达 时刻
      .planner-result-card__summary-duration            19分钟
      .planner-result-card__summary-meta                4元 / 换乘1次 / 8.6公里
      .planner-result-card__advantage[title]            少换乘 / 省票价
      section.planner-result-card__ride[style=--line-color]
        .planner-result-card__station--board            上车站 + 上车时刻 + 票价
        .planner-result-card__line-name / __line-direction / __line-meta
        .planner-result-card__duration-number            区间运行时长（分钟）
        ol.planner-result-card__stop-list li             经停站 + 到站时刻
        .planner-result-card__station--alight           下车站 + 下车时刻
      section.planner-result-card__connection            换乘方式（如「站内换乘」）
      script[type=application/json]                     线路图几何坐标
```

四个面板会重复渲染同一批方案，**必须按 `data-plan-id` 去重**。

## 4. 线网拓扑数据（JSON，嵌在 HTML 里）

```
GET /network/{city}
```

页面内第一个 `<script type="application/json">` 是完整线网模型：

```json
{
  "version": 20261028,
  "lines": [{"id": 0, "name": "1号线", "en": "Line 1", "code": "1",
             "color": "#E73B41", "slug": "line-1", "search": "...",
             "stationIds": [0, 1, 2], "stats": ["\t28 座车站", "36.4 公里", "1993年5月28日 通车"]}],
  "stations": [{"id": 0, "name": "莘庄", "en": "Xinzhuang", "slug": "xinzhuang",
                "position": [36078.76, 29786.3], "anchorStopId": 0,
                "stopIds": [0, 114, 533], "lineIds": [0, 4, 21],
                "important": true, "search": "..."}],
  "stops": [{"id": 0, "stationId": 0, "lineId": 0, "position": [x, y]}],
  "segments": [{"lineId": 0, "fromStop": 0, "toStop": 1, "path": [[x, y], ...]}],
  "connections": [{"stationId": 0, "kind": 3, "path": [[x, y], ...]}]
}
```

- `lines[].stationIds` → 线路站点顺序（按站名去重后的拓扑顺序）
- `stops[].id` → 线路方向上的站点实例（同名站不同线有不同 stopId）
- `segments[].path` / `connections[].path` → 线路图绘制折线
- 第二个 JSON 块是前端配置：`{"site": "/", "network": "shanghai", "planner": "/planner/shanghai", "routes": "/network/shanghai/routes", ...}`

## 5. 路线查询接口（唯一的 JSON API）

```
GET /network/{city}/routes?from={slug}&to={slug}
```

由 `/assets/js/metro-map.js` 的 `searchRoute()` 调用（`fetch(options.routes + '?' + parameters)`），只接受 `from` / `to` 两个参数，缺任一参数返回 **400 `错误的请求`**。

```json
{
  "mode": "depart", "datetime": "202611061644", "fare": "ic",
  "queryText": "2026年11月6日（周五）· 16:44 出发",
  "status": "Ok", "message": "…", "emptyAction": null,
  "plans": [{
    "id": "p4c9dd4e00250971a", "duration": "19分钟", "fare": "4元",
    "transfers": "换乘1次", "partial": false,
    "paths": [{"lineId": 0, "color": "#E73B41", "code": "1", "name": "1号线",
               "fromId": 7, "toId": 11, "fromName": "徐家汇",
               "toName": "一大会址·黄陂南路", "path": [[x, y], ...]}],
    "connections": [{"kind": 2, "path": [[x, y], ...]}],
    "stops": [{"stationId": 7, "position": [x, y]}],
    "markers": [{"stationId": 11, "stopId": 413, "kind": "transfer",
                 "name": "一大会址·黄陂南路", "position": [x, y]}]
  }]
}
```

特点与限制：

- 忽略 `mode` / `datetime` / `fare` 参数，始终按「当前时刻」计算（实测 mode/fare/datetime 传不同值返回完全一致）
- 不含逐站到站时刻，只有线路、起终站、耗时、票价、换乘次数
- `kind`：`from` / `to` / `transfer`（换乘点）

因此本项目以 **HTML 方案页**为主数据源，JSON 接口作为轻量校验/兜底。

## 6. 车站详情（首末班车）

```
GET /cities/{city}/stations/{stationSlug}
```

```html
<article class="city-timetable-card" data-timetable-line="line-1">
  <header><a href="/cities/shanghai/lines/line-1">
    <span class="city-line-code" style="background:#E73B41">1</span><h3>1号线</h3>
  </a></header>
  <section class="city-timetable-direction" data-pattern-id="0">
    <h4>富锦路方向</h4>
    <table><tbody>
      <tr><th scope="row">工作日(周一至周四)</th>
          <td><span data-first-time><time datetime="05:02" data-service-day-offset="0">05:02</time></span>
              <span data-last-time><time datetime="22:50" data-service-day-offset="0">22:50</time></span></td></tr>
      <tr><th scope="row">周五</th>
          <td><span data-first-time><time datetime="05:02" data-service-day-offset="0">05:02</time></span>
              <span data-last-time><time datetime="00:18" data-service-day-offset="1">00:18</time></span></td></tr>
    </tbody></table>
  </section>
</article>
```

- 每天型：工作日(周一至周四) / 周五 / 周六 / 周日、国定假日
- `data-service-day-offset="1"` 表示末班车跨到次日（需要拼接日期）
- 数据版本：`[data-timetable-version]`

## 7. 线路详情（途经站）

```
GET /cities/{city}/lines/{lineSlug}
```

页面内 `a[href="/cities/{city}/stations/{slug}"]` 按顺序给出途经站。

- 环线（如上海 4 号线、北京 2 号线）首尾重复一次
- 往返线（如北京首都机场线）会完整列出返程

## 8. 其它可用页面

| 路径 | 内容 |
|------|------|
| `/maps/{city}` | 线网图页面（OpenSeadragon + 同一份 JSON） |
| `/network/{city}` | 线网图 + 路线 API 前端 |
| `/cities` | 城市总览 |
| `/cities/{city}` | 城市概览 + 换乘车站列表 |
| `/cities/{city}/stations` | 全量车站列表页 |
| `/rankings` `/articles` `/apps` | 排行、指南、App 下载 |
| `/sitemaps/sitemap_*.xml` | 站点地图（城市/线路/车站/换乘页 URL 全集） |

多语言前缀：`/en`、`/ja`、`/zh-hant`（内容一致，语言不同）。

## 8. 本项目的实现要点

| 关注点 | 做法 |
|--------|------|
| 零第三方依赖 | 自带 `htmldom.py`（`html.parser` 搭的小 DOM），不依赖 lxml / BeautifulSoup |
| HTTP | 标准库 `urllib`，带 gzip/deflate 解压 |
| 缓存 | 城市 24h / 车站索引 12h / 线网 6h / 时刻表 6h / 换乘方案 60s，缓存在 `~/.cache/metroman` |
| 方案去重 | 服务端在 4 个面板里重复渲染同一批方案，必须按 `data-plan-id` 去重 |
| 跨日末班 | `time[data-service-day-offset="1"]` 表示次日，折算成「分钟数 > 1440」 |
| 口语地标 | `metroman/resolver.py` 的 `KNOWN_LANDMARKS`（首都机场→3号航站楼等） |
| 铁路站↔地铁站 | `scripts/transit.py` 的 `station_core` + `build_rail_metro_xref` |

## 反爬与频率

- 无登录、无 Token、无签名
- 需要正常 `User-Agent`
- 建议：城市线网数据缓存 6 小时、车站索引 12 小时、换乘方案 60 秒
