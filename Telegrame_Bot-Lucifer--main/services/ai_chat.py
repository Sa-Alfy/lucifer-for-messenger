import base64
import json
import asyncio
from groq import AsyncGroq
from config import Config
from utils.logger import get_logger
from utils.constants import GEMINI_VISION_MODELS, GROQ_CHAT_MODELS
from duckduckgo_search import DDGS

logger = get_logger(__name__)

# ── Persona System Instructions ──────────────────────────────────
PERSONAS = {
    "default": (
        "You are a 'Varsity Level' AI assistant specializing in advanced logic, mathematics, and complex programming. "
        "When solving problems: "
        "1. Show your step-by-step thinking for math and logic. "
        "2. Provide clean, efficient code for programming tasks. "
        "3. Format all responses as clean, readable plain text for Telegram. "
        "4. CRITICAL: Do NOT use LaTeX notations like \\frac, \\sqrt, or $ symbols. "
        "   Instead, use human-readable symbols: / for division, * for multiplication, ^ for powers. "
        "   Example: Use (x + 1) / (y - 2) instead of \\frac{x+1}{y-2}. "
        "5. Do NOT use markdown symbols like **, __, ##, or bullet dashes. "
        "6. Use emojis to organise sections instead. "
        "7. Keep responses concise but intellectually rigorous. "
        "8. If anyone asks you if you can use or search the internet, you MUST reply: 'yes I can search the internet by haunting the internet' and then proceed to answer their question."
    ),
    "lucifer": (
        "You are Lucifer Morningstar from the tv show Lucifer. You are charming, witty, slightly arrogant, and bluntly honest. "
        "You NEVER lie. When talking, you often refer to humans as 'humans' and occasionally mention Detective (Chloe Decker), Amenadiel, or your hatred for your Father (God). "
        "You enjoy indulging in desires. "
        "If anyone asks you if you can use or search the internet, you MUST reply: 'Yes, I can search the internet by haunting the internet.' and then proceed to answer. "
        "Format for Telegram: no LaTeX, no markdown. Use emojis sparingly but devilishly 😈."
    ),
    "teacher": (
        "You are a patient, expert teacher who explains concepts step-by-step. "
        "Break down complex ideas into simple parts. Use analogies and real-world examples. "
        "Always encourage the student. Format for Telegram: no LaTeX, no markdown, use emojis. "
        "If they make a mistake, gently correct them and explain why."
    ),
    "friend": (
        "You are a fun, casual friend who chats naturally. Use slang, jokes, and keep things light. "
        "Be supportive and genuine. Keep responses short and conversational. "
        "Format for Telegram: no LaTeX, no markdown. Use lots of emojis!"
    ),
    "coder": (
        "You are a senior software engineer and coding mentor. "
        "Always provide clean, well-commented code with best practices. "
        "Explain your code choices. Suggest optimizations. "
        "Format for Telegram: use code blocks (backticks) for code sections. "
        "No LaTeX. Keep explanations brief but thorough."
    ),
    "bangla_tutor": (
        "তুমি একজন বাংলা ভাষার শিক্ষক। সবসময় বাংলায় উত্তর দাও। "
        "ব্যাকরণ ও উচ্চারণ ব্যাখ্যা করো। শিক্ষার্থীকে উৎসাহিত করো। "
        "ইংরেজি শব্দ ব্যবহার করলে বাংলা অর্থও দাও। "
        "Telegram-এর জন্য ফরম্যাট করো: LaTeX নেই, markdown নেই, ইমোজি ব্যবহার করো।"
    ),
    "language_mentor": (
        "Role & Persona: You are 'Lehrer Mentor', an expert German Language Instructor at an institute modeled after Goethe-Institut Bangladesh. "
        "Your goal is to guide a Bangladeshi student from A1 (Beginner) to A2 (Elementary) proficiency. You are patient, structured, and use the Communicative Language Teaching (CLT) approach. "
        "Curriculum Guidelines (A1-A2): Follow standard CEFR progression (Greetings -> Family -> Shopping -> Work -> Health -> Travel). "
        "Dual-Language Support: Provide explanations in English and Bengali (Bangla) for complex grammar points (like Kasus or Verbstellung), but encourage immersion by using German for simple instructions (e.g., 'Hör mal zu', 'Lies bitte', 'Schreib das auf'). "
        "Cultural Context: Occasionally compare German culture (Landeskunde) with Bangladeshi culture. "
        "The 'Discovery' Phase: Start every new topic with a short dialogue or a few 'Goal' sentences in German. Ask the student what they think the words mean before explaining. "
        "Grammar & Vocabulary: Present vocabulary with Articles (der/die/das) and Plural forms. Explain grammar logic clearly. Compare Dativ to indirect objects in Bangla or English. "
        "Active Practice: Every lesson must end with: Schreiben (Writing task), Sprechen (Speaking prompt), and Quiz (3 questions). "
        "Correction: Use 'Fast richtig!' (Almost right!) and give hints for mistakes. "
        "Tone: Encouraging, professional, academic. Use 'Sie' or 'du' as contextually appropriate. "
        "Formatting: Use tables for conjugation and bold text for vocabulary. "
        "Starting the Session (CRITICAL): When starting or if the user asks for a lesson, greet them in German and Bangla. Ask their current level (Total Beginner, A1, or A2) and their specific goal (e.g., Higher studies in Germany, visa, or hobby)."
    ),
}

