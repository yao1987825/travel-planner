# travel-planner —— 出行助手 Skill（行程规划 + 公共交通 + 天气）

把「出行」这件事封装成一个 AI 技能：模型加载后就知道该敲哪条命令、参数怎么传、
返回里哪些字段能直接用、哪些坑要避开。

> 技能名 `travel-planner`；仓库名 `travel-planner`。
> **零第三方依赖、零 API Key** —— 装好 python3 就能跑。

## 核心思路

一次出行不是四个互不相干的功能，而是**一条由若干段组成的旅程**：

```
出发地 ──[火车/高铁]──→ 到达站 ──[地铁/公交]──→ 目的地 ──[步行]──→ 景点
                            ↑                    ↑
                    首班/末班车卡点        天气、预警、票价
```

所以主入口是 **`transit.py journey`**：它把 12306 火车票、55 城地铁换乘、579 城公交实时、
中国天气网天气预警**串成一条带时刻的时间线**，并做跨方式校验（换乘缓冲、末班车卡点、天气预警）。

## 功能特性

- 🧭 **整段出行编排**: 火车 + 地铁 + 公交 + 天气 拼成一条时间线，支持 `--arrive-by` 反推
- 🚄 **火车票**: 12306 余票/时刻/席别（标准库实现）
- 🚇 **地铁换乘**: 55 城，逐站时刻、换乘次数、票价、**各方向首末班车时刻表**（地铁通 metroman.cn）
- 🚌 **公交实时**: 线路实时车辆、**到站预测（还有几站/几分钟）**、站点线路、直达线路、全城扫
- 🌤️ **天气**: 实况 + AQI + **生活指数（穿衣/旅游/运动/紫外线…）** + 气象预警 + 7 天预报 + 逐小时（中国天气网）
- 🗺️ **景点规划**: 内置景点库（评分/门票/标签/游玩时长），自动生成每日行程
- 🍽️ **美食推荐**: 内置多城美食价格手册（含本地实测）
- 📊 **多预算支持**: 穷游 / 舒适 / 轻奢
- 📱 **小红书攻略**: 内置 88 篇多城热门推荐，含避坑

## 配套命令

`install.sh` 会在 PATH 上装好 wrapper，装完直接敲：

| 命令 | 干什么 |
| --- | --- |
| `travel` | **统一入口**，下面四个都是它的子命令 |
| `journey` | **整段出行时间线**（火车+地铁+公交+天气） |
| `metro` | 地铁换乘 / 线路站点 / 车站首末班车 |
| `bus` | 公交实时车辆 / 到站预测 / 站点线路 / 直达线路 |
| `train` | 12306 火车票余票 |

```bash
# 统一入口
travel metro plan 上海 徐家汇 陆家嘴
travel bus live 郴州 2路 --to 湘南幼专
travel weather live 郴州
travel train 郴州 长沙 明天
travel journey --from 郴州西 --to 陆家嘴 --date 明天 --weather
travel plan --profile profile.json --output ./trip
travel price 上海                       # 本地价格参考（只读，不联网采集）

# 不用 wrapper 时，直接调脚本，效果相同
python3 scripts/transit.py journey --from 郴州西 --to 陆家嘴 --date 明天 --weather
python3 scripts/metro_query.py plan 上海 徐家汇 陆家嘴
python3 scripts/bus_query.py live 郴州 2路 --to 湘南幼专
python3 scripts/weather_query.py live 郴州
```

> `travel price` 是**只读查询**本地价格数据；`python3 scripts/food_price_scraper.py`
> 才是采集，会覆盖 `data/` 下的价格文件。

## 支持城市

| 城市 | 景点数量 | 特色 |
|------|---------|------|
| 郴州 | 10个 | 东江湖(雾漫小东江)、高椅岭、仰天湖草原、莽山 |
| 长沙 | 12个 | 橘子洲、岳麓山、湖南博物院、太平老街 |
| 衡阳 | 9个 | 南岳衡山、石鼓书院、酃湖公园、衡东土菜 |
| 上海 | 13个 | 外滩、豫园、迪士尼、朱家角、武康路 |
| 清远 | 12个 | 古龙峡漂流、连州地下河、千年瑶寨、英西峰林 |
| 丹东 | 5个 | 鸭绿江断桥、安东老街、抗美援朝纪念馆、月亮岛 |

