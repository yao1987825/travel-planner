# 旅游攻略规划 — API 接口定义参考

## 基础约定

- Base URL: `https://api.travel-planner.example.com/v1`
- 认证: `Authorization: Bearer <token>`
- 响应格式: `Content-Type: application/json`
- 时间格式: ISO 8601 (`YYYY-MM-DD`, `HH:MM:SS`)
- 错误结构:
  ```json
  { "code": 40001, "message": "参数缺失: travel_days", "data": null }
  ```

---

## 1. 创建用户旅行偏好

**POST** `/travel/profile`

### 请求体

```json
{
  "user_id": "u_abc123",
  "nickname": "小明",
  "dest_city": "上海",
  "origin_city": "北京",
  "depart_date": "2026-05-01",
  "return_date": "2026-05-04",
  "travel_days": 3,
  "budget_cny": 3000,
  "budget_level": "mid",
  "travel_style": ["文化", "美食", "购物"],
  "group_type": "couple",
  "mobility": "mid"
}
```

### 响应

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "profile_id": 101,
    "user_id": "u_abc123",
    "created_at": "2026-04-09T16:00:00Z"
  }
}
```

---

## 2. 生成旅游计划

**POST** `/travel/plan/generate`

> 核心接口：根据用户偏好自动生成完整的多日行程计划。

### 请求体

```json
{
  "profile_id": 101,
  "options": {
    "prefer_free": false,
    "include_disney": false,
    "avoid_crowded": false,
    "daily_start_time": "09:00",
    "daily_end_time": "21:00"
  }
}
```

### 响应

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "plan_id": 501,
    "title": "上海3日精华游（文化+美食）",
    "city": "上海",
    "total_days": 3,
    "est_total_cost": 2480.00,
    "ai_summary": "行程覆盖外滩、豫园、田子坊等经典文化地标，融合上海本帮菜美食体验，适合情侣出行。由于时间有限，迪士尼、朱家角等需单独整天的景点未纳入本次行程。",
    "highlights": ["外滩", "豫园", "上海博物馆", "新天地", "田子坊", "武康路"],
    "skipped": [
      { "name": "迪士尼乐园", "reason": "需单独一天，时间不足" },
      { "name": "朱家角古镇", "reason": "距市区较远，3日行程不建议安排" }
    ],
    "days": [
      {
        "day_index": 1,
        "date": "2026-05-01",
        "theme": "外滩老上海·黄浦区精华",
        "breakfast_tip": "城隍庙小吃：南翔馒头店",
        "lunch_tip": "老正兴菜馆（本帮菜）",
        "dinner_tip": "外滩附近餐厅，边吃边看夜景",
        "hotel_area": "人民广场/外滩附近",
        "budget_estimate": 820.00,
        "items": [
          {
            "seq": 1, "type": "attraction",
            "name": "豫园", "visit_time": "09:00",
            "duration_h": 2.5, "est_cost": 40,
            "transport_to": "地铁10号线→豫园站"
          },
          {
            "seq": 2, "type": "meal",
            "name": "南翔馒头店（午餐）", "visit_time": "12:00",
            "duration_h": 1.0, "est_cost": 80,
            "transport_to": "步行5分钟"
          },
          {
            "seq": 3, "type": "attraction",
            "name": "上海博物馆", "visit_time": "14:00",
            "duration_h": 3.0, "est_cost": 0,
            "transport_to": "地铁1号线→人民广场站"
          },
          {
            "seq": 4, "type": "attraction",
            "name": "外滩（夜景）", "visit_time": "18:30",
            "duration_h": 2.0, "est_cost": 0,
            "transport_to": "步行20分钟或打车"
          }
        ]
      }
    ]
  }
}
```

---

## 3. 查询旅游计划详情

**GET** `/travel/plan/{plan_id}`

### 路径参数

| 参数      | 类型   | 说明   |
|-----------|--------|--------|
| `plan_id` | bigint | 计划ID |

### 响应（同上 `data` 结构）

---

## 4. 调整/更新计划

**PATCH** `/travel/plan/{plan_id}`

### 请求体（仅传需要修改的字段）

```json
{
  "remove_attractions": ["迪士尼乐园"],
  "add_attractions": ["上海科技馆"],
  "update_days": 4,
  "update_budget": 4000
}
```

### 响应

```json
{
  "code": 0,
  "message": "计划已重新生成",
  "data": { "plan_id": 501, "version": 2 }
}
```

---

## 5. 获取城市景点列表

**GET** `/attractions`

### 查询参数

| 参数        | 类型     | 必填 | 说明                              |
|-------------|----------|------|-----------------------------------|
| `city`      | string   | ✅   | 目的地城市                        |
| `category`  | string   |      | 分类过滤，多个逗号分隔             |
| `max_price` | number   |      | 最高票价（元），0=只看免费        |
| `min_rating`| number   |      | 最低评分                          |
| `page`      | int      |      | 页码，默认1                       |
| `page_size` | int      |      | 每页数量，默认20                  |

### 响应

```json
{
  "code": 0,
  "data": {
    "total": 13,
    "items": [
      {
        "id": 1, "name": "外滩", "category": "文化",
        "district": "黄浦区", "ticket_price": 0,
        "rating": 4.8, "avg_duration_h": 2.0,
        "tags": ["必去", "夜景", "免费"],
        "description": "上海标志性地标，可欣赏浦东天际线。"
      }
    ]
  }
}
```

---

## 6. 删除计划

**DELETE** `/travel/plan/{plan_id}`

### 响应

```json
{ "code": 0, "message": "已删除", "data": null }
```

---

## 错误码表

| code  | 含义                      |
|-------|---------------------------|
| 0     | 成功                      |
| 40001 | 请求参数缺失或格式错误    |
| 40101 | 未授权，token 无效或过期  |
| 40401 | 资源不存在                |
| 50001 | 服务器内部错误            |
| 50002 | AI 规划引擎暂时不可用     |
