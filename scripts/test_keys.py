import asyncio
import os
import dotenv
import httpx
import asyncpg
from redis.asyncio import Redis

dotenv.load_dotenv()

async def test_supabase():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY")
    if not url or not key:
        print("[Supabase] [FAIL] SUPABASE_URL or SUPABASE_SERVICE_KEY is empty")
        return
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{url}/storage/v1/bucket", headers={"Authorization": f"Bearer {key}"})
            if resp.status_code == 200:
                print("[Supabase] [OK] SUPABASE_URL and KEY are valid!")
            else:
                print(f"[Supabase] [FAIL] Invalid status code: {resp.status_code} ({resp.text[:200]})")
    except Exception as e:
        print(f"[Supabase] [FAIL] Connection failed: {e}")

async def test_neon_db():
    url = os.getenv("DATABASE_URL")
    if not url:
        print("[Neon DB] [FAIL] DATABASE_URL is empty")
        return
    try:
        conn = await asyncpg.connect(url)
        res = await conn.fetchval("SELECT 1")
        if res == 1:
            print("[Neon DB] [OK] DATABASE_URL is valid and connected!")
        await conn.close()
    except Exception as e:
        print(f"[Neon DB] [FAIL] Connection failed: {e}")

async def test_redis():
    url = os.getenv("REDIS_URL")
    if not url:
        print("[Redis] [FAIL] REDIS_URL is empty")
        return
    try:
        r = Redis.from_url(url)
        res = await r.ping()
        if res:
            print("[Redis] [OK] REDIS_URL is valid and pinged successfully!")
        await r.aclose()
    except Exception as e:
        print(f"[Redis] [FAIL] Connection failed: {e}")

async def test_groq():
    key = os.getenv("GROQ_API_KEY")
    if not key:
        print("[Groq] [FAIL] GROQ_API_KEY is empty")
        return
    try:
        async with httpx.AsyncClient() as client:
            # Test using openai/gpt-oss-120b or fallback openai/gpt-oss-20b
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"model": "openai/gpt-oss-20b", "messages": [{"role": "user", "content": "Ping"}]}
            )
            if resp.status_code == 200:
                print("[Groq] [OK] GROQ_API_KEY is valid!")
            else:
                print(f"[Groq] [FAIL] Invalid key/response: {resp.status_code} ({resp.text[:200]})")
    except Exception as e:
        print(f"[Groq] [FAIL] Request failed: {e}")

async def test_gemini():
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        print("[Gemini] [FAIL] GEMINI_API_KEY is empty")
        return
    try:
        async with httpx.AsyncClient() as client:
            # Test using the actual stable v1 API for gemini-2.5-flash
            resp = await client.post(
                f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent?key={key}",
                headers={"Content-Type": "application/json"},
                json={"contents": [{"parts": [{"text": "Ping"}]}]}
            )
            if resp.status_code == 200:
                print("[Gemini] [OK] GEMINI_API_KEY is valid!")
            else:
                print(f"[Gemini] [FAIL] Invalid key/response: {resp.status_code} ({resp.text[:200]})")
    except Exception as e:
        print(f"[Gemini] [FAIL] Request failed: {e}")

async def test_hf():
    key = os.getenv("HF_API_KEY")
    if not key:
        print("[HuggingFace] [FAIL] HF_API_KEY is empty")
        return
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://api-inference.huggingface.co/models/black-forest-labs/FLUX.1-schnell",
                headers={"Authorization": f"Bearer {key}"}
            )
            if resp.status_code in [200, 503]:
                print("[HuggingFace] [OK] HF_API_KEY is valid!")
            else:
                print(f"[HuggingFace] [FAIL] Invalid status: {resp.status_code} ({resp.text[:200]})")
    except Exception as e:
        print(f"[HuggingFace] [FAIL] Request failed: {e}")

async def test_weather():
    key = os.getenv("OPENWEATHER_API_KEY")
    if not key:
        print("[OpenWeatherMap] [FAIL] OPENWEATHER_API_KEY is empty")
        return
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"https://api.openweathermap.org/data/2.5/weather?q=London&appid={key}"
            )
            if resp.status_code == 200:
                print("[OpenWeatherMap] [OK] OPENWEATHER_API_KEY is valid!")
            else:
                print(f"[OpenWeatherMap] [FAIL] Invalid status: {resp.status_code} ({resp.text[:200]})")
    except Exception as e:
        print(f"[OpenWeatherMap] [FAIL] Request failed: {e}")

async def main():
    await test_neon_db()
    await test_redis()
    await test_groq()
    await test_gemini()
    await test_hf()
    await test_weather()
    await test_supabase()

if __name__ == "__main__":
    asyncio.run(main())
