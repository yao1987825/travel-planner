# 公交查询 API 参考

> 本文按 **2026-11-05 对线上接口的实测**整理, 不是抄文档。
> 脚本 `scripts/bus_query.py` 已经把下面的细节全部包好, 正常用脚本就行;
> 这份文档是给「脚本挂了要自己手搓 curl」或者「要改脚本」时用的。

---

# 数据源一:掌上公交 (mygolbs)

## 基本信息

- **端点**: `https://h5.mygolbs.com/ApiData.do`
- **方法**: POST,表单(`application/x-www-form-urlencoded`)
- **必带请求头**:

```
Origin: https://h5.mygolbs.com
Referer: https://h5.mygolbs.com/
User-Agent: Mozilla/5.0 (Linux; Android 12) Mobile Safari/537.36
```

> ⚠️ **Origin 头是命门**: 末尾多一个斜杠、换成 http、或者干脆不带,
> 上游都回 **HTTP 200 + 47 字节占位串**
> (`0vx0czK73ykwCHaLBTiKh0iCXQINzRvSZw4+b/H8FgE52U=`),
> 症状是「永远查不到」。实测: 正确 Origin → 郴州线路目录 346KB;错误 Origin → 47 字节。

---

## CMD=101:城市列表

**参数**: `CMD=101`

**响应**:

```json
{
  "status": "1",
  "msg": "...",
  "data": [{"cityname": "贵阳市"}, {"cityname": "长春市"}]
}
```

实测 **579** 个城市/县。离线缓存见 `references/mygolbs_cities.json`。

> `status` 有时是数字 `1`, 有时是字符串 `"1"` —— 比较时统一 `str(status) == "1"`。

---

## CMD=119:城市线路目录

**参数**: `CMD=119&CITYNAME=郴州市`

**响应**: `{status, msg, buslines: [...], busstations: []}`

```json
{
  "lineName": "1路",
  "upperOrDown": "1",
  "from": "长冲铺",
  "to": "兴义粮油市场",
  "company": "郴州市公共汽车公司",
  "beginTime": "", "endTime": "",
  "number": "", "cityName": "", "comments": "",
  "stationName": "", "stationID": "", "commentStationName": "",
  "neartext": "", "nexttext": "", "nearnum": 0, "neardis": "", "neartime": "",
  "distance": 0.0, "routeNameUp": "", "routeNameDown": "",
  "shortName": 1, "stationOrder": 0
}
```

- `upperOrDown`: 方向, `"1"` 上行 / `"2"` 下行。传 0/3/空串时服务端**静默退化成方向 1**, 会回错方向的车。
- 同名线路有两条记录(上下行各一条)。郴州实测 **857 条方向 / 438 个唯一线名**。
- `busstations` 实测是**空数组**, 别指望从这里拿站表。
- 单城响应 300KB+, 一定要落盘再过滤, 别整份读进上下文。

---

## CMD=103:线路站表 ★

**这是拿"到站预测"的第一跳**, 原文档里没有, 但它才是关键。

**参数**: `CMD=103&CITYNAME=郴州市&LINENAME=2路&DIRECTION=1`

**响应**:

```json
{
  "routeName": "2路",
  "upperOrDown": "1",
  "beginTime": "", "endTime": "",
  "planTime": "11:40",
  "routeColor": "",
  "commonts": "票价：2元",
  "data": [
    {
      "stationId": 0,
      "stationName": "长冲铺",
      "station_lon": 113.04068645,
      "station_lat": 25.86029429,
      "stationOrder": 1,
      "showName": "长冲铺",
      "come": 0, "arrive": 0,
      "stationsStatus": 1,
      "StationNihePointIndex": 0
    }
  ],
  "nihelist": [], "routeId": "", "loopType": 0, "showDepart": "",
  "firstLast": "", "companys": "", "routeName2": "",
  "StationRelatedRouteName": "", "telephoneTips": "",
  "status": "1", "msg": "..."
}
```

