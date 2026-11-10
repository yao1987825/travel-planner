# images/ —— 景点实景图放置目录

景点实景照片放在这里，按 **`images/<城市>/<景点名>.jpg`** 命名。
放在这里之后，景点表里对应的 GitHub raw 链接就会**自动生效**：

```
https://raw.githubusercontent.com/yao1987825/travel-planner/main/images/丹东/鸭绿江断桥.jpg
```

国内访问 raw 不稳定时，展示链接带代理前缀（`fetch_images.py github-url` 默认就会加）：

```
https://gh-proxy.com/https://raw.githubusercontent.com/yao1987825/travel-planner/main/images/丹东/鸭绿江断桥.jpg
```

## 我该放哪些文件？先看清单

```bash
python3 scripts/fetch_images.py manifest            # 全部城市
python3 scripts/fetch_images.py manifest --city 丹东 # 只看某个城市
```

输出示例：

```
== 丹东 ==
  OK       images/丹东/鸭绿江断桥.jpg
  MISSING  images/丹东/抗美援朝纪念馆.jpg
           备用(原站直链): https://p8.itc.cn/...
           原始页面: https://www.sohu.com/a/474894394_384664
```

- `OK` —— 本地已有这张图；
- `MISSING` —— 还缺，按提示的路径放文件即可；清单里同时给出**原站直链**和
  **原始页面**（可从这里下载，图片版权归原站，索引里也会记来源）。

## 命名规则

景点名里的**特殊字符会被替换成 `_`**，其余原样保留：

| 景点名（景点表里） | 文件名 |
|---|---|
| 东江湖（雾漫小东江） | `images/郴州/东江湖_雾漫小东江_.jpg` |
| 广州塔（小蛮腰） | `images/广州/广州塔_小蛮腰_.jpg` |
| 鸭绿江断桥 | `images/丹东/鸭绿江断桥.jpg` |

扩展名 `.jpg/.jpeg/.png/.webp` 都支持（清单按 `.jpg` 给默认名，实际放别的扩展名也能被识别）。

## 也可以让脚本自动下载

```bash
python3 scripts/fetch_images.py download --limit 999        # 全量下载
python3 scripts/fetch_images.py download --city 丹东 --limit 3
python3 scripts/fetch_images.py github-url                   # 把景点表图片列换成 raw 链接
```

## 图片二进制默认不入库

`.gitignore` 里排除了 `images/*/*.jpg` 等图片文件 —— 仓库只提交**索引**
（`references/image_index.json`，含每张图的原始页面与来源站点）和景点表里的图片链接。

如果决定把图片也提交进仓库（让 raw 链接直接可用），把 `.gitignore` 里那几行删掉再
`git add images/` 即可。

## 版权说明

图片版权归原站点/作者所有。`references/image_index.json` 里保留了每张图的
**原始页面 URL**（`page`）和来源站点（`source`）用于溯源；商用前请自行确认授权。
