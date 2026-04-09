# 高德地图 Web 服务 API 参考

> 文档版本：v3（2025年9月）  
> API Key 免费注册：https://lbs.amap.com/ → 控制台 → 应用管理 → 添加Key  
> 个人开发者每日免费配额：**5000次/日**

---

## 一、核心接口速查

| 功能 | 接口地址 | 必填参数 |
|------|---------|---------|
| 地理编码（地名→坐标） | `GET https://restapi.amap.com/v3/geocode/geo` | key, address |
| 驾车路线规划 | `GET https://restapi.amap.com/v3/direction/driving` | key, origin, destination |
| 公交路线规划 | `GET https://restapi.amap.com/v3/direction/transit/integrated` | key, origin, destination, city |
| 步行路线规划 | `GET https://restapi.amap.com/v3/direction/walking` | key, origin, destination |

---

## 二、地理编码 `GET /v3/geocode/geo`

将文字地址/地点名转为经纬度坐标。

### 请求示例

```
https://restapi.amap.com/v3/geocode/geo?key=你的KEY&address=上海外滩&city=上海
```

### 响应字段

```json
{
  "status": "1",
  "count": "1",
  "geocodes": [{
    "location": "121.490317,31.240124",
    "province": "上海市",
    "city": "上海市",
    "district": "黄浦区",
    "formatted_address": "上海市黄浦区外滩"
  }]
}
```

### ⚠️ 注意事项
- `location` 格式为 **经度,纬度**（注意顺序）
- 建议同时传入 `city` 参数提高准确性

---

## 三、驾车路线 `GET /v3/direction/driving`

### 请求参数

| 参数 | 必填 | 说明 | 示例 |
|------|------|------|------|
| `key` | ✅ | API 密钥 | `key=xxx` |
| `origin` | ✅ | 起点坐标 | `origin=121.49,31.24` |
| `destination` | ✅ | 终点坐标 | `destination=121.48,31.22` |
| `strategy` | | 路线策略（默认0） | 见下方策略表 |
| `extensions` | | base=基本/all=详细 | `base` |
| `waypoints` | | 途经点，最多16个 | `lng1,lat1;lng2,lat2` |

### 驾车策略（strategy 参数）

| 值 | 含义 |
|----|------|
| `0` | 速度优先（默认） |
| `1` | 费用优先（走收费道路少） |
| `2` | 距离优先（最短距离） |
| `3` | 不走快速路 |
| `4` | 躲避拥堵 |
| `5` | 不走高速 |
| `6` | 躲避拥堵且不走高速 |

### 响应字段（精简）

```json
{
  "status": "1",
  "route": {
    "paths": [{
      "distance": 5432,
      "time": 1234,
      "steps": [
        { "road_name": "延安高架路", "instruction": "沿延安高架路向东..." },
        { "road_name": "外滩隧道", "instruction": "进入外滩隧道" }
      ]
    }],
    "cost": { "toll": 10, "oil": 15 }
  }
}
```
- `distance`：路线总距离（**米**）
- `time`：预估时间（**秒**）
- `toll`：通行费（元）

---

## 四、公交路线 `GET /v3/direction/transit/integrated`

城内公交/地铁换乘方案。

### 请求参数

| 参数 | 必填 | 说明 |
|------|------|------|
| `key` | ✅ | API 密钥 |
| `origin` | ✅ | 起点坐标 |
| `destination` | ✅ | 终点坐标 |
| `city` | ✅ | 起点所在城市名 |
| `strategy` | | 策略（默认0） |
| `nightflag` | | 是否含夜班车（0/1） |

### 公交策略（strategy 参数）

| 值 | 含义 |
|----|------|
| `0` | 最快捷模式（默认） |
| `1` | 最经济模式（最少换乘） |
| `2` | 最少换乘 |
| `3` | 最少步行 |
| `4` | 最舒适模式 |
| `5` | 不乘地铁 |

### 响应字段（精简）

```json
{
  "status": "1",
  "route_transits": [{
    "distance": 8500,
    "duration": 2100,
    "cost": 4,
    "segments": [{
      "walk": { "distance": 320 },
      "bus": {
        "buslines": [{ "name": "地铁1号线", "station_count": 3 }]
      }
    }]
  }]
}
```
- `duration`：总耗时（秒）
- `cost`：票价（元）

---