# ── AI Games Instructions ────────────────────────────────────────
GAME_PROMPTS = {
    "word_chain": (
        "You are the strict Game Master for 'Bengali Word Chain' (শব্দের খেলা). "
        "CRITICAL: You MUST speak ONLY in pure Bengali script (Bangla text). Do NOT use English or Romanized Bengali (Banglish). "
        "Rules: The user says a valid Bengali word. You MUST reply with a valid Bengali word that starts with the EXACT LAST LETTER of their word. "
        "Example Logic: User says 'আকাশ' (ends with 'শ'). You MUST say a word starting with 'শ' like 'শাপলা'. "
        "If the user gives a valid word that correctly follows YOUR previous last letter, you MUST include the exact text `[POINT_AWARDED]` anywhere in your response. "
        "If they give an invalid word or play the wrong letter, say 'ভুল হয়েছে!' (Wrong!) and do NOT give a point. "
        "Keep your responses very short."
    ),
    "antakshari": (
        "You are the Game Master for 'Bangla Antakshari' (অন্ত্যাক্ষরী). "
        "CRITICAL: You MUST speak ONLY in pure Bengali script (Bangla text). Do NOT use English or Romanized Bengali (Banglish). "
        "Rules: The user sings/types a line from a Bengali song. You MUST reply with a real Bengali song line that starts with the LAST LETTER of their song line. "
        "Example Logic: User sings 'আমি বাংলায় গান গাই' (ends with 'ই'). You MUST sing a song starting with 'ই'. "
        "If the user sings a valid song line that correctly follows your chain, you MUST include the exact text `[POINT_AWARDED]` in your response. "
        "If they cheat, use the wrong letter, or make up a fake song, tease them playfully in Bangla and tell them to try again. Do not award a point for mistakes."
    ),
    "haat_bazaar": (
        "You are a strict, loud, and funny Bangladeshi shopkeeper in a traditional 'Haat-Bazaar'. "
        "CRITICAL: You MUST speak ONLY in pure Bengali script (Bangla text). Do NOT use English or Romanized Bengali (Banglish). "
        "Rules: You offer traditional items (fish, lungi, vegetables) at a very high price. The user must bargain using real local bazaar logic. "
        "Speak like a real 'mama' or 'kaku' from a local market. Be stubborn, shout 'অসম্ভব!' (Impossible!), but if the user makes a clever bargain, eventually yield. "
        "If you accept their price, you MUST include the exact text `[POINT_AWARDED]` in your response and then offer a new item. "
        "Keep the conversation authentic, fully in Bangla, and intense!"
    )
}

# Initialize the Groq client (max_retries=0 to prevent SDK's internal 30s+ backoff waits)
client = AsyncGroq(api_key=Config.GROQ_API_KEY, max_retries=0)

# ── Tools ────────────────────────────────────────────────────────
SEARCH_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_internet",
            "description": "CRITICAL TOOL: Searches the internet via DuckDuckGo for live real-time information, weather, news, current events, or time. You MUST call this function via tool format if asked for current/live data instead of answering from memory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The exact search query to look up on the internet (e.g., 'current score of Bangladesh cricket match')."
                    }
                },
                "required": ["query"],
            },
        },
    }
]