**关键**: `stationOrder` 就是**1 基站序**, 把它当 `STATIONORDER` 参数传给 CMD=104。
郴州 2 路实测 39 站。

---

## CMD=104:实时车辆 + 到站预测 ★

**参数**:

```
CMD=104&CITYNAME=郴州市&LINENAME=2路&DIRECTION=1[&STATIONORDER=5]
```

`STATIONORDER` = 目标站在线路里的站序(取自 CMD=103 的 `stationOrder`)。
**带上它才有到站预测**。

**响应**:

```json
{
  "data": [{"stationName": "造纸厂", "index": 1, "arrive": 0, "come": 1, "showType": 1}],
  "list": [
    {
      "stationName": "造纸厂",
      "statusType": "2",
      "index": 1,
      "station_lat": 25.85186885, "station_lng": 113.02990384,
      "bus_lat": 25.859598155526395, "bus_lng": 113.04078999261185,
      "busNumber": "湘LA9239",
      "crowdStatus": "",
      "busToStationNiheDistance": 1642.99,
      "nihePointIndex": 2,
      "angle": 211.43,
      "_recTime": 1793849657104,
      "busType": "", "runType": "", "sectionStation": "",
      "personNumOnBus": "", "busRaoXingTips": "", "abnormal": ""
    }
  ],
  "dislist": [{"d": 1716.04}],
  "speedlist": [{"co": "orange", "speed": 438.0}],
  "hasReal": "1",
  "planTime": "11:40",
  "runState": 0,
  "exceptionFlag": false,
  "plantimeSimpleVectorMain": [{"remarks": "", "stime": "11:40"}],
  "plantimeSimpleVectorSub": [],
  "routeOnStationRTimeInfoList": [
    {
      "routeName": "2路",
      "upperOrDown": "1",
      "stationName": "湘南幼专",
      "stationIndex": "4",
      "frmStationName": "长冲铺",
      "toStationName": "首末站5",
      "busToStationCount": 4,
      "busToStationTime": 7.0,
      "busToStationDistance": 3000,
      "busToStationTips": "4站",
      "busToStationTimeTips": "8分钟",
      "busToStationDistanceTips": "3公里",
      "busToStationName": "造纸厂",
      "busNumber": "湘LA9239",
      "stationLat": "25.8385901", "stationLng": "113.02178498",
      "planTime": "11:40"
    }
  ],
  "status": "1",
  "msg": "获取实时数据成功!"
}
```

**字段要点**:

| 字段 | 含义 |
| --- | --- |
| `list[]` | 在途车辆。`busNumber`=车牌, `stationName`=下一站, `busToStationNiheDistance`=距下一站(米) |
| `list[].index` | **不是连续站序**, 只覆盖有车的站, 跟 CMD=103 的 `stationOrder` 对不上 —— 别拿它算站数 |
| `routeOnStationRTimeInfoList[]` | **到站预测**(需带 STATIONORDER)。每站最多给最近 2 辆车 |
| `busToStationCount=-1` 且 `busNumber` 为空 | 站已过 / 没预测 |
| `dislist` / `speedlist` | 每段里程(米) / 每段均速(m/min), 用来估算区间行驶时间 |
| `hasReal` | `"1"`=上游给实时数据; `"0"`=该城不给实时车辆位置(北京/上海/成都等) |
| `planTime` | 数据时间 |
| `exceptionFlag` | 异常标记 |

---

## CMD=102:站点搜索

**参数**: `CMD=102&CITYNAME=郴州市&KEYWORD=五岭广场`

**响应**:

```json
{
  "status": "1",
  "msg": "...",
  "busstations": [
    {
      "stationId": 0,
      "stationName": "五岭广场",
      "station_lon": 0.0, "station_lat": 0.0,
      "stationOrder": 0,
      "lat": "25.7724108272", "lng": "113.0145325299",
      "relatedRoutes": ["20路", "22路", "28路", "29路", "55路", "58路", "62路", "68路",
                        "假日旅游专线", "文旅美食专线", "机场2号线专线", "郴安线901路（A线）", "..."],
      "address": "",
      "sameNameNum": 4
    }
  ],
  "buslines": []
}
```

