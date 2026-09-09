import os
import pytest
from google import genai
from google.genai import types
import time
from app.config import settings

def test_veo_smoke():
    if os.getenv("RUN_LIVE_VEO_TEST") != "1":
        pytest.skip("Live Veo generation is opt-in; set RUN_LIVE_VEO_TEST=1 to run it.")
    print(f"Testing Veo 3.1 Fast with model: {settings.veo_model_name}")
    client = genai.Client(
        vertexai=True,
        project=settings.google_cloud_project,
        location=settings.google_cloud_location
    )
    
    prompt = "Cinematic close-up of a cup of coffee on a wooden table, steam rising, 9:16 aspect ratio."
    
    print("Submitting prompt...")
    operation = client.models.generate_videos(
        model=settings.veo_model_name,
        source=types.GenerateVideosSource(prompt=prompt),
        config=types.GenerateVideosConfig(
            aspect_ratio="9:16",
            duration_seconds=6,
            generate_audio=True,
            person_generation="ALLOW_ADULT",
            output_gcs_uri=f"gs://{settings.gcs_bucket_name}/test_veo_{int(time.time())}/"
        )
    )
    
    print(f"Operation started: {operation.name}")
    start_time = time.time()
    
    while not operation.done:
        elapsed = time.time() - start_time
        if elapsed > 900:
            pytest.fail("Live Veo smoke test exceeded the 15-minute timeout")
        print(f"[{elapsed:.0f}s] Polling operation...")
        time.sleep(10)
        operation = client.operations.get(operation)
        
    print(f"\nCompleted in {time.time() - start_time:.0f}s")
    if getattr(operation, "error", None):
        print("ERROR:", str(operation.error))
    else:
        try:
            print("SUCCESS! Output URI:", operation.result.generated_videos[0].video.uri)
        except Exception as e:
            print("Could not extract URI:", e)
            print("Raw result:", operation.result)

if __name__ == "__main__":
    test_veo_smoke()
