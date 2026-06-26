import requests
from config import Config
from utils.constants import FLUX_HF_ROUTER_URL, FLUX_HF_MODEL

# Using the incredibly fast and powerful Flux.1 model hosted on Hugging Face Serverless
API_URL = f"{FLUX_HF_ROUTER_URL}{FLUX_HF_MODEL}"

def generate_image_bytes(prompt: str) -> bytes:
    """
    Sends a prompt to Hugging Face (Flux.1) and returns the generated image as raw bytes.
    """
    if not Config.IMAGE_GEN_KEY or "sk_" in Config.IMAGE_GEN_KEY:
        raise Exception("Invalid or missing Hugging Face API Key!")

    headers = {
        "Authorization": f"Bearer {Config.IMAGE_GEN_KEY}"
    }
    payload = {
        "inputs": prompt
    }
    
    # We use a 60 second timeout because image generation can take some time
    try:
        response = requests.post(API_URL, headers=headers, json=payload, timeout=60)
        
        if response.status_code == 200:
            return response.content
        elif response.status_code == 503:
            raise Exception("🛠️ Hugging Face server is currently BUSY. Please wait 10 seconds and try again!")
        elif response.status_code in [404, 410]:
            raise Exception("📡 Hugging Face has moved this model. Admin needs to update the API URL.")
        else:
            raise Exception(f"Hugging Face API Error {response.status_code}: {response.text}")
    except requests.exceptions.Timeout:
        raise Exception("⚡ Request timed out. The image generation is taking too long!")
    except Exception as e:
        raise e