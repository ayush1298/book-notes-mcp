import os
from typing import Any

from google import genai
from google.genai import types

import config

def extract_text_from_media(media_bytes: bytes, mime_type: str) -> str:
    """
    Uses Gemini to extract text from an image (OCR) or audio (Transcription).
    """
    if not os.getenv("GEMINI_API_KEY"):
        raise ValueError("GEMINI_API_KEY is required for media processing.")
        
    client = genai.Client()
    
    # Extract the raw model name (e.g., 'gemini/gemini-2.5-flash' -> 'gemini-2.5-flash')
    model_name = config.LLM_MODEL.replace("gemini/", "") if config.LLM_MODEL.startswith("gemini/") else "gemini-2.5-flash"
    
    prompt = (
        "Please extract the text from this media exactly as it is. "
        "If it is an image, perform OCR and return ONLY the extracted text. "
        "If it is audio, perform transcription and return ONLY the spoken text. "
        "Do not add any conversational filler, markdown formatting, or explanations."
    )
    
    response = client.models.generate_content(
        model=model_name,
        contents=[
            types.Part.from_bytes(data=media_bytes, mime_type=mime_type),
            prompt
        ]
    )
    
    return response.text.strip()
