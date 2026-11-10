# images/ —— 景点实景图本地缓存

这个目录存放**景点实景照片**的本地副本，供离线展示、离线生成行程图集使用。

## 它和 `references/image_index.json` 的关系

| 文件 | 内容 | 是否进 git |
|------|------|-----------|
| `references/image_index.json` | 图片索引：城市 → 景点 → `{url, page, title, source, query, local}` | ✅ 进 |
| `references/images/<城市>/<景点>.jpg` | 图片二进制 | ❌ 默认不进（见 `.gitignore`） |

- `url`   —— 图片直链（可热链展示）
- `page`  —— **原始页面 URL**（溯源用：这张图出自哪个站点的哪篇内容）
- `source`—— 来源站点名（百度百科 / 携程 / 去哪儿 / 人民网 / 新浪 …）
- `local` —— 本地缓存路径（下载后才有）

## 怎么用

```bash
# 1) 更新索引（只写链接，不下图）
python3 scripts/fetch_images.py index
python3 scripts/fetch_images.py index --city 郴州

# 2) 下载到本地缓存
python3 scripts/fetch_images.py download --limit 10
python3 scripts/fetch_images.py download --city 郴州 --limit 3

# 3) 把索引里的链接写回景点表（新增「图片」列）
python3 scripts/fetch_images.py sync

# 4) 看索引
python3 scripts/fetch_images.py list --city 郴州
```

## 版权说明

- 图片**版权归原站点/作者所有**，本项目只做检索与索引，并保留原始页面 URL 便于溯源；
- 是否可用于商业用途，需自行确认授权；
- 仓库**默认不提交图片二进制**，只提交索引（链接 + 来源），需要离线图时请本地下载。
