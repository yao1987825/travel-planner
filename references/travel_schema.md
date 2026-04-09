# 旅游攻略规划 — 数据库表结构参考

## 一、核心表结构（MySQL / PostgreSQL 均适用）

### 1. 用户旅行偏好表 `user_travel_profiles`

```sql
CREATE TABLE user_travel_profiles (
    id            BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id       VARCHAR(64)   NOT NULL UNIQUE COMMENT '用户唯一标识',
    nickname      VARCHAR(100)  COMMENT '昵称',
    budget_level  ENUM('budget','mid','luxury') DEFAULT 'mid' COMMENT '预算档次',
    budget_cny    DECIMAL(10,2) COMMENT '总预算（元）',
    travel_days   TINYINT       COMMENT '出行天数',
    depart_date   DATE          COMMENT '出发日期',
    return_date   DATE          COMMENT '返回日期',
    origin_city   VARCHAR(50)   COMMENT '出发城市',
    dest_city     VARCHAR(50)   COMMENT '目的地城市',
    travel_style  JSON          COMMENT '旅行风格，如 ["文化","美食","购物"]',
    group_type    ENUM('solo','couple','family','friends') DEFAULT 'solo' COMMENT '出行类型',
    mobility      ENUM('high','mid','low') DEFAULT 'mid' COMMENT '体力/行动力（影响每日景点数量）',
    created_at    TIMESTAMP     DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
```

---

### 2. 城市景点库 `attractions`

```sql
CREATE TABLE attractions (
    id              BIGINT PRIMARY KEY AUTO_INCREMENT,
    city            VARCHAR(50)   NOT NULL COMMENT '所在城市',
    name            VARCHAR(200)  NOT NULL COMMENT '景点名称',
    category        VARCHAR(50)   COMMENT '分类：文化/自然/美食/购物/夜景/亲子',
    district        VARCHAR(50)   COMMENT '区域/街区',
    lat             DECIMAL(9,6)  COMMENT '纬度',
    lng             DECIMAL(9,6)  COMMENT '经度',
    open_time       VARCHAR(100)  COMMENT '开放时间，如 09:00-17:00',
    avg_duration_h  DECIMAL(3,1)  COMMENT '平均游览时长（小时）',
    ticket_price    DECIMAL(8,2)  COMMENT '票价（元），0=免费',
    rating          DECIMAL(2,1)  COMMENT '评分 0-5',
    crowd_level     ENUM('low','mid','high') COMMENT '人流量',
    tags            JSON          COMMENT '标签，如 ["网红打卡","世界遗产","必去"]',
    description     TEXT          COMMENT '景点简介',
    tips            TEXT          COMMENT '游玩贴士',
    image_url       VARCHAR(500)  COMMENT '封面图',
    priority        TINYINT       DEFAULT 5 COMMENT '推荐优先级 1-10',
    is_active       TINYINT(1)    DEFAULT 1
);
```

---

### 3. 每日行程计划表 `itinerary_days`

```sql
CREATE TABLE itinerary_days (
    id              BIGINT PRIMARY KEY AUTO_INCREMENT,
    plan_id         BIGINT        NOT NULL COMMENT '关联 travel_plans.id',
    day_index       TINYINT       NOT NULL COMMENT '第几天（1-N）',
    date            DATE          COMMENT '具体日期',
    theme           VARCHAR(100)  COMMENT '当天主题，如 "外滩老上海一日"',
    breakfast_tip   VARCHAR(200)  COMMENT '早餐建议',
    lunch_tip       VARCHAR(200)  COMMENT '午餐建议',
    dinner_tip      VARCHAR(200)  COMMENT '晚餐建议',
    hotel_area      VARCHAR(100)  COMMENT '当晚住宿区域建议',
    transport_tip   TEXT          COMMENT '交通贴士',
    budget_estimate DECIMAL(8,2)  COMMENT '当天预估花费（元）',
    notes           TEXT          COMMENT '备注',
    INDEX idx_plan_day (plan_id, day_index)
);
```

---

### 4. 行程景点明细表 `itinerary_items`