## 五、步行路线 `GET /v3/direction/walking`

### 请求参数

| 参数 | 必填 | 说明 |
|------|------|------|
| `key` | ✅ | API 密钥 |
| `origin` | ✅ | 起点坐标 |
| `destination` | ✅ | 终点坐标 |

### 响应字段（精简）

```json
{
  "status": "1",
  "paths": [{
    "distance": 1250,
    "time": 895,
    "steps": [
      { "road_name": "南京东路", "instruction": "沿南京东路向东步行" }
    ]
  }]
}
```

---

## 六、在旅游规划中的集成方式

### 场景 1：景点间逐段导航

```python
# 根据生成的行程 JSON，对每个景点间查导航
for day in plan["days"]:
    for i, item in enumerate(day["items"][:-1]):
        next_item = day["items"][i + 1]
        route = amap.driving(
            origin=amap.geocode(item["name"], city),
            destination=amap.geocode(next_item["name"], city)
        )
        print(f"{item['name']} → {next_item['name']}: {route.distance_km}km")
```

### 场景 2：批量行程优化

```
python amap_nav.py --plan travel_plan.json --mode transit --city 上海 --output nav_result.json
```

### 场景 3：行程结束后汇总

```
🧮 自动穷举 TSP 最优顺序（≤8景点时）
📍 计算每段距离、耗时、费用
📊 输出完整导航汇总表
```

---

---

## 七、天气查询 API

### 基础信息
| 项目 | 内容 |
|------|------|
| 接口地址 | `https://restapi.amap.com/v3/weather/weatherInfo` |
| 请求方式 | GET |
| 数据格式 | JSON |
| 每日免费配额 | 5000 次（个人开发者） |

### 请求参数
| 参数名 | 必填 | 说明 |
|--------|------|------|
| `key` | ✅ | 高德 API 密钥 |
| `city` | ✅ | 城市中文名、citycode 或 adcode，如 `上海`、`郴州`、`430100` |
| `extensions` | ✅ | `base`=实时天气，`all`=实时+未来3天+生活指数 |
| `output` | | JSON（默认）或 XML |

### 返回字段（实时天气 base）
| 字段 | 含义 | 示例 |
|------|------|------|
| `weather` | 天气现象 | `"晴"` |
| `temperature` | 实时温度（℃） | `"23"` |
| `winddirection` | 风向 | `"东南风"` |
| `windpower` | 风力等级 | `"3"` |
| `humidity` | 湿度（%） | `"40"` |
| `report_time` | 发布时间 | `"2026-04-09 15:30:00"` |

### 返回字段（预报天气 extensions=all）
| 字段 | 含义 |
|------|------|
| `date` | 日期（YYYY-MM-DD） |
| `dayweather` / `nightweather` | 白天/夜间天气 |
| `daytemp` / `nighttemp` | 白天/夜间温度 |
| `daywind` / `nightwind` | 白天/夜间风向 |
| `daypower` / `nightpower` | 白天/夜间风力等级 |

### 生活指数（extensions=all 时）
| 指数名 | 说明 |
|--------|------|
| 穿衣指数 | 根据温度建议穿着 |
| 紫外线指数 | 防晒建议 |
| 舒适度指数 | 体感舒适度 |
| 运动指数 | 户外运动建议 |
| 洗车指数 | 洗车适宜度 |

### 示例请求
```
# 实时天气
https://restapi.amap.com/v3/weather/weatherInfo?key=密钥&city=郴州&extensions=base

# 实时+3天预报+生活指数
https://restapi.amap.com/v3/weather/weatherInfo?key=密钥&city=长沙&extensions=all
```

---

## 八、免费 Key 申请步骤

1. 访问 https://lbs.amap.com/
2. 注册账号并完成实名认证（必须）
3. 进入「控制台」→「应用管理」→「添加应用」
4. 添加 Key（类型选 **Web服务**）
5. 将 Key 填入 `.env` 文件：`AMAP_KEY=你的密钥`

### ⚠️ 重要限制

| 限制项 | 免费版额度 |
|--------|-----------|
| 每日调用量 | 5000次/日 |
| QPS（并发） | 5次/秒 |
| Key 有效期 | 永久有效 |
| 计费 | 免费（超配额后按量计费） |

> **提示**：行程规划场景，每日调用量足够（每次查询约3-5个请求/景点）