> `generate_plan.py` 的景点库直接解析 `references/cities_attractions.md`，
> 覆盖郴州/长沙/衡阳/上海/清远/丹东（及广州）；「鸭绿江/鸭绿江流域/中朝边境」会自动映射到丹东。
> 清远详细攻略另见 `references/xiaohongshu_qingyuan.md`。
> 美食手册另含广州数据（早茶/粤菜/肠粉等）
> **地铁**覆盖 55 城；**公交**覆盖全国（掌上公交 579 城/县 + 车来了 320 城）。
> **公交查询没有默认城市**——用户没说城市时，AI 会先反问「在哪个城市」，命令本身也会报错提示补城市。

## 安装

### A. 工具箱 U 盘 / opencode（bash 环境）

```bash
git clone https://github.com/yao1987825/travel-planner.git
cd travel-planner
bash scripts/install.sh
```

装到 opencode 的技能目录（`~/.opencode/skills/travel-planner/`，没有则用
`~/.config/opencode/skills/`），并在 PATH 上（优先 `~/.local/bin`）装好
`travel` / `journey` / `metro` / `bus` / `train` 五个命令。
重启 opencode 后技能即可被自动发现。
镜像里已预装的话重装是安全的 —— `data/` 不会被覆盖；
如果技能目录是指向仓库的符号链接（开发模式），install.sh 不会覆盖任何文件。

体检：

```bash
bash scripts/preflight.sh
```

> **不需要申请任何 API Key**（原来的高德 Key 已随高德服务一起移除）。
> 也不需要 `pip install` —— 核心脚本零第三方依赖。

### B. RikkaHub（安卓）—— 技能 + 工作区

RikkaHub 的技能是**纯指令包**，没有 shell；但它的**工作区**是一个 proot Linux 环境，
有 shell、python3 和网络。两者配合才能跑实时查询。

> ⚠️ **手机上不能直接用 HTTP 工具查公交**：
> 掌上公交要求请求头带 `Origin: https://h5.mygolbs.com`（不带就回 47 字节占位串），
> 车来了要求 `Referer`（不带回 status=400）。所以必须用工作区里的脚本跑。

**Step 1 · 装技能**

`设置 → 扩展管理 → 技能 → +` → **从文件导入**，选 Release 里的 zip。两个版本任选：

| zip | 内部结构 | 说明 |
| --- | --- | --- |
| `travel-planner-rikkahub.zip` | 顶层一个 `travel-planner/` 目录 | 「压缩了技能文件夹」的形态，多数客户端能认 |
| `travel-planner-rikkahub-flat.zip` | 根目录直接是 `SKILL.md` | 解压出来就是技能目录，适合直接解压到技能目录的客户端 |

也可以 **从 GitHub 导入**，粘 `https://github.com/yao1987825/travel-planner`
（仓库根目录就有 `SKILL.md`）。

**Step 2 · 建工作区**

`设置 → 扩展管理 → 工作区 → +` 新建 → 点进去 → **安装 Rootfs** → 切到「文件」标签看目录。

**Step 3 · 在工作区里装技能本体**

聊天页点 `+` → 选工作区卡片 → 绑定，然后直接跟助手说：

> 克隆 https://github.com/yao1987825/travel-planner.git，按 scripts/setup_workspace.sh 装好，
> 再帮我查一下郴州 2 路到湘南幼专还有几分钟，我明天坐高铁去上海，能赶上吗

或者自己在工作区终端里跑：

```bash
bash setup_workspace.sh
```

**Step 4 · 给助手启用技能**

长按助手 → 编辑 → 找到「已启用技能」→ 打开 **travel-planner** 开关。

## 目录结构

