from google import genai
from google.genai import types
from dotenv import load_dotenv
import os

load_dotenv()
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

try:
    response = client.models.generate_content(
        model='gemini-2.5-flash-preview-tts',
        contents="Please convert this text to audio. Do not generate any text, ONLY audio. Text: The quick brown fox jumps over the lazy dog.",
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
        )
    )
    
    # Check if we got audio
    for part in response.candidates[0].content.parts:
        if part.inline_data:
            print("Got audio bytes! Length:", len(part.inline_data.data))
            print("MIME type:", part.inline_data.mime_type)
            with open("test.wav", "wb") as f:
                f.write(part.inline_data.data)
        else:
            print("No inline data found. Part:", part)
except Exception as e:
    print("Error:", e)