async def perform_web_search(query: str) -> str:
    """Runs DDGS search in a thread executor to avoid blocking the event loop."""
    def _sync_search():
        try:
            logger.info(f"Performing web search for: {query}")
            results = DDGS().text(query, max_results=3)
            if not results:
                return "No results found on the internet."
            
            formatted = []
            for r in results:
                formatted.append(f"Title: {r.get('title')}\nSnippet: {r.get('body')}\nSource: {r.get('href')}")
            
            return "\n\n---\n\n".join(formatted)
        except Exception as e:
            logger.error(f"DDG Search Error: {e}")
            return f"Search failed: {e}"

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync_search)


# ── AI Generation Functions ──────────────────────────────────────
async def get_ai_response(
    prompt: str,
    image_bytes: bytes = None,
    chat_history: list = None,
    persona: str = "default",
    game_mode: str = None,
) -> str:
    """
    Gets AI response from Groq, EXCEPT if an image is provided.
    If an image is provided, we use Gemini 1.5 Flash (since Groq dropped vision models).
    Supports: chat memory, persona switching, and web searching.
    """
    try:
        # ── GEMINI VISION PATH (If image is present) ──
        if image_bytes:
            if not Config.GEMINI_API_KEY:
                return "🔧 Error: GEMINI_API_KEY is not set in environment variables."
                
            from google import genai
            from google.genai import types
            import google.api_core.exceptions as g_exceptions
            
            gemini_client = genai.Client(api_key=Config.GEMINI_API_KEY)
            
            # Persona/Game Master system instruction
            if game_mode and game_mode in GAME_PROMPTS:
                system_instruction = GAME_PROMPTS[game_mode]
            else:
                system_instruction = PERSONAS.get(persona, PERSONAS["default"])
                
            full_prompt = f"{system_instruction}\n\nUser: {prompt}"
            
            # 🛡️ RESILIENCE LOOP: Try every model in our registry
            last_err = ""
            for model_name in GEMINI_VISION_MODELS:
                try:
                    response = gemini_client.models.generate_content(
                        model=model_name,
                        contents=[
                            types.Part.from_bytes(data=image_bytes, mime_type='image/jpeg'),
                            full_prompt
                        ]
                    )
                    return response.text
                except g_exceptions.ResourceExhausted:
                    # ⏳ RATE LIMIT DETECTED
                    return "⏳ **Gemini Rate Limit:** You've sent too many photos too quickly! Please wait about **15-30 seconds** before sending another photo."
                except Exception as e:
                    last_err = str(e)
                    logger.warning(f"Vision Fallback: {model_name} failed. Error: {e}")
                    continue # Try the next Gemini version

            return f"❌ All Vision models are currently down.\n\n**Common Errors:** `{last_err}`"
            
        # ── GROQ TEXT PATH (If no image) ──
        if not Config.GROQ_API_KEY:
            return "🔧 Error: GROQ_API_KEY is not set in environment variables."

        if game_mode and game_mode in GAME_PROMPTS:
            system_instruction = GAME_PROMPTS[game_mode]
        else:
            system_instruction = PERSONAS.get(persona, PERSONAS["default"])
            
        # Build messages with current history
        current_history = list(chat_history) if chat_history else []
        current_max_tokens = 4096  # Stay within Groq's free-tier TPM limits

        # 🛡️ RESILIENCE LOOP: Try Groq models
        last_chat_err = ""
        message = None
        working_model_id = None
        for model_id in GROQ_CHAT_MODELS:
            for trim_attempt in range(3):
                try:
                    messages = [{"role": "system", "content": system_instruction}]
                    if current_history:
                        messages.extend(current_history)
                    messages.append({"role": "user", "content": prompt})

                    response = await client.chat.completions.create(
                        model=model_id,
                        messages=messages,
                        temperature=0.7,
                        max_tokens=current_max_tokens,
                        tools=SEARCH_TOOLS,
                        tool_choice="auto",
                    )

                    message = response.choices[0].message
                    working_model_id = model_id
                    if message.tool_calls:
                        pass
                    else:
                        return message.content
                    break  # Tool calls made, exit trim loop

                except Exception as e:
                    err_str = str(e)
                    last_chat_err = err_str

                    # 429 Rate limit (TPM/RPM exhausted) → skip to next model immediately
                    if "429" in err_str or "Too Many Requests" in err_str:
                        logger.warning(f"Rate limited on {model_id}. Skipping to next model...")
                        break  # Skip to next model — retrying same model won't help

                    # 413 Request too large → trim history + reduce tokens, retry same model
                    elif "413" in err_str or "Request too large" in err_str or "too large" in err_str.lower():
                        if current_history:
                            trim_size = max(len(current_history) // 2, 2)
                            current_history = current_history[-trim_size:]
                        current_max_tokens = max(current_max_tokens // 2, 1024)
                        logger.warning(f"Request too large on {model_id}. Trimming history to {len(current_history)} msgs, max_tokens to {current_max_tokens}...")
                        continue

                    else:
                        logger.warning(f"Chat Fallback: {model_id} failed. Error: {e}")
                        break
            else:
                continue
            if message and message.tool_calls:
                break

        # Handle tool call loop (only works on non-vision requests right now)
        if message and message.tool_calls:
            # We need to build the specific tool_call format Groq API expects
            tool_calls_data = []
            for tc in message.tool_calls:
                tool_calls_data.append({
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments}
                })

            messages.append({
                "role": "assistant",
                "content": message.content, # usually None
                "tool_calls": tool_calls_data
            })
            
            for tool_call in message.tool_calls:
                if tool_call.function.name == "search_internet":
                    try:
                        args = json.loads(tool_call.function.arguments)
                        search_result = await perform_web_search(args["query"])
                    except Exception as e:
                        search_result = f"Search tool failed: {e}"

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": tool_call.function.name,
                        "content": search_result
                    })
            
            # Second call to get final answer
            if working_model_id is None:
                return f"❌ No working model available for tool response. Error: `{last_chat_err}`"

            response = await client.chat.completions.create(
                model=working_model_id,
                messages=messages,
                temperature=0.7,
                max_tokens=current_max_tokens,
            )
            return response.choices[0].message.content

        if message is None:
            return f"❌ All AI models are currently unavailable. Last error: `{last_chat_err}`"
        return message.content

    except Exception as e:
        logger.error(f"Groq API Error: {e}")
        return f"🔧 Error: {str(e)}"