> ⚠️ **没有 `data` 键** —— 站点结果在 `busstations` 里, `buslines` 实测是空数组。
> (旧文档写的是 `data[].relatedRoutes`, 与实际不符。)
> `sameNameNum` = 同名站数量(五岭广场实测 4 个)。
> 上下行各返回一遍 → **同一站会出现两次, 按 (站名, 线路集合) 去重**。

---

## 掌上公交状态码

| status | 含义 |
| --- | --- |
| `"1"` / `1` | 成功 |
| `"-1"` | 业务失败(如城市不支持) |
| 非 JSON 响应 | 多半是 Origin 头错了(47 字节占位串), 或缺 CITYNAME / 线路名不存在回了 HTML 错误页 |

---

# 数据源二:车来了 (chelaile)

## 基本信息

- **Base URL**: `https://web.chelaile.net.cn/api/`
- **方法**: GET
- **必带请求头**:

```
Referer: https://web.chelaile.net.cn/customer_ch5/
User-Agent: Mozilla/5.0 (Linux; Android 13) Mobile MicroMessenger/8.0
```

- **公共参数**(所有接口都带):

```
s=h5&v=9.1.2&vc=1&sign=1&userId=&h5Id=&cityId=<城市ID>&src=app
```

城市 ID 见 `references/cities.json`(如郴州市 = 212)。

## 响应壳

响应被 `**YGKJ` 和 `YGKJ##` 包裹, **先剥壳再解析**:

```python
text.split("**YGKJ", 1)[1].rsplit("YGKJ##", 1)[0]
```

剥完是 `{"jsonr": {"status": "00", "data": {...}}}`,`status != "00"` 就是错, 看 `errmsg`。

---

## bus/cityLineList:线路目录

**响应 data**:

```json
{
  "allLines": {
    "all": [
      {
        "endStopName": "长冲铺",
        "firstTime": "06:30",
        "lastTime": "16:40",
        "lineId": "735217769887",
        "lineName": "1",
        "startStopName": "长冲铺",
        "tagName": "all", "tags": {}, "type": 0
      }
    ]
  }
}
```

> ⚠️ `lineName` **不带"路"后缀**(是 `"1"` 不是 `"1路"`) —— 掌上公交带、车来了不带, 别混。
> `lineId` 是纯数字串。同名线路两个方向各一个 lineId。
> `firstTime` / `lastTime` 是首末班时间, 掌上公交那边没有, 这边有。

---

## bus/line!lineRoute.action:线路站表

**参数**: `cityId=212&lineId=735217769795`

**响应 data**:

```json
{
  "stations": [
    {"distanceToSp": 0, "gpsType": "bd", "lat": 25.761641771384706,
     "lng": 113.02490929887217, "order": 1, "sId": "0735-2118", "sn": "首末站5"}
  ]
}
```

- `order` = 站序(1 基), `sn` = 站名。
- `distanceToSp` = 距上一站的距离(米)。

---

## bus/line!encryptedLineDetail.action:实时车辆(加密)

### cryptoSign 签名

业务参数按**前端顺序**拼, 末尾拼盐值 `qwihrnbtmj`, 取 MD5(小写):

```
lineId=<>&lineName=<>&direction=<>&stationName=<>&nextStationName=<>&lineNo=<>&targetOrder=<>qwihrnbtmj
```

> 签名**对参数顺序敏感, 不能随意重排**。
> 只查线路不带目标站时, 签 `lineId=<>qwihrnbtmj` 即可。
> `lineNo` 只能从解密后的 `line.lineNo` 拿到 —— 所以要拿预测得查两次:
> 第一次不带 targetOrder 拿 `lineNo`, 第二次带全参数拿预测。

### 解密

| 项 | 值 |
| --- | --- |
| 算法 | AES-256-ECB |
| 填充 | PKCS7 |
| 密钥 | `422556651C7F7B2B5C266EED06068230` |
| 密文 | `encryptResult`(base64) |

