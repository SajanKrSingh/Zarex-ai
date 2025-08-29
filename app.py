from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import logging
import asyncio
import base64
import re
import json

# Import services and the config module
from services import stt, llm, tts
import config as app_config  # Import config to modify it at runtime

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
    logging.info("WebSocket client connected. Waiting for API keys.")
    
    try:
        config_message = await websocket.receive_text()
        config = json.loads(config_message)
        api_keys = config.get("keys", {})
        
        MURF_API_KEY = api_keys.get("murf")
        ASSEMBLYAI_API_KEY = api_keys.get("assemblyai")
        GEMINI_API_KEY = api_keys.get("gemini")
        SERPAPI_API_KEY = api_keys.get("serpapi")
        
        if not all([MURF_API_KEY, ASSEMBLYAI_API_KEY, GEMINI_API_KEY]):
            logging.error("Missing one or more required API keys.")
            await websocket.close(code=1008, reason="Missing API Keys")
            return
            
        logging.info("API Keys received successfully.")

    except (json.JSONDecodeError, KeyError, WebSocketDisconnect) as e:
        logging.error(f"Error receiving/parsing config: {e}")
        await websocket.close(code=1003, reason="Invalid configuration")
        return

    loop = asyncio.get_event_loop()
    chat_history = []

    async def handle_transcript(text: str):
        await websocket.send_json({"type": "final", "text": text})
        try:
            if ("search for" in text.lower() or "what is" in text.lower()) and SERPAPI_API_KEY:
                # Pass all required keys to the web response function
                full_response, updated_history = llm.get_web_response(text, chat_history, GEMINI_API_KEY, SERPAPI_API_KEY)
            else:
                full_response, updated_history = llm.get_llm_response(text, chat_history, GEMINI_API_KEY)
            
            chat_history.clear()
            chat_history.extend(updated_history)
            await websocket.send_json({"type": "assistant", "text": full_response})

            sentences = re.split(r'(?<=[.?!])\s+', full_response.strip())
            for sentence in sentences:
                if sentence.strip():
                    audio_bytes = await loop.run_in_executor(None, tts.speak, sentence.strip(), MURF_API_KEY)
                    if audio_bytes:
                        b64_audio = base64.b64encode(audio_bytes).decode('utf-8')
                        await websocket.send_json({"type": "audio", "b64": b64_audio})

        except Exception as e:
            logging.error(f"Error in LLM/TTS pipeline: {e}")
            await websocket.send_json({"type": "error", "text": "Sorry, an error occurred."})

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