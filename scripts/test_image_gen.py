"""
Diagnose image generation options:
1. Test HF FLUX.1-schnell directly
2. Test Gemini Imagen 3 as fallback
"""
import asyncio
import os
import dotenv

dotenv.load_dotenv()

async def test_hf_image():
    """Test HuggingFace FLUX.1-schnell via the actual InferenceClient."""
    key = os.getenv("HF_API_KEY")
    if not key:
        print("[HF Image] [FAIL] HF_API_KEY is empty")
        return False
    try:
        from huggingface_hub import InferenceClient
        client = InferenceClient(api_key=key)
        print("[HF Image] Attempting FLUX.1-schnell generation...")
        image = client.text_to_image("a red apple", model="black-forest-labs/FLUX.1-schnell")
        print(f"[HF Image] [OK] FLUX.1-schnell works! Image size: {image.size}")
        return True
    except Exception as e:
        print(f"[HF Image] [FAIL] {e}")
        return False

async def test_gemini_imagen():
    """Test Gemini Imagen 3 via google-genai SDK."""
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        print("[Gemini Imagen] [FAIL] GEMINI_API_KEY is empty")
        return False
    try:
        from google import genai
        client = genai.Client(api_key=key)
        print("[Gemini Imagen] Attempting imagen-3.0-generate-002...")
        response = client.models.generate_images(
            model="imagen-3.0-generate-002",
            prompt="a red apple",
            config={"number_of_images": 1},
        )
        if response.generated_images:
            img = response.generated_images[0].image
            print(f"[Gemini Imagen] [OK] imagen-3.0 works! Bytes: {len(img.image_bytes)}")
            return True
        else:
            print("[Gemini Imagen] [FAIL] No images returned")
            return False
    except Exception as e:
        print(f"[Gemini Imagen] [FAIL] {e}")

    # Fallback: try gemini-2.0-flash-exp-image-generation
    try:
        print("[Gemini Imagen] Trying gemini-2.0-flash-exp-image-generation...")
        response = client.models.generate_content(
            model="gemini-2.0-flash-exp-image-generation",
            contents="Generate an image of a red apple",
            config={"response_modalities": ["IMAGE", "TEXT"]},
        )
        for part in response.candidates[0].content.parts:
            if part.inline_data and part.inline_data.data:
                print(f"[Gemini Imagen] [OK] flash-exp-image-generation works! Bytes: {len(part.inline_data.data)}")
                return True
        print("[Gemini Imagen] [FAIL] No image data in response")
        return False
    except Exception as e:
        print(f"[Gemini Imagen] [FAIL] flash-exp also failed: {e}")
        return False

async def main():
    hf_ok = await test_hf_image()
    if not hf_ok:
        print()
        print("[Diagnosis] HF failed — testing Gemini Imagen as replacement...")
        await test_gemini_imagen()

if __name__ == "__main__":
    asyncio.run(main())
