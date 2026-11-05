# travel-planner —— 出行助手 Skill(旅游规划 + 公交实时)

把「出行」这件事封装成一个 AI 技能。模型加载后就知道该敲哪条命令、参数怎么传、
返回里哪些字段能直接用、哪些坑要避开。

> 技能名 `travel-planner`;仓库名 `travel-planner`。

## 功能特性

- 🗺️ **景点规划**:内置景点库(评分/门票/标签/建议游玩时长),自动生成每日行程
- 🍽️ **美食推荐**:内置五城美食价格手册(必吃小吃、推荐店铺、日均预算)
- 🧭 **高德导航**:每日景点间驾车/公交/步行路线,含 ETA 和距离
- 🌤️ **天气预报**:实时天气 + 未来3天 + 穿衣/紫外线/舒适度等生活指数
- 🚄 **火车票**:12306 余票查询(标准库实现,零第三方依赖)
- 🚌 **公交实时**:线路实时车辆、**到站预测(还有几站/几分钟)**、站点线路、
  起终点直达线路(按站序判方向)、全城扫 —— 覆盖掌上公交 579 城/县 + 车来了 320 城
- 📊 **多预算支持**:穷游 / 舒适 / 轻奢三档预算推荐
- 📱 **小红书攻略**:内置 88 篇五城小红书热门推荐,含景点/美食/避坑指南

## 配套命令

| 命令 | 干什么 |
| --- | --- |
| `travel` | 旅游攻略 / 行程规划 / 高德导航 / 天气 / 美食价格 |
| `train` | 12306 火车票余票 |
| `bus` | 公交实时车辆 / 到站预测 / 站点线路 / 直达线路 |

```bash
travel plan --profile profile.json --output ./trip   # 生成行程
travel weather 郴州                                    # 实时+3天天气+生活指数
train 郴州 衡阳 明天                                    # 火车票
bus live 郴州 2路 --to 湘南幼专                         # 公交到站预测
bus route 郴州 五岭广场 火车站                          # 直达线路(带方向站数)
```

## 支持城市

| 城市 | 景点数量 | 特色 |
|------|---------|------|
| 郴州 | 10个 | 东江湖(雾漫小东江)、高椅岭、仰天湖草原、莽山 |
| 长沙 | 12个 | 橘子洲、岳麓山、湖南博物院、太平老街 |
| 衡阳 | 9个 | 南岳衡山、石鼓书院、酃湖公园、衡东土菜 |
| 上海 | 13个 | 外滩、豫园、迪士尼、朱家角、武康路 |
| 清远 | 12个 | 古龙峡漂流、连州地下河、千年瑶寨、英西峰林 |

> 美食手册另含广州数据(早茶/粤菜/肠粉等)
> 公交查询覆盖全国(掌上公交 579 城/县 + 车来了 320 城),默认城市郴州市。

## 安装

### A. 工具箱 U 盘 / opencode(有 bash)

```bash
git clone https://github.com/yao1987825/travel-planner.git
cd travel-planner
bash scripts/install.sh
```

装到 `~/.config/opencode/skills/travel-planner/`,重启 opencode 后即可被自动发现。
镜像里已预装的话重装是安全的 —— `.env` 和 `data/` 不会被覆盖。

高德 Key 放在技能目录的 `.env` 里:

```bash
cp .env.example .env
# 编辑 .env, 把 AMAP_KEY 填上
```

申请地址: https://lbs.amap.com/dev/key/app (免费,个人开发者每日 5000 次)

体检:

```bash
bash scripts/preflight.sh
```

### B. RikkaHub(安卓)—— 技能 + 工作区

RikkaHub 的技能是**纯指令包**,没有 shell;但它的**工作区**是一个 proot Linux 环境,
有 shell、python3 和网络。两者配合才能跑实时查询。

> ⚠️ **手机上不能直接用 HTTP 工具查公交**:
> 掌上公交要求请求头带 `Origin: https://h5.mygolbs.com`(不带就回 47 字节占位串),
> 车来了要求 `Referer`(不带回 status=400)。所以必须用工作区里的脚本跑。

**Step 1 · 装技能**

`设置 → 扩展管理 → 技能 → +` → **从文件导入**,选 Release 里的 zip。两个版本任选:

| zip | 内部结构 | 说明 |
| --- | --- | --- |
| `travel-planner-rikkahub.zip` | 顶层一个 `travel-planner/` 目录 | 「压缩了技能文件夹」的形态,多数客户端能认 |
| `travel-planner-rikkahub-flat.zip` | 根目录直接是 `SKILL.md` | 解压出来就是技能目录,适合直接解压到技能目录的客户端 |

导入后如果 RikkaHub 里看不到这个技能,换一个 zip 版本重来 —— 两种解压行为都覆盖到了。

