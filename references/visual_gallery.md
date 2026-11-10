# 图片与描述图集

行程生成和图片图集已接通：统一入口 `travel plan` 会先生成行程 JSON，再自动输出 `travel_gallery.md`。图集以图片和描述为主，不展示预约状态或订单信息。

## 使用方式

```bash
travel plan --profile profile.json --output ./trip
```

或直接运行集成入口：

```bash
python3 scripts/generate_trip.py --profile profile.json --output ./trip
```

以上命令会同时生成 `travel_plan.json` 和 `travel_gallery.md`。原有 `python3 scripts/generate_plan.py` 仍保留为只生成计划的兼容入口；如需图集，请改用 `travel plan` 或 `generate_trip.py`。

## 添加图片和描述

在 `references/visual_stories.json` 的 `cities` 下按城市添加内容。`kind` 只是内容类别。图片地址可以是可访问的图片 URL，也可以是项目中的相对路径；图片需要真实、可追溯，描述应由维护者根据可靠资料或亲身体验撰写。

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
python3 -m unittest discover -s tests -p 'test_visual_gallery.py'
python3 scripts/validate_data.py
```

图库扩展不要求购买、预约或接入第三方服务。