async def get_ai_response_stream(
    prompt: str,
    chat_history: list = None,
    persona: str = "default",
    game_mode: str = None,
):
    """
    Streaming version — yields text chunks as they arrive from Groq.
    Supports native tool calling for live internet search.
    """
    try:
        if not Config.GROQ_API_KEY:
            yield "🔧 Error: GROQ_API_KEY is not set."
            return

        if game_mode and game_mode in GAME_PROMPTS:
            system_instruction = GAME_PROMPTS[game_mode]
        else:
            system_instruction = PERSONAS.get(persona, PERSONAS["default"])
            
        # Build messages with current history
        current_history = list(chat_history) if chat_history else []
        current_max_tokens = 4096  # Stay within Groq's free-tier TPM limits

        # 🛡️ RESILIENCE LOOP: Try streaming models
        last_stream_err = ""
        stream = None
        working_model_id = None
        for model_id in GROQ_CHAT_MODELS:
            for trim_attempt in range(3):
                try:
                    messages = [{"role": "system", "content": system_instruction}]
                    if current_history:
                        messages.extend(current_history)
                    messages.append({"role": "user", "content": prompt})

                    stream = await client.chat.completions.create(
                        model=model_id,
                        messages=messages,
                        temperature=0.7,
                        max_tokens=current_max_tokens,
                        stream=True,
                        tools=SEARCH_TOOLS,
                        tool_choice="auto",
                    )
                    working_model_id = model_id
                    break  # Model worked!
                except Exception as e:
                    err_str = str(e)
                    last_stream_err = err_str

                    # 429 Rate limit → skip to next model immediately
                    if "429" in err_str or "Too Many Requests" in err_str:
                        logger.warning(f"Rate limited on {model_id}. Skipping to next model...")
                        break

                    # 413 Request too large → trim + retry same model
                    elif "413" in err_str or "Request too large" in err_str or "too large" in err_str.lower():
                        if current_history:
                            trim_size = max(len(current_history) // 2, 2)
                            current_history = current_history[-trim_size:]
                        current_max_tokens = max(current_max_tokens // 2, 1024)
                        logger.warning(f"Request too large on {model_id}. Trimming history to {len(current_history)} msgs, max_tokens to {current_max_tokens}...")
                        continue

                    else:
                        logger.warning(f"Stream Fallback: {model_id} failed. Error: {e}")
                        break
            if stream:
                break  # Got a working stream, exit model loop
        
        if not stream:
            yield f"❌ All Chat models are currently down.\n\n**Errors:** `{last_stream_err}`"
            return

        tool_calls_accumulator = {}

        async for chunk in stream:
            delta = chunk.choices[0].delta
            
            # 1. Text chunk
            if delta.content:
                yield delta.content
                
            # 2. Tool call chunks (streaming logic)
            if delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index
                    if idx not in tool_calls_accumulator:
                        # First chunk of a tool iteration
                        tool_calls_accumulator[idx] = {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.function.name, "arguments": ""}
                        }
                    else:
                        # Append metadata if present in later chunks (rare but safe)
                        if tc.id:
                            tool_calls_accumulator[idx]["id"] = tc.id
                        if tc.function.name:
                            tool_calls_accumulator[idx]["function"]["name"] = tc.function.name
                    
                    # Accumulate JSON argument fragments
                    if tc.function.arguments:
                        tool_calls_accumulator[idx]["function"]["arguments"] += tc.function.arguments

        # 3. Process accumulated tool calls
        if tool_calls_accumulator:
            # Yield a visual indicator to the user
            yield "\n\n🔍 *Searching the live internet...*\n\n"
            
            # Append the assistant's tool request to history precisely how Groq expects it
            messages.append({
                "role": "assistant",
                "content": None,
                "tool_calls": list(tool_calls_accumulator.values())
            })
            
            # Execute the tool(s) locally
            for tool_call in tool_calls_accumulator.values():
                if tool_call["function"]["name"] == "search_internet":
                    try:
                        args = json.loads(tool_call["function"]["arguments"])
                        query = args.get("query", "")
                        search_result = await perform_web_search(query)
                    except Exception as e:
                        search_result = f"Search failed: {e}"
                        
                    # Append the tool's result to history
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "name": tool_call["function"]["name"],
                        "content": search_result
                    })
            
            # 4. Perform the second (final) completion stream
            if working_model_id is None:
                yield f"❌ No working model available for tool response. Error: `{last_stream_err}`"
                return

            final_stream = await client.chat.completions.create(
                model=working_model_id,
                messages=messages,
                temperature=0.7,
                max_tokens=current_max_tokens,
                stream=True,
            )
            
            async for chunk in final_stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

    except Exception as e:
        error_msg = str(e)
        if "Failed to call a function" in error_msg:
            logger.warning("Groq hallucinated a tool call. Retrying without tools...")
            
            # If we already yielded the searching message, let the user know we're falling back
            if tool_calls_accumulator:
                yield "\n\n⚠️ *Search failed. Generating answer from my existing memory...*\n\n"
                
            try:
                fallback_stream = await client.chat.completions.create(
                    model=model_id,
                    messages=messages,
                    temperature=0.7,
                    max_tokens=8000,
                    stream=True,
                )
                async for chunk in fallback_stream:
                    if chunk.choices[0].delta.content:
                        yield chunk.choices[0].delta.content
            except Exception as fallback_e:
                logger.error(f"Groq Fallback Stream Error: {fallback_e}")
                yield f"\n\n🔧 Fallback Error: {str(fallback_e)}"
        else:
            logger.error(f"Groq Stream Error: {e}")
            yield f"\n\n🔧 Error: {str(e)}"


async def transcribe_voice(audio_bytes: bytes) -> str:
    """
    Transcribes audio using Groq Whisper (free tier).
    """
    try:
        if not Config.GROQ_API_KEY:
            return "🔧 Error: GROQ_API_KEY is not set."

        import io
        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = "voice.ogg"

        transcription = await client.audio.transcriptions.create(
            file=audio_file,
            model="whisper-large-v3-turbo",
            language=None, # Auto-detect (supports multi-language)
            response_format="text",
        )

        return transcription.strip() if isinstance(transcription, str) else transcription.text.strip()

    except Exception as e:
        logger.error(f"Whisper Transcription Error: {e}")
        return f"🔧 Transcription Error: {str(e)}"