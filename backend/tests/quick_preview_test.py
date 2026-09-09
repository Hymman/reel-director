import sys
sys.path.insert(0, r"C:\reel-director\backend")
from app.services.preview_service import render_storyboard_fallback

class MockShot:
    purpose = "hero"
    order = 1
    duration_seconds = 6
    visual = "Wide establishing shot of user at desk with laptop glowing"
    action = "User opens app on phone, relief washes over face"
    camera = "Medium close-up, slight tilt-down"
    audio_direction = "Natural keyboard clicks and coffee sounds"
    creative_mode = "creator_demo"
    caption = "Stop losing time to scattered workflows"
    shot_id = "S1"

class MockKit:
    brand_colors = ["#F5F5F0", "#1A1714", "#FFB347"]
    brand_name = "TestBrand"

shot = MockShot()
kit = MockKit()
data = render_storyboard_fallback(shot, "SHOT 1", kit)
is_png = data[:4] == b"\x89PNG"
print(f"Storyboard rendered: {len(data)} bytes, PNG: {is_png}")

from PIL import Image
import io
img = Image.open(io.BytesIO(data)).convert("RGB")
pixels = list(img.getdata())
unique_colors = len(set(pixels))
print(f"Unique colors: {unique_colors}")
assert unique_colors > 3, "Preview has too few colors - nearly black!"
print("PREVIEW SMOKE TEST PASSED")
