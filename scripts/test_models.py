import asyncio
import os
import io
import wave
import dotenv
import httpx
from groq import AsyncGroq
from google import genai
from google.genai import types
from huggingface_hub import InferenceClient
from PIL import Image

dotenv.load_dotenv()

async def test_groq_primary():
    key = os.getenv("GROQ_API_KEY")
    if not key:
        print("[Groq Primary] [FAIL] GROQ_API_KEY is empty")
        return
    try:
        client = AsyncGroq(api_key=key)
        resp = await asyncio.wait_for(
            client.chat.completions.create(
                model="openai/gpt-oss-120b",
                messages=[{"role": "user", "content": "Say: 'Yes, gpt-oss-120b is working!'"}]
            ),
            timeout=15.0
        )
        content = resp.choices[0].message.content.strip()
        print(f"[Groq Primary] [OK] openai/gpt-oss-120b works! Response: '{content}'")
    except asyncio.TimeoutError:
        print("[Groq Primary] [FAIL] Request timed out (15s)")
    except Exception as e:
        print(f"[Groq Primary] [FAIL] Error: {e}")

async def test_groq_fallback():
    key = os.getenv("GROQ_API_KEY")
    if not key:
        print("[Groq Fallback] [FAIL] GROQ_API_KEY is empty")
        return
    try:
        client = AsyncGroq(api_key=key)
        resp = await asyncio.wait_for(
            client.chat.completions.create(
                model="openai/gpt-oss-20b",
                messages=[{"role": "user", "content": "Say: 'Yes, gpt-oss-20b is working!'"}]
            ),
            timeout=15.0
        )
        content = resp.choices[0].message.content.strip()
        print(f"[Groq Fallback] [OK] openai/gpt-oss-20b works! Response: '{content}'")
    except asyncio.TimeoutError:
        print("[Groq Fallback] [FAIL] Request timed out (15s)")
    except Exception as e:
        print(f"[Groq Fallback] [FAIL] Error: {e}")

async def test_groq_whisper():
    key = os.getenv("GROQ_API_KEY")
    if not key:
        print("[Groq Whisper] [FAIL] GROQ_API_KEY is empty")
        return
    try:
        buf = io.BytesIO()
        with wave.open(buf, 'wb') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(16000)
            wav_file.writeframes(b'\x00' * 32000)
        wav_bytes = buf.getvalue()

        client = AsyncGroq(api_key=key)
        resp = await asyncio.wait_for(
            client.audio.transcriptions.create(
                file=("voice.wav", wav_bytes),
                model="whisper-large-v3-turbo",
                response_format="text"
            ),
            timeout=15.0
        )
        print(f"[Groq Whisper] [OK] whisper-large-v3-turbo works! Response: '{resp.strip()}'")
    except asyncio.TimeoutError:
        print("[Groq Whisper] [FAIL] Request timed out (15s)")
    except Exception as e:
        print(f"[Groq Whisper] [FAIL] Error: {e}")

async def test_gemini_vision():
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        print("[Gemini Vision] [FAIL] GEMINI_API_KEY is empty")
        return
    try:
        client = genai.Client(api_key=key)
        # Create a proper 100x100 red image to avoid "Unable to process input image" errors
        img = Image.new('RGB', (100, 100), color='red')
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        red_png = buf.getvalue()
        
        response = await asyncio.wait_for(
            client.aio.models.generate_content(
                model="gemini-2.5-flash",
                contents=[
                    "What color is this image? Reply with just the color name.",
                    types.Part.from_bytes(data=red_png, mime_type="image/png")
                ]
            ),
            timeout=15.0
        )
        content = response.text.strip()
        print(f"[Gemini Vision] [OK] gemini-2.5-flash works! Response: '{content}'")
    except asyncio.TimeoutError:
        print("[Gemini Vision] [FAIL] Request timed out (15s)")
    except Exception as e:
        print(f"[Gemini Vision] [FAIL] Error: {e}")

async def test_hf_image():
    key = os.getenv("HF_API_KEY")
    if not key:
        print("[HuggingFace FLUX] [FAIL] HF_API_KEY is empty")
        return
    try:
        loop = asyncio.get_running_loop()
        client = InferenceClient(api_key=key, timeout=15)
        
        print("[HuggingFace FLUX] Requesting image generation...")
        image = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                lambda: client.text_to_image("a yellow banana", model="black-forest-labs/FLUX.1-schnell")
            ),
            timeout=20.0
        )
        print(f"[HuggingFace FLUX] [OK] FLUX.1-schnell works! Image size: {image.size}")
    except asyncio.TimeoutError:
        print("[HuggingFace FLUX] [FAIL] Request timed out (20s)")
    except Exception as e:
        print(f"[HuggingFace FLUX] [FAIL] Error: {e}")

async def main():
    print("=== STARTING AI MODEL TESTS ===")
    await asyncio.gather(
        test_groq_primary(),
        test_groq_fallback(),
        test_groq_whisper(),
        test_gemini_vision(),
        test_hf_image()
    )
    print("=== AI MODEL TESTS COMPLETE ===")

if __name__ == "__main__":
    asyncio.run(main())
