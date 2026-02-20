from fastapi import APIRouter, UploadFile, File, Form
from fastapi.responses import JSONResponse
from groq import AsyncGroq
import tempfile, os, re, json
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

# Initialize Groq client
# In production, this would come from settings or env
api_key = os.getenv("GROQ_API_KEY")
client = AsyncGroq(api_key=api_key)

# Technical vocabulary hint — improves Whisper accuracy dramatically
WHISPER_PROMPT = (
    "MindX AI research assistant. Technical terms: "
    "LLM, RAG, API, GPU, CPU, neural network, quantum physics, "
    "machine learning, deep learning, transformer, reinforcement learning, "
    "SearXNG, Groq, Whisper, FastAPI, Python, JavaScript. "
    "Proper nouns, scientific vocabulary, company names, research terms."
)

def clean_transcription(text: str) -> str:
    """Clean common Whisper output issues."""
    if not text: return ""
    
    # Remove trailing period Whisper always adds
    text = text.strip().rstrip('.')
    
    # Remove filler words at start
    text = re.sub(
        r'^(um+|uh+|hmm+|ah+|er+)\s*,?\s*',
        '', text, flags=re.IGNORECASE
    )
    
    # Fix common technical term casing
    corrections = {
        r'\brag\b': 'RAG',
        r'\bllm\b': 'LLM',
        r'\bapi\b': 'API',
        r'\bgpu\b': 'GPU',
        r'\bgpt\b': 'GPT',
        r'\bai\b':  'AI',
        r'\bml\b':  'ML',
        r'\bmindx\b': 'MindX',
        r'\bsearxng\b': 'SearXNG',
    }
    for pattern, replacement in corrections.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    
    return text.strip()

def detect_voice_command(text: str) -> dict:
    """
    Detect if transcribed text is a command rather than a search query.
    Returns command info or marks as regular query.
    """
    t = text.lower().strip()
    
    COMMANDS = {
        'new chat':        'new_chat',
        'start new chat':  'new_chat',
        'clear chat':      'clear_chat',
        'clear history':   'clear_chat',
        'scroll down':     'scroll_down',
        'scroll up':       'scroll_up',
        'go to top':       'scroll_top',
        'go to bottom':    'scroll_bottom',
        'copy answer':     'copy_last_answer',
        'copy that':       'copy_last_answer',
        'read answer':     'read_aloud',
        'read that':       'read_aloud',
        'read aloud':      'read_aloud',
        'stop reading':    'stop_reading',
        'dark mode':       'dark_mode',
        'light mode':      'light_mode',
    }
    
    for phrase, action in COMMANDS.items():
        if phrase in t:
            return {'is_command': True, 'action': action}
    
    return {'is_command': False}


# ── ENDPOINT 1: Standard Transcription ──────────

@router.post("/voice/transcribe")
async def transcribe_audio(audio: UploadFile = File(...)):
    """
    Receive audio blob → Whisper → clean text → return.
    Used for normal voice input.
    """
    try:
        suffix = ".webm"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            content: bytes = await audio.read()
            
            # Quality check — reject if too small (silence/noise)
            if len(content) < 3000:
                return JSONResponse({
                    "success": False,
                    "error": "Recording too short. Please speak clearly."
                })
            
            tmp.write(content)
            tmp_path = tmp.name

        try:
            with open(tmp_path, "rb") as f:
                transcription = await client.audio.transcriptions.create(
                    model="whisper-large-v3",
                    file=f,
                    language="en",
                    response_format="text",
                    prompt=WHISPER_PROMPT
                )

            text = clean_transcription(transcription.strip())
            
            if not text:
                return JSONResponse({
                    "success": False,
                    "error": "Could not understand audio. Please try again."
                })

            # Check for voice command
            command_check = detect_voice_command(text)
            
            return JSONResponse({
                "success": True,
                "text": text,
                "is_command": command_check['is_command'],
                "action": command_check.get('action'),
            })
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    except Exception as e:
        logger.error(f"Transcription failed: {str(e)}")
        return JSONResponse({
            "success": False,
            "error": f"Transcription failed: {str(e)}"
        }, status_code=500)


# ── ENDPOINT 2: Chunk Transcription (for live preview) ──

@router.post("/voice/transcribe-chunk")
async def transcribe_chunk(
    audio: UploadFile = File(...),
    is_final: bool = Form(False)
):
    """
    Transcribe audio chunk for live preview while still recording.
    Called every 3 seconds during recording.
    """
    try:
        const_content: bytes = await audio.read()
        
        if len(const_content) < 2000:
            return JSONResponse({"success": True, "text": "", "is_final": is_final})

        with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as tmp:
            tmp.write(const_content)
            tmp_path = tmp.name

        try:
            with open(tmp_path, "rb") as f:
                transcription = await client.audio.transcriptions.create(
                    model="whisper-large-v3",
                    file=f,
                    language="en",
                    response_format="text",
                    prompt=WHISPER_PROMPT
                )

            text = clean_transcription(transcription.strip())

            return JSONResponse({
                "success": True,
                "text": text,
                "is_final": is_final
            })
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    except Exception as e:
        return JSONResponse({
            "success": False,
            "text": "",
            "is_final": is_final
        })


# ── ENDPOINT 3: Language Auto-Detect + Translate ──

@router.post("/voice/transcribe-multilang")
async def transcribe_multilang(audio: UploadFile = File(...)):
    """
    Auto-detect language. If non-English, translate to English.
    Supports Tamil, Hindi, and 97 other languages automatically.
    """
    try:
        content: bytes = await audio.read()
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        try:
            # First pass — detect language
            with open(tmp_path, "rb") as f:
                # Verbose JSON returns the language
                detection = await client.audio.transcriptions.create(
                    model="whisper-large-v3",
                    file=f,
                    response_format="verbose_json",  # returns language info
                    prompt=WHISPER_PROMPT
                )

            # Accessing dict-style or attribute-style safely
            det_dict = detection if isinstance(detection, dict) else detection.model_dump()
            detected_lang = det_dict.get('language', 'en')
            original_text = clean_transcription(det_dict.get('text', '').strip())

            # If non-English — translate to English
            if detected_lang != 'en':
                with open(tmp_path, "rb") as f:
                    translation = await client.audio.translations.create(
                        model="whisper-large-v3",
                        file=f,
                        prompt=WHISPER_PROMPT
                    )
                english_text = clean_transcription(translation.text.strip())
            else:
                english_text = original_text

            return JSONResponse({
                "success": True,
                "text": english_text,
                "original_text": original_text,
                "detected_language": detected_lang,
                "was_translated": detected_lang != 'en',
                "is_command": detect_voice_command(english_text)['is_command'],
                "action": detect_voice_command(english_text).get('action')
            })
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    except Exception as e:
        logger.error(f"Multilang transcription failed: {str(e)}")
        return JSONResponse({
            "success": False,
            "error": str(e)
        }, status_code=500)
