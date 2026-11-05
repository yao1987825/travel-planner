# travel-planner

把 Omarchy 便携工具箱 U 盘上的**旅游攻略与出行**能力封装成一个 AI 技能(Skill)。

模型加载这个技能后,就知道该敲哪条命令、参数怎么传、缺哪些信息该先问 ——
不用每次都现查脚本。

## 功能特性

- 🗺️ **景点规划**:内置景点库(评分/门票/标签/建议游玩时长),自动生成每日行程
- 🍽️ **美食推荐**:内置五城美食价格手册(必吃小吃、推荐店铺、日均预算)
- 🧭 **高德导航**:每日景点间驾车/公交/步行路线,含 ETA 和距离
- 🌤️ **天气预报**:实时天气 + 未来3天 + 穿衣/紫外线/舒适度等生活指数
- 🚄 **火车票**:12306 余票查询(标准库实现,零第三方依赖)
- 📊 **多预算支持**:穷游 / 舒适 / 轻奢三档预算推荐
- 📱 **小红书攻略**:内置 88 篇五城小红书热门推荐,含景点/美食/避坑指南

## 它覆盖什么

| 能力 | 底层命令 |
| --- | --- |
| 按天数/预算/偏好生成每日行程 | `travel plan --profile profile.json` |
| 景点之间的路线(驾车/公交/步行) | `travel nav --from A --to B --mode driving` |
| 目的地实时天气 + 3 天预报 + 生活指数 | `travel weather 郴州` |
| 五城美食价格采集与摘要 | `travel price` |
| 12306 火车票余票 | `train 北京 上海 明天` |

**支持城市**: 郴州、长沙、衡阳、上海、清远(含周边联游)

## 前置条件

- `/usr/local/bin/` 下的 `travel` / `train` 命令;
- `python3` + `requests`;
- 高德 Web 服务 Key,放在**技能目录的 `.env`** 里:

```bash
cp .env.example .env
# 然后编辑 .env,把 AMAP_KEY 填上
```

申请地址: https://lbs.amap.com/dev/key/app (免费,个人开发者每日 5000 次)

体检:

```bash
bash scripts/preflight.sh
```

会逐项检查命令、Python 依赖、Key、脚本完整性,并顺带测一次高德接口连通性。

## 安装

```bash
git clone https://github.com/<你的账号>/travel-planner.git
cd travel-planner
bash scripts/install.sh
```

装到 `~/.config/opencode/skills/travel-planner/`,重启 opencode 后即可被自动发现。

镜像里已经预装过的话,重装是安全的 —— `.env` 和 `data/` 不会被覆盖。

### 其它用法

- **Dify**:把本仓库打包成 zip,用 mini_claw 插件安装;
- **其它认 SKILL.md 的客户端**:把仓库根目录(含 `SKILL.md`、`references/`、`scripts/`)拷进它的技能目录即可;
- **直接跑脚本**:`pip install -r requirements.txt`,然后
  `python3 scripts/amap_nav.py --weather 郴州`。

## 目录结构

```
travel-planner/
├── SKILL.md                        # 技能本体: 入口, 模型主要读这个
├── .env.example                    # 高德 Key 模板(真实 .env 不进仓库)
├── references/                     # 参考资料(模型按需查)
│   ├── cities_attractions.md       # 五城景点库
│   ├── food_guide.md               # 五城美食价格手册
│   ├── money_saving.md             # 全链路省钱攻略
│   ├── xiaohongshu_all_cities.md   # 五城小红书合集(88 篇)
│   ├── xiaohongshu_qingyuan.md     # 清远小红书合集(17 篇)
│   ├── amap_api.md                 # 高德 API 参考
│   ├── travel_schema.md            # 数据库表结构
│   └── travel_api.md               # RESTful API 定义
├── scripts/
│   ├── generate_plan.py            # 行程规划器
│   ├── amap_nav.py                 # 高德客户端(路线 + 天气)
│   ├── food_price_scraper.py       # 美食价格采集
│   ├── preflight.sh                # 环境体检
│   └── install.sh                  # 安装到 opencode 技能目录
└── data/                           # 价格采集结果(运行期数据)
```

## 给 AI 的关键约定

1. **信息不全先问**。天数和城市是硬性必需,其余(预算/风格/体力/同行类型)有默认值,
   但预算和体力直接影响结果,别替用户假设。
2. **公交路线必须带 `city`**(起点所在城市),否则同名地点坐标全错,接口报 30001。
3. **地理编码务必传 `city`**,避免同名地点歧义。
4. **火车票汇报必须带"余票随时变,以 12306 为准"**。
5. **天气查不了历史** —— 高德只能查实时和未来预报,用户问过去要直说。
6. **被排除的景点要说明原因**,别让用户以为漏了。

## 依赖的上游项目

- 高德开放平台: https://lbs.amap.com/ (Web 服务 Key,免费额度每日 5000 次)
- 12306 公开接口(标准库实现,不装第三方包)

## License

MIT
