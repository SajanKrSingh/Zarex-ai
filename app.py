from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import logging
import asyncio
import base64
import re
import json

# Import services and the config module
from services import stt, llm, tts, weather # Import the new weather service
import config as app_config

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

@app.get("/")
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logging.info("WebSocket client connected. Waiting for API keys and config.")
    
    try:
        config_message = await websocket.receive_text()
        config = json.loads(config_message)
        api_keys = config.get("keys", {})
        
        MURF_API_KEY = api_keys.get("murf")
        ASSEMBLYAI_API_KEY = api_keys.get("assemblyai")
        GEMINI_API_KEY = api_keys.get("gemini")
        SERPAPI_API_KEY = api_keys.get("serpapi")
        WEATHER_API_KEY = api_keys.get("weather")
        
        persona = config.get("persona", "zarex")
        
        if not all([MURF_API_KEY, ASSEMBLYAI_API_KEY, GEMINI_API_KEY]):
            logging.error("Missing one or more required API keys.")
            await websocket.close(code=1008, reason="Missing API Keys")
            return
            
        logging.info(f"Config received. Persona: {persona}")

    except (json.JSONDecodeError, KeyError, WebSocketDisconnect) as e:
        logging.error(f"Error receiving/parsing config: {e}")
        await websocket.close(code=1003, reason="Invalid configuration")
        return

    loop = asyncio.get_event_loop()
    chat_history = []

    async def handle_transcript(text: str):
        await websocket.send_json({"type": "final", "text": text})
        
        full_response = ""
        updated_history = list(chat_history) # Make a copy to avoid modifying in place

        # --- Weather Skill Logic ---
        weather_keywords = ["weather", "mausam", "temperature", "tapman"]
        text_lower = text.lower()
        if any(keyword in text_lower for keyword in weather_keywords) and WEATHER_API_KEY:
            # Simple city extraction logic
            city = "current location" # Default
            words = text_lower.split()
            if "in" in words:
                city = text_lower.split(" in ")[-1].strip()
            elif len(words) > 1 and words[-1] not in weather_keywords:
                 city = words[-1].strip()

            logging.info(f"Weather skill triggered for city: {city}")
            full_response = weather.get_weather(city, WEATHER_API_KEY)
            updated_history.append({"role": "user", "content": text})
            updated_history.append({"role": "assistant", "content": full_response})
        
        # --- LLM Logic ---
        else:
            try:
                if ("search for" in text_lower or "what is" in text_lower) and SERPAPI_API_KEY:
                    full_response, updated_history = llm.get_web_response(text, chat_history, GEMINI_API_KEY, SERPAPI_API_KEY, persona)
                else:
                    full_response, updated_history = llm.get_llm_response(text, chat_history, GEMINI_API_KEY, persona)
            except Exception as e:
                logging.error(f"Error in LLM pipeline: {e}")
                await websocket.send_json({"type": "error", "text": "Sorry, an error occurred with the AI response."})
                return

        chat_history.clear()
        chat_history.extend(updated_history)
        await websocket.send_json({"type": "assistant", "text": full_response})

        # --- TTS Logic ---
        try:
            sentences = re.split(r'(?<=[.?!])\s+', full_response.strip())
            for sentence in sentences:
                if sentence.strip():
                    audio_bytes = await loop.run_in_executor(None, tts.speak, sentence.strip(), MURF_API_KEY)
                    if audio_bytes:
                        b64_audio = base64.b64encode(audio_bytes).decode('utf-8')
                        await websocket.send_json({"type": "audio", "b64": b64_audio})
        except Exception as e:
            logging.error(f"Error in TTS pipeline: {e}")


    def on_final_transcript(text: str):
        logging.info(f"Final transcript received: {text}")
        asyncio.run_coroutine_threadsafe(handle_transcript(text), loop)

    app_config.ASSEMBLYAI_API_KEY = ASSEMBLYAI_API_KEY
    
    transcriber = stt.AssemblyAIStreamingTranscriber(
        on_final_callback=on_final_transcript
    )

    try:
        while True:
            data = await websocket.receive_bytes()
            transcriber.stream_audio(data)
    except WebSocketDisconnect:
        logging.info("Client disconnected.")
    finally:
        transcriber.close()
        logging.info("Transcription resources released.")
