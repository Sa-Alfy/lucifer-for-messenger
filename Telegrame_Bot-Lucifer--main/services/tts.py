import edge_tts
import asyncio
import os
import tempfile
import re

async def generate_speech(text: str, voice_type: str = "male"):
    """
    Generates speech using Edge-TTS and returns the path to the temporary audio file.
    Automatically detects if text is Bangla or English.
    """
    
    # 1. Select the correct Neural Voice
    # Defaulting to Bangla voices since the user specified Bangla support.
    # We use a simple regex to see if there are any Bangla characters.
    is_bangla = bool(re.search(r'[\u0980-\u09FF]', text))
    
    if is_bangla:
        # confirmed voices for bn-BD (2026)
        voice = "bn-BD-PradeepNeural" if voice_type == "male" else "bn-BD-NabanitaNeural"
    else:
        # High quality US English voices
        voice = "en-US-GuyNeural" if voice_type == "male" else "en-US-AriaNeural"

    # 2. Generate the Audio
    # We use a temporary file to store the audio safely
    with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as tmp:
        output_path = tmp.name

    try:
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(output_path)
    except Exception as e:
        # Cleanup on failure
        if os.path.exists(output_path):
            os.remove(output_path)
        raise e
    
    return output_path