也可以 **从 GitHub 导入**,粘 `https://github.com/yao1987825/travel-planner`
(仓库根目录就有 `SKILL.md`,RikkaHub 会直接读默认分支)。

**Step 2 · 建工作区**

`设置 → 扩展管理 → 工作区 → +` 新建 → 点进去 → **安装 Rootfs** → 切到「文件」标签看目录。

**Step 3 · 在工作区里装技能本体**

聊天页点 `+` → 选工作区卡片 → 绑定,然后直接跟助手说:

> 克隆 https://github.com/yao1987825/travel-planner.git,然后按它的 scripts/setup_workspace.sh 装好,再帮我查一下郴州 2 路到湘南幼专还有几分钟

或者自己在工作区终端里跑:

```bash
bash setup_workspace.sh
```

它会:装 python3/git → clone 仓库 → 检查高德 Key → 跑一次公交自检。

**Step 4 · 给助手启用技能**

长按助手 → 编辑 → 找到「已启用技能」→ 打开 **travel-planner** 开关。

> 高德 Key 在工作区里是个人密钥:写进 `travel-planner/.env`(别提交到公开仓库),
> 或 `export AMAP_KEY=...`。

### 其它用法

- **Dify**:把本仓库打包成 zip,用 mini_claw 插件安装;
- **其它认 SKILL.md 的客户端**:把仓库根目录(含 `SKILL.md`、`references/`、`scripts/`)拷进它的技能目录即可;
- **直接跑脚本**:`pip install -r requirements.txt`,然后
  `python3 scripts/amap_nav.py --weather 郴州`。

### 重新打包 RikkaHub zip

改完技能后:

```bash
python3 scripts/package_rikkahub.py
```

会在 `dist/` 下生成两个 zip(含目录版 + 扁平版),并自动排除 `.env` 和 `data/`。

## 文件结构

```
travel-planner/
├── SKILL.md                      # 技能定义文件(模型主要读这个)
├── .env.example                  # 高德 Key 模板(真实 .env 不进仓库)
├── requirements.txt              # Python 依赖(实际只有 requests)
├── scripts/
│   ├── generate_plan.py          # 核心规划逻辑(景点评分 + 行程生成)
│   ├── amap_nav.py               # 高德地图 API 封装(地理编码 + 路线 + 天气)
│   ├── food_price_scraper.py     # 美食价格采集
│   ├── bus_query.py              # 公交实时查询(纯标准库)
│   ├── preflight.sh              # 环境体检
│   └── install.sh                # 安装到 opencode 技能目录
└── references/
    ├── cities_attractions.md     # 城市景点详细资料
    ├── food_guide.md             # 美食价格手册(早餐/正餐/夜宵/老字号)
    ├── money_saving.md           # 省钱攻略
    ├── travel_api.md             # 天气 API 文档
    ├── travel_schema.md          # 输出数据格式定义
    ├── amap_api.md               # 高德 API 文档
    ├── bus_api.md                # 公交接口文档(掌上公交 + 车来了)
    ├── mygolbs_cities.json       # 掌上公交 579 城(离线缓存)
    ├── bus_cities.json           # 车来了城市 ID(320 城)
    ├── districts.json            # 区县 → 地级市映射
    ├── xiaohongshu_qingyuan.md   # 小红书清远攻略(17篇)
    └── xiaohongshu_all_cities.md # 小红书五城合集(88篇)
```

## 踩过的坑(都修在脚本里了)

| 坑 | 说明 |
| --- | --- |
| 掌上公交 Origin 头 | 必须 `https://h5.mygolbs.com`(无尾斜杠),错了回 47 字节占位串,症状是「永远查不到」 |
| 到站预测要两跳 | 先 `CMD=103` 拿站序,再用站序请求 `CMD=104` 的 `STATIONORDER` |
| 车来了的密钥不是 hex | `422556...` 是 UTF-8 字符串字节(32 字节 → AES-256),按 hex 解成 AES-128 会解出乱码 |
| `CMD=102` 没有 `data` 键 | 站点结果在 `busstations[]` 里 |
| 车来了线路名不带「路」 | 掌上公交是 `2路`,车来了是 `2` |
| `list[].index` 不是站序 | 只覆盖有车的站且不连续,算站数要用 `stationOrder` |
| `status` 有时是数字 | 比较时统一按字符串 |

## 数据源与免责

- 高德地图开放平台: https://lbs.amap.com/ (Web 服务 Key,免费额度每日 5000 次)
- 掌上公交: `https://h5.mygolbs.com` — 579 城/县,给车牌和到站预测
- 车来了: `https://web.chelaile.net.cn` — 320 城,含港澳台与境外
- 12306 公开接口(标准库实现,不装第三方包)

覆盖范围和实时性**取决于第三方数据源**,不是官方承诺。请低频、善意使用。

## License

MIT
