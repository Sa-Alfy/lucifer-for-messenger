"""
tests/test_phase4_ai_tools.py — Extended AI Capabilities.

Tests:
  - Image generation (HF FLUX.1-schnell thread pool execution)
  - OCR (Gemini vision wrapper with OCR-specific prompt)
  - Translation (Groq-based translation wrapper)
  - AI text tools (explain, summarize, rewrite)
  - Gemini vision image description
  - Supabase Storage upload helper (httpx mocked)
"""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import httpx
from tests.conftest import FakeRedis


# ── Image Generation ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_generate_image_success():
    """Verify generate_image runs in a thread pool and returns PNG bytes."""
    from services.image_gen import generate_image
    
    mock_pil_image = MagicMock()
    # Mock the save method to write nothing or mock bytes
    def mock_save(buf, format):
        buf.write(b"fake-png-bytes")
    mock_pil_image.save.side_effect = mock_save
    
    mock_client = MagicMock()
    mock_client.text_to_image.return_value = mock_pil_image
    
    with patch("services.image_gen._get_client", return_value=mock_client):
        # We need to mock run_in_executor to avoid actual thread execution if we want, 
        # or let it run but mock the blocking function.
        # Since run_in_executor calls _generate_sync, we can just mock _generate_sync or text_to_image.
        # Let's let the thread pool run and mock _get_client().text_to_image.
        img_bytes = await generate_image("a cute cat")
        assert img_bytes == b"fake-png-bytes"
        mock_client.text_to_image.assert_called_once_with("a cute cat", model="black-forest-labs/FLUX.1-schnell")


# ── Gemini Vision ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_describe_image_success():
    """Verify describe_image calls Gemini stable async generate_content API."""
    from services.gemini_vision import describe_image
    
    mock_response = MagicMock()
    mock_response.text = "A beautiful landscape."
    
    mock_aio = AsyncMock()
    mock_aio.models.generate_content.return_value = mock_response
    
    mock_client = MagicMock()
    mock_client.aio = mock_aio
    
    with patch("services.gemini_vision._get_client", return_value=mock_client):
        result = await describe_image(
            system_prompt="You are Lucifer.",
            prompt="What is this?",
            image_bytes=b"image-bytes",
            mime_type="image/jpeg"
        )
        assert result == "A beautiful landscape."
        mock_aio.models.generate_content.assert_called_once()
        
        # Verify call arguments
        call_kwargs = mock_aio.models.generate_content.call_args[1]
        assert call_kwargs["model"] == "gemini-2.5-flash"
        assert call_kwargs["contents"][0] == "What is this?"
        # Part check
        part = call_kwargs["contents"][1]
        assert part.inline_data.data == b"image-bytes"
        assert part.inline_data.mime_type == "image/jpeg"
        # Config check
        assert call_kwargs["config"].system_instruction == "You are Lucifer."


# ── OCR (Gemini adapter) ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ocr_success():
    """Verify extract_text calls describe_image with OCR system prompt."""
    from services.ocr import extract_text
    
    with patch("services.ocr.describe_image", new_callable=AsyncMock) as mock_describe:
        mock_describe.return_value = "Hello World"
        result = await extract_text(b"image-bytes", "image/png")
        assert result == "Hello World"
        mock_describe.assert_called_once()
        args = mock_describe.call_args[0]
        # System prompt contains OCR instructions
        assert "You are an OCR tool" in args[0]
        assert args[1] == "Extract all text from this image."
        assert args[2] == b"image-bytes"
        assert args[3] == "image/png"


# ── Translation ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_translate_text_success():
    """Verify translate_text calls get_groq_reply with translation system prompt."""
    from services.translate import translate_text
    
    with patch("services.translate.get_groq_reply", new_callable=AsyncMock) as mock_groq:
        mock_groq.return_value = "Bonjour"
        result = await translate_text("French", "Hello")
        assert result == "Bonjour"
        mock_groq.assert_called_once()
        
        system_prompt = mock_groq.call_args[0][0]
        assert "You are a precise translator" in system_prompt
        assert "French" in system_prompt
        assert mock_groq.call_args[0][2] == "Hello"


# ── AI Text Tools ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_ai_tool_explain():
    """Verify run_ai_tool calls get_groq_reply with the explain prompt."""
    from services.ai_tools import run_ai_tool
    
    with patch("services.ai_tools.get_groq_reply", new_callable=AsyncMock) as mock_groq:
        mock_groq.return_value = "Explanation of quantum computing..."
        result = await run_ai_tool("explain", "quantum computing")
        assert result == "Explanation of quantum computing..."
        mock_groq.assert_called_once()
        
        system_prompt = mock_groq.call_args[0][0]
        assert "Explain the following clearly and simply" in system_prompt


@pytest.mark.asyncio
async def test_run_ai_tool_invalid():
    """Verify run_ai_tool raises KeyError for unrecognized tool names."""
    from services.ai_tools import run_ai_tool
    with pytest.raises(KeyError):
        await run_ai_tool("invalid_tool_name", "some text")


# ── Supabase Storage ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_upload_image_success():
    """Verify upload_image POSTs to Supabase storage and returns the public URL."""
    from services.storage import upload_image
    
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    
    # We mock the client context manager
    mock_client = MagicMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    
    with patch("httpx.AsyncClient", return_value=mock_client):
        public_url = await upload_image(b"fake-image-data")
        
        # Verify it returns a public URL under the correct bucket
        assert "https://test.supabase.co/storage/v1/object/public/generated-images/" in public_url
        assert public_url.endswith(".png")
        
        # Verify post parameters
        mock_client.post.assert_called_once()
        post_url = mock_client.post.call_args[0][0]
        assert "https://test.supabase.co/storage/v1/object/generated-images/" in post_url
        
        headers = mock_client.post.call_args[1]["headers"]
        assert headers["Authorization"] == "Bearer test-service-key"
        assert headers["Content-Type"] == "image/png"
        assert mock_client.post.call_args[1]["content"] == b"fake-image-data"