```sql
CREATE TABLE itinerary_items (
    id              BIGINT PRIMARY KEY AUTO_INCREMENT,
    day_id          BIGINT        NOT NULL COMMENT '关联 itinerary_days.id',
    attraction_id   BIGINT        COMMENT '关联 attractions.id，null=自由活动',
    seq             TINYINT       NOT NULL COMMENT '当天顺序',
    visit_time      TIME          COMMENT '建议到达时间',
    duration_h      DECIMAL(3,1)  COMMENT '建议停留时长（小时）',
    transport_to    VARCHAR(200)  COMMENT '前往方式，如 "地铁2号线→人民广场站"',
    est_cost        DECIMAL(8,2)  COMMENT '该项预估花费',
    type            ENUM('attraction','meal','transport','accommodation','free') DEFAULT 'attraction',
    custom_name     VARCHAR(200)  COMMENT '自定义项目名（非景点时使用）',
    notes           TEXT          COMMENT '备注',
    INDEX idx_day_seq (day_id, seq)
);
```

---

### 5. 旅行计划主表 `travel_plans`

```sql
CREATE TABLE travel_plans (
    id              BIGINT PRIMARY KEY AUTO_INCREMENT,
    profile_id      BIGINT        NOT NULL COMMENT '关联 user_travel_profiles.id',
    title           VARCHAR(200)  COMMENT '计划标题',
    city            VARCHAR(50)   COMMENT '目的地',
    total_days      TINYINT       COMMENT '总天数',
    total_budget    DECIMAL(10,2) COMMENT '总预算',
    est_total_cost  DECIMAL(10,2) COMMENT '规划预估总花费',
    highlights      JSON          COMMENT '亮点景点列表',
    skipped         JSON          COMMENT '因时间/偏好跳过的景点及原因',
    ai_summary      TEXT          COMMENT 'AI 生成的行程总结',
    status          ENUM('draft','confirmed','completed') DEFAULT 'draft',
    created_at      TIMESTAMP     DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
```

---

## 二、索引建议

```sql
-- 景点查询加速
CREATE INDEX idx_attractions_city_cat ON attractions (city, category, priority DESC);
CREATE INDEX idx_attractions_rating   ON attractions (city, rating DESC);

-- 计划查询加速
CREATE INDEX idx_plans_profile        ON travel_plans (profile_id, status);
```

---

## 三、示例数据（上海）

```sql
INSERT INTO attractions (city,name,category,district,avg_duration_h,ticket_price,rating,crowd_level,tags,priority) VALUES
('上海','外滩','文化','黄浦区',2.0,0,4.8,'high','["必去","夜景","免费"]',10),
('上海','东方明珠塔','地标','浦东新区',2.0,189,4.5,'high','["地标","观光"]',9),
('上海','豫园','文化','黄浦区',2.5,40,4.6,'high','["历史","园林","购物"]',9),
('上海','田子坊','文化','黄浦区',1.5,0,4.4,'mid','["文艺","购物","免费"]',8),
('上海','新天地','购物','黄浦区',2.0,0,4.3,'mid','["购物","餐饮","夜生活"]',8),
('上海','上海博物馆','文化','黄浦区',3.0,0,4.7,'mid','["历史","艺术","免费"]',8),
('上海','迪士尼乐园','亲子','浦东新区',10.0,535,4.9,'high','["亲子","主题乐园"]',10),
('上海','朱家角古镇','文化','青浦区',4.0,0,4.5,'mid','["古镇","水乡","免费"]',7),
('上海','南京路步行街','购物','黄浦区',2.0,0,4.2,'high','["购物","免费"]',7),
('上海','上海科技馆','亲子','浦东新区',3.0,60,4.6,'mid','["科技","亲子"]',7),
('上海','思南公馆','文化','黄浦区',1.5,0,4.3,'low','["文艺","建筑","免费"]',6),
('上海','武康路','文化','徐汇区',1.5,0,4.4,'mid','["网红","建筑","免费"]',7),
('上海','上海自然博物馆','亲子','静安区',3.0,55,4.7,'mid','["科普","亲子"]',7);
```
