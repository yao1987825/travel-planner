# 图片与描述图集

行程生成器现有景点图集以图片为主，景点描述和美食/店铺配图展示不够统一。这个扩展保持“图片 + 描述”为核心，不展示预约状态或订单信息。

## 使用方式

先按原有方式生成行程 JSON：

```bash
python3 scripts/generate_plan.py --profile profile.json --output ./trip
```

然后生成包含景点图片、描述及精选美食/店铺内容的图集：

```bash
python3 scripts/generate_gallery.py --plan ./trip/travel_plan.json
```

输出 `./trip/travel_gallery.md`。已有景点图片会从行程读取，描述优先取景点的介绍/实用提示；美食、推荐店铺和实测打卡内容从 `references/visual_stories.json` 读取。若同名景点有更完整的精选描述，会优先采用精选内容。

## 添加图片和描述

在 `visual_stories.json` 的 `cities` 下按城市添加内容。`kind` 只是内容类别，不代表预约或交易状态。图片地址可以是可访问的图片 URL，也可以是项目中的相对路径；图片需要真实、可追溯，描述应由维护者根据可靠资料或亲身体验撰写。

```json
{
  "version": "1.0",
  "cities": {
    "郴州": [
      {
        "name": "示例美食或店铺名称",
        "kind": "实测美食",
        "district": "所在区域（可选）",
        "image": "https://example.com/your-photo.jpg",
        "description": "填写真实体验：味道/特色、推荐理由、位置或避坑提示。价格可能变化时注明以现场为准。",
        "source": "拍摄者或图片出处（可选）",
        "source_url": "https://example.com/original-page（可选）"
      }
    ]
  }
}
```

上面的名称和 URL 仅为格式示例，不是项目的真实店铺推荐。尚无可信图片时先不要添加记录，也不要用相似风景图代替。避免把个人订单、预约凭证、二维码或证件信息放进公开数据。

## 校验

```bash
python3 -m unittest tests/test_visual_gallery.py
python3 scripts/validate_data.py
```

图库扩展不要求购买、预约或接入第三方服务；没有新增图片数据时，脚本仍可生成原有景点图集。