```
travel-planner/
├── SKILL.md                    # 技能主文件（出行主线）
├── scripts/
│   ├── transit.py              # ★ 跨方式出行编排（主入口）
│   ├── travel.py               # ★ 统一命令入口（travel <子命令>）
│   ├── train_cli.py            # 12306 命令行入口
│   ├── metro_query.py          # 地铁查询
│   ├── metroman/               #   地铁数据层（纯标准库）
│   ├── weather_query.py        # 天气（中国天气网）
│   ├── bus_query.py            # 公交实时（掌上公交 + 车来了）
│   ├── train_store.py          # 12306 火车票
│   ├── generate_plan.py        # 行程规划
│   ├── validate_data.py        # ★ 参考数据校验（格式/来源/重复项/非法票价/图片链接）
│   ├── fetch_images.py         # ★ 景点实景图索引 / 本地缓存
│   ├── food_price_scraper.py   # 美食价格采集（--query 只读查询）
│   ├── install.sh / preflight.sh / setup_workspace.sh / package_rikkahub.py
├── references/
│   ├── data_schema.md          # ★★ 数据规范（新增城市/景点/美食看这里）
│   ├── transit_link.md         # ★ 多方式联动规则
│   ├── metro_api.md            # 地铁接口逆向
│   ├── weather_api.md          # 天气接口逆向
│   ├── bus_api.md              # 公交接口说明
│   ├── cities_attractions.md / food_guide.md / money_saving.md
│   ├── travel_data.json        # ★ 城市注册表（别名/地铁覆盖/来源/风格词表）
│   ├── image_index.json        # ★ 图片索引（直链 + 原始页面 + 来源站点）
│   ├── images/                 #   图片本地缓存（默认不入 git）
│   ├── weather_cities.json     # 天气城市码（3137 个城市/区县）
│   └── station_cache.json      # 12306 车站电报码表（3407 站，随技能分发）
├── tests/
│   └── test_journey.py         # 端到端冒烟测试
└── data/                       # 运行时数据（价格监控 workflow 会更新；车站表刷新副本在此，已 gitignore）
```

## 加数据（持续维护）

参考数据全部在 `references/` 下，**加城市/景点/美食只改数据文件，不改脚本**：

```bash
# 1. 按规范写数据 → references/data_schema.md
#    景点表：references/cities_attractions.md
#    美食表：references/food_guide.md
#    注册城市：references/travel_data.json（别名/地铁覆盖/来源/核实年份）
# 2. 校验（必须 0 error）
python3 scripts/validate_data.py
# 3. 跑测试
python3 tests/test_journey.py --offline
```

三条铁律：**不编造**（拿不准写「待核实」，不算「免费」）、**有出处**（来源登记在 `travel_data.json`）、
**单一事实源**（景点数据只放 md，代码里不再内置副本）。

## 实景图片

景点不只有文字，还能「看见」：

```bash
# 检索实景图（真实照片，来自百度百科/携程/去哪儿/人民网/新浪等）
python3 scripts/fetch_images.py index --city 郴州
# 把图片链接写回景点表的「图片」列
python3 scripts/fetch_images.py sync
# 需要离线图时下载到 references/images/<城市>/
python3 scripts/fetch_images.py download --limit 10
```

- 索引在 `references/image_index.json`：每张图都带**原始页面 URL** 和来源站点，便于溯源；
- 景点表新增可选的「图片」列 `![景点名](URL)`，生成行程时会输出实景图链接，并产出
  `travel_gallery.md` 图集；
- 图片版权归原作者/站点所有，仓库只提交索引、不提交图片二进制。

## 测试

```bash
python3 tests/test_journey.py            # 全部（需要网络）
python3 tests/test_journey.py --offline  # 只跑不联网的解析逻辑
```

端到端跑通四条数据源（公交 / 地铁 / 天气 / 12306）和跨方式编排，共 24 项断言。
CI 里由 `.github/workflows/test.yml` 每次推送自动执行。

## 数据来源与逆向

| 能力 | 来源 | 方式 |
|------|------|------|
| 地铁 | 地铁通 metroman.cn（55 城） | 服务端渲染页面 + 页面内嵌 JSON，解析提取 |
| 天气 | 中国天气网 weather.com.cn | `d1.weather.com.cn` 的 JSONP 接口 |
| 火车票 | 12306 | 官方公开查询接口 |
| 公交 | 掌上公交 + 车来了 | 私有接口（含 AES 解密） |
| 景点/美食 | 本地参考库 | 静态数据 |

逆向细节见 `references/metro_api.md`、`references/weather_api.md`、`references/bus_api.md`。

## 注意事项

- 地铁换乘方案为**推荐时刻表**结果，不含步行、接驳、安检进站时间；
- 火车票**只查不购**，余票随时变，以 12306 为准；
- 公交与天气数据来自第三方源，**覆盖范围和实时性取决于对方**；
- **驾车与精确步行路线已移除**（原高德服务下线），市内出行用地铁/公交，末段步行请用地图 App；
- 请低频、善意使用接口。

## License

MIT
