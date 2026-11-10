import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import generate_gallery
import generate_trip


class GalleryTests(unittest.TestCase):
    def test_build_gallery_uses_itinerary_tips_and_curated_food(self):
        plan = {
            "city": "郴州",
            "title": "郴州两日游",
            "gallery": [{"name": "高椅岭", "district": "资兴市", "image": "https://img.example/hill.jpg"}],
            "days": [{"items": [{"name": "高椅岭", "tips": "丹霞地貌适合徒步，穿防滑鞋。"}]}],
        }
        stories = {"cities": {"郴州": [{
            "name": "实测鱼粉店", "kind": "实测美食", "image": "https://img.example/food.jpg",
            "description": "汤鲜微辣，配油条更合适。", "source": "用户实拍",
        }]}}
        cards = generate_gallery.build_gallery(plan, stories)
        self.assertEqual(len(cards), 2)
        self.assertEqual(cards[0]["description"], "丹霞地貌适合徒步，穿防滑鞋。")
        self.assertEqual(cards[1]["kind"], "实测美食")

    def test_curated_story_overrides_matching_attraction(self):
        plan = {"city": "上海", "gallery": [{"name": "外滩", "image": "https://img.example/bund.jpg"}]}
        stories = {"cities": {"上海": [{
            "name": "外滩", "kind": "景点", "image": "https://img.example/real.jpg",
            "description": "黄昏时沿江散步，可以看到两岸灯光。",
        }]}}
        cards = generate_gallery.build_gallery(plan, stories)
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["image"], "https://img.example/real.jpg")
        self.assertIn("黄昏时", cards[0]["description"])

    def test_render_includes_image_description_and_source(self):
        markdown = generate_gallery.render_gallery("上海一日游", [{
            "name": "外滩", "kind": "景点", "district": "黄浦区",
            "image": "https://img.example/bund.jpg", "description": "沿江散步看夜景。",
            "source": "摄影者", "source_url": "https://example.com/photo",
        }])
        self.assertIn("![外滩](https://img.example/bund.jpg)", markdown)
        self.assertIn("沿江散步看夜景。", markdown)
        self.assertIn("https://example.com/photo", markdown)
        self.assertNotIn("预约", markdown)

    def test_empty_gallery_has_helpful_message(self):
        markdown = generate_gallery.render_gallery("行程", [])
        self.assertIn("visual_stories.json", markdown)

    def test_trip_entrypoint_generates_gallery_automatically(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir)
            plan_path = output / "travel_plan.json"

            def fake_plan_main(_argv):
                plan_path.write_text('{"city":"上海"}', encoding="utf-8")
                return 0

            with patch.object(generate_trip.generate_plan, "main", side_effect=fake_plan_main), \
                    patch.object(generate_trip.generate_gallery, "main", return_value=0) as gallery_main:
                result = generate_trip.main(["--output", str(output)])

            self.assertEqual(result, 0)
            gallery_main.assert_called_once_with(["--plan", str(plan_path)])

    def test_trip_entrypoint_skips_gallery_for_sql_only(self):
        with patch.object(generate_trip.generate_plan, "main", return_value=0), \
                patch.object(generate_trip.generate_gallery, "main") as gallery_main:
            result = generate_trip.main(["--sql-only"])
        self.assertEqual(result, 0)
        gallery_main.assert_not_called()


if __name__ == "__main__":
    unittest.main()