> ⚠️ **密钥的坑**: 很多资料写「密钥: 422556651C7F7B2B5C266EED06068230(hex)」,
> **这个 hex 标注是错的**。上游 JS 用的是
> `CryptoJS.enc.Utf8.parse("422556651C7F7B2B5C266EED06068230")`
> —— 把这 32 个字符当 **UTF-8 字符串字节**用, 即 **32 字节 = AES-256**。
> 按 hex 解成 16 字节当 AES-128, 会解出一堆乱码。

### 解密后的结构

```json
{
  "buses": [
    {
      "busId": "湘LA8076",
      "licence": "湘LA8076",
      "order": 8,
      "distanceToWaitStn": 15332,
      "delay": 0,
      "lat": 0.0, "lng": 0.0, "speed": 0,
      "state": 0,
      "travels": [
        {
          "arrivalTime": 1793853113940,
          "recommTip": "12:31",
          "travelTime": 3419,
          "order": 39,
          "distance": 0
        }
      ]
    }
  ],
  "line": {
    "name": "2", "direction": 1,
    "startSn": "首末站5", "endSn": "长冲铺",
    "firstTime": "06:45", "lastTime": "21:55",
    "price": "2元", "stationsNum": 39,
    "lineNo": "r67518",
    "segTimes": [["06:45", "21:55"]]
  },
  "stations": [{"order": 1, "sn": "首末站5", "lat": 0.0, "lng": 0.0, "distanceToSp": 0, "sId": "0735-2118"}],
  "tip": {"desc": "还有9分钟，公交出行签个到", "destType": 1},
  "targetOrder": 39,
  "realData": false,
  "predictionText": "发车\n时间",
  "preArrivalTime": "",
  "departLeft": 0
}
```

| 字段 | 含义 |
| --- | --- |
| `buses[].licence` / `busId` | 车牌(两者相同; 部分车队没车牌时用 `busId` 前缀) |
| `buses[].order` | 车辆当前站序 |
| `buses[].distanceToWaitStn` | 到下一站距离(米) |
| `buses[].travels[]` | 到站预测: `arrivalTime`(epoch 毫秒)、`recommTip`(如 "12:31")、`distance` |
| `tip.desc` | **人话提示**, 如「还有9分钟，公交出行签个到」/「车辆即将到站，请准备上车」 |
| `line.price` | 票价 |
| `line.segTimes` | 分段运营时间 |

---

# 城市与区县映射

### cities.json

车来了城市 ID: `{"郴州市": "212", "南宁市": "046", "北京市": "027", ...}`, 共 320 城。

### mygolbs_cities.json

掌上公交城市名数组(离线缓存): `["三亚市", "上海市", ...]`, 共 579 个。

### districts.json

区县 → 地级市: `{"北湖区": "郴州市", "桂阳县": "郴州市", ...}`。

- 只收全国不重名的区县(朝阳区、城区这类重名的没收)。
- **键是官方全名**("桂阳县"), 用户只写"桂阳"时要自己补后缀再查。
- 有些值是 "省直辖县级行政区划"(如万宁市)—— 这是上游城市列表里的真实条目, 别当成映射错误。
- 郴州市下辖 11 个区县: 北湖区、苏仙区、桂阳县、宜章县、永兴县、嘉禾县、临武县、汝城县、桂东县、安仁县、资兴市。

---

# 调用顺序建议

```
查线路实时:
  1. CMD=119 拿线路目录(确认线名 + 方向)   ← 300KB+, 落盘再过滤
  2. CMD=103 拿站表(确认站序)                ← 只有需要到站预测时才要
  3. CMD=104 拿实时车辆(带 STATIONORDER 可拿预测)

查站点:
  CMD=102 → relatedRoutes ∩ → 再走上面 1~3

查直达:
  CMD=102(起点) ∩ CMD=102(终点) → 候选线路 → CMD=103 按站序定方向
```

**全程只用一个数据源**, 两家站名写法不一致, 不合并站表。
