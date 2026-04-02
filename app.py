from fastapi import FastAPI, WebSocket, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import asyncio
import json
import os
import tempfile
import uuid
import sqlite3
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

from sarvamai import SarvamAI
import google.generativeai as genai
import boto3
from commands import route_command

load_dotenv()

SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

genai.configure(api_key=GEMINI_API_KEY)
gemini_client = genai.GenerativeModel("gemini-2.5-flash")
polly_client = boto3.client("polly", region_name="us-east-1")

# === DATABASE SETUP ===
DB_PATH = Path(__file__).parent / "chats.db"

def init_database():
    """Initialize SQLite database with schema"""
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    # Create conversations table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            language TEXT DEFAULT 'unknown',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Create messages table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            language TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
        )
    """)
    
    # Create indexes for performance
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_conversation_id ON messages(conversation_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_created_at ON conversations(created_at DESC)")
    
    # Add is_favorite column to conversations if not exists
    try:
        cursor.execute("ALTER TABLE conversations ADD COLUMN is_favorite BOOLEAN DEFAULT 0")
    except sqlite3.OperationalError:
        pass  # Column already exists
    
    # Create notes table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notes (
            id TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
        )
    """)
    
    # Create reminders table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL,
            content TEXT NOT NULL,
            trigger_time DATETIME NOT NULL,
            completed BOOLEAN DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
        )
    """)
    
    # Create indexes for reminders and notes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_reminder_trigger ON reminders(trigger_time)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_notes_conversation ON notes(conversation_id)")
    
    conn.commit()
    conn.close()
    print("✅ Database initialized")

def get_db_connection():
    """Get database connection with row factory"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def save_message(conversation_id: str, role: str, content: str, language: str = "unknown"):
    """Save a message to database"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        message_id = str(uuid.uuid4())
        
        cursor.execute("""
            INSERT INTO messages (id, conversation_id, role, content, language)
            VALUES (?, ?, ?, ?, ?)
        """, (message_id, conversation_id, role, content, language))
        
        # Update conversation updated_at
        cursor.execute("""
            UPDATE conversations SET updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (conversation_id,))
        
        conn.commit()
        conn.close()
        return message_id
    except Exception as e:
        print(f"Error saving message: {e}")
        return None

def create_conversation(language: str = "unknown", title: str = None) -> str:
    """Create a new conversation"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        conv_id = str(uuid.uuid4())
        
        # If title is not provided, use a timestamp-based default
        if not title:
            title = f"Conversation {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        
        cursor.execute("""
            INSERT INTO conversations (id, title, language)
            VALUES (?, ?, ?)
        """, (conv_id, title, language))
        
        conn.commit()
        conn.close()
        print(f"✅ Created conversation: {conv_id}")
        return conv_id
    except Exception as e:
        print(f"Error creating conversation: {e}")
        return None

def update_conversation_title(conversation_id: str, title: str):
    """Update conversation title"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE conversations SET title = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (title, conversation_id))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Error updating conversation: {e}")
        return False

def get_conversations(limit: int = 50, offset: int = 0):
    """Get all conversations with messages (latest first) - filters out empty conversations"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT c.id, c.title, c.language, c.created_at, c.updated_at, c.is_favorite,
                   COUNT(m.id) as message_count
            FROM conversations c
            LEFT JOIN messages m ON c.id = m.conversation_id
            GROUP BY c.id
            HAVING COUNT(m.id) > 0
            ORDER BY c.is_favorite DESC, c.updated_at DESC
            LIMIT ? OFFSET ?
        """, (limit, offset))
        rows = cursor.fetchall()
        conn.close()
        # Remove the message_count from the response (keep it in dict but not sent)
        return [dict(row) for row in rows]
    except Exception as e:
        print(f"Error fetching conversations: {e}")
        return []

def get_conversation_messages(conversation_id: str):
    """Get all messages for a conversation"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, conversation_id, role, content, language, timestamp
            FROM messages
            WHERE conversation_id = ?
            ORDER BY timestamp ASC
        """, (conversation_id,))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]
    except Exception as e:
        print(f"Error fetching messages: {e}")
        return []

def search_conversations(query: str):
    """Search conversations by title or content"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        search_term = f"%{query}%"
        
        cursor.execute("""
            SELECT DISTINCT c.id, c.title, c.language, c.created_at, c.updated_at
            FROM conversations c
            LEFT JOIN messages m ON c.id = m.conversation_id
            WHERE c.title LIKE ? OR m.content LIKE ?
            ORDER BY c.updated_at DESC
        """, (search_term, search_term))
        
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]
    except Exception as e:
        print(f"Error searching conversations: {e}")
        return []

def delete_conversation(conversation_id: str):
    """Delete a conversation and all its messages"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Error deleting conversation: {e}")
        return False

def generate_title_from_message(text: str, language: str = "unknown") -> str:
    """Generate a conversation title from the first user message"""
    # Truncate to first 50 characters, capitalize
    title = text.strip()[:50]
    if len(text.strip()) > 50:
        title += "..."
    return title if title else f"Conversation {datetime.now().strftime('%H:%M')}"

# Initialize database on startup
init_database()

app = FastAPI(title="VaaniAI API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === API ROUTES (must be BEFORE the catch-all route) ===
@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "VaaniAI API"}

@app.post("/api/conversations")
async def create_new_conversation(request: dict):
    """Create a new conversation"""
    try:
        language = request.get("language", "unknown")
        title = request.get("title")
        conv_id = create_conversation(language, title)
        if conv_id:
            return {"id": conv_id, "title": title or f"Conversation {datetime.now().strftime('%Y-%m-%d %H:%M')}", "language": language}
        else:
            raise HTTPException(status_code=500, detail="Failed to create conversation")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/conversations")
async def list_conversations(limit: int = 50, offset: int = 0):
    """Get list of all conversations"""
    try:
        conversations = get_conversations(limit, offset)
        print(f"DEBUG: Returning {len(conversations)} conversations from DB")
        return {"conversations": conversations, "count": len(conversations)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/conversations/search")
async def search_convs(q: str):
    """Search conversations by query"""
    try:
        if not q or len(q) < 1:
            raise ValueError("Query must be provided")
        results = search_conversations(q)
        return {"results": results, "count": len(results)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/conversations/{conversation_id}")  
async def get_conversation(conversation_id: str):
    """Get conversation details and messages"""
    try:
        # Skip if trying to access /search
        if conversation_id == "search":
            raise HTTPException(status_code=404, detail="Not found")
            
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM conversations WHERE id = ?", (conversation_id,))
        conv = cursor.fetchone()
        conn.close()
        
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        messages = get_conversation_messages(conversation_id)
        return {"conversation": dict(conv), "messages": messages}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/conversations/{conversation_id}")
async def update_conversation(conversation_id: str, request: dict):
    """Update conversation title"""
    try:
        title = request.get("title")
        if not title:
            raise ValueError("Title required")
        if update_conversation_title(conversation_id, title):
            return {"id": conversation_id, "title": title}
        else:
            raise HTTPException(status_code=500, detail="Update failed")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/conversations/{conversation_id}")
async def delete_conv(conversation_id: str):
    """Delete a conversation"""
    try:
        if delete_conversation(conversation_id):
            return {"status": "deleted", "id": conversation_id}
        else:
            raise HTTPException(status_code=500, detail="Deletion failed")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/transcribe")
async def transcribe_audio(language_code: str = "unknown"):
    try:
        return {"error": "Use WebSocket for real-time transcription"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/process-text")
async def process_text(request: dict):
    try:
        transcript = request.get("transcript", "")
        language_code = request.get("language_code", "en")
        
        if not transcript:
            raise ValueError("No transcript provided")
        
        response_native, response_transliterated = gemini_process(transcript, language_code)
        return {"response": response_native}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/synthesize")
async def synthesize_speech(request: dict):
    try:
        text = request.get("text", "")
        if not text:
            raise ValueError("No text provided")
        
        response = polly_client.synthesize_speech(
            Text=text,
            OutputFormat="mp3",
            VoiceId="Aditi"
        )
        
        audio_data = response["AudioStream"].read()
        import base64
        return {
            "audio": base64.b64encode(audio_data).decode(),
            "format": "mp3"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
async def root():
    """Serve index.html at root"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    file_full_path = os.path.join(current_dir, "index.html")
    if os.path.exists(file_full_path):
        return FileResponse(file_full_path, media_type="text/html")
    return {"error": "index.html not found"}, 404

@app.get("/landing")
async def landing():
    """Serve landing page"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    file_full_path = os.path.join(current_dir, "landing.html")
    if os.path.exists(file_full_path):
        return FileResponse(file_full_path, media_type="text/html")
    return {"error": "landing.html not found"}, 404

# Mount static files - serve CSS, JS directly from root (this MUST be the LAST route)
current_dir = os.path.dirname(os.path.abspath(__file__))

@app.get("/{file_path:path}")
async def serve_static(file_path: str):
    """Serve static files (CSS, JS) and index.html from current directory"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Don't serve API or WebSocket routes through this handler
    if "/" in file_path and (file_path.split("/")[0] in ["api", "ws"]):
        # Let the API routes handle it
        raise HTTPException(status_code=404, detail="Not found")
    
    # Handle root path
    if file_path == "" or file_path == "/":
        file_full_path = os.path.join(current_dir, "index.html")
        if os.path.exists(file_full_path):
            return FileResponse(file_full_path, media_type="text/html")
        return {"error": "index.html not found"}, 404
    
    # Handle static files
    if file_path in ["style.css", "scripts.js", "index.html", "landing.html"]:
        file_full_path = os.path.join(current_dir, file_path)
        if os.path.exists(file_full_path):
            if file_path.endswith('.css'):
                return FileResponse(file_full_path, media_type="text/css")
            elif file_path.endswith('.js'):
                return FileResponse(file_full_path, media_type="application/javascript")
            elif file_path.endswith('.html'):
                return FileResponse(file_full_path, media_type="text/html")
            return FileResponse(file_full_path)
    return {"error": "File not found"}, 404

# === CONVERSATION MEMORY ===
conversation_histories = {}  # {conversation_id: [{"role": "user"/"assistant", "content": "...", "language": "..."}]}

# === EMOTION SYSTEM ===
EMOTION_SSML = {
    "happy":   {"rate": "fast",   "pitch": "+3st", "volume": "loud"},
    "sad":     {"rate": "slow",   "pitch": "-2st", "volume": "soft"},
    "angry":   {"rate": "medium", "pitch": "+1st", "volume": "x-loud"},
    "anxious": {"rate": "medium", "pitch": "+2st", "volume": "medium"},
    "neutral": {"rate": "medium", "pitch": "0st",  "volume": "medium"},
    "curious": {"rate": "medium", "pitch": "+2st", "volume": "medium"},
    "excited": {"rate": "fast",   "pitch": "+4st", "volume": "loud"},
}

EMOTION_TONE = {
    "happy":   "Be warm, cheerful, and celebratory.",
    "sad":     "Be gentle, empathetic, and comforting. Use soft language.",
    "angry":   "Be calm, non-confrontational, and de-escalating.",
    "anxious": "Be reassuring, clear, and calming.",
    "curious": "Be enthusiastic, detailed, and engaging.",
    "excited": "Match the energy! Be enthusiastic and expressive.",
    "neutral": "Be helpful and conversational.",
}

EMOTION_EXPRESSIONS = {
    "happy": "Add a light laugh like 'haha' or 'that's awesome!'",
    "sad": "Start with empathy like 'oh...' or 'I'm sorry...'",
    "angry": "Stay calm and grounding",
    "excited": "Use 'wow!!' or 'this is amazing!'",
    "curious": "Use 'hmm...' or 'interesting...'",
}

PAUSE_MAP = {
    "happy": "200ms",
    "sad": "500ms",
    "angry": "150ms",
    "anxious": "300ms",
    "excited": "100ms",
    "neutral": "250ms",
    "curious": "250ms"
}

# === USER MEMORY (session-level) ===
user_memory = {}

def get_memory_context(session_id, current_query):
    history = user_memory.get(session_id, [])
    if not history:
        return ""

    # Keep last 6 messages for continuity
    recent = history[-6:]

    # Simple relevance filter (keyword match)
    relevant = []
    for m in history:
        if any(word in m["text"].lower() for word in current_query.lower().split()):
            relevant.append(m)

    # Limit relevant memory
    relevant = relevant[-4:]

    lines = []

    if relevant:
        lines.append("Relevant past context:")
        lines.extend([f"{m['role'].upper()}: {m['text']}" for m in relevant])

    lines.append("\nRecent conversation:")
    lines.extend([f"{m['role'].upper()}: {m['text']}" for m in recent])

    return "\n\n" + "\n".join(lines) + "\n"

def update_memory(session_id, user_text, ai_text, emotion):
    if session_id not in user_memory:
        user_memory[session_id] = []
    user_memory[session_id].append({"role": "user", "text": user_text, "emotion": emotion})
    user_memory[session_id].append({"role": "ai", "text": ai_text})
    user_memory[session_id] = user_memory[session_id][-20:]


# === WEBSOCKET ===
@app.websocket("/ws/chat")
async def websocket_endpoint(websocket: WebSocket, conversation_id: str = None):
    await websocket.accept()
    print("WebSocket client connected")
    
    # Track if we need to create a conversation on first message
    if conversation_id:
        # Load existing conversation history from database
        messages = get_conversation_messages(conversation_id)
        conversation_histories[conversation_id] = messages
        print(f"✅ Loaded existing conversation: {conversation_id} ({len(messages)} messages)")
    else:
        conversation_id = None
        print("WebSocket ready - will create conversation on first message")
    
    # Send client the conversation ID (None if new)
    await websocket.send_json({
        "type": "conversation_id",
        "conversation_id": conversation_id
    })
    
    has_user_message = False  # Track if we need to auto-title
    
    try:
        while True:
            try:
                data = await websocket.receive_text()
                message = json.loads(data)
                
                # CREATE CONVERSATION ON FIRST MESSAGE (if not already created)
                if not conversation_id:
                    conversation_id = create_conversation()
                    conversation_histories[conversation_id] = []
                    print(f"✅ Created conversation on first message: {conversation_id}")
                    # Send the new conversation_id to client
                    await websocket.send_json({
                        "type": "conversation_id",
                        "conversation_id": conversation_id
                    })
                
                if message.get("type") == "audio":
                    audio_base64 = message.get("audio")
                    language_code = message.get("language_code", "unknown")
                    
                    import base64
                    audio_bytes = base64.b64decode(audio_base64)
                    
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
                        tmp.write(audio_bytes)
                        tmp_path = tmp.name
                    
                    await websocket.send_json({
                        "type": "pipeline",
                        "stage": "stt",
                        "status": "active",
                        "message": "Transcribing with Sarvam STT..."
                    })
                    
                    transcript, detected_lang = sarvam_transcribe(tmp_path, language_code)
                    
                    if not transcript:
                        await websocket.send_json({
                            "type": "error",
                            "message": "Transcription failed"
                        })
                        if os.path.exists(tmp_path):
                            os.unlink(tmp_path)
                        continue
                    
                    await websocket.send_json({
                        "type": "transcript",
                        "text": transcript
                    })
                    
                    # ===== CHECK FOR DIRECT COMMAND (no LLM processing) =====
                    # Get conversation messages for export
                    messages = get_conversation_messages(conversation_id) if conversation_id else []
                    
                    is_direct_command, command_response = route_command(transcript, conversation_id, messages)
                    
                    if is_direct_command and command_response:
                        # Direct command - execute and return immediately
                        print(f"✅ Direct command detected: {command_response.get('type')}")
                        
                        # Save user message to database
                        save_message(conversation_id, "user", transcript, detected_lang)
                        
                        # Send command response to client
                        await websocket.send_json({
                            "type": "command_response",
                            "command": command_response
                        })
                        
                        # Save command response as assistant message for conversation context
                        response_text = command_response.get("text", "")
                        save_message(conversation_id, "assistant", response_text, detected_lang)
                        
                        # Update in-memory history
                        conversation_histories[conversation_id].append({
                            "role": "user",
                            "content": transcript,
                            "language": detected_lang
                        })
                        conversation_histories[conversation_id].append({
                            "role": "assistant",
                            "content": response_text,
                            "language": detected_lang
                        })
                        
                        # Complete pipeline
                        await websocket.send_json({
                            "type": "pipeline",
                            "stage": "complete",
                            "status": "complete",
                            "message": "Command executed! Press to talk again"
                        })
                        
                        if os.path.exists(tmp_path):
                            os.unlink(tmp_path)
                        continue
                    
                    # Not a direct command - continue with LLM processing
                    await websocket.send_json({
                        "type": "pipeline",
                        "stage": "nlp",
                        "status": "active",
                        "message": "Processing with Gemini NLP..."
                    })
                    
                    # Get conversation history
                    history = conversation_histories.get(conversation_id, [])
                    
                    # Process with history
                    response_native, response_transliterated = gemini_process(transcript, detected_lang, history)
                    
                    # Store in conversation history
                    if response_native and response_transliterated:
                        # Save user message to database
                        save_message(conversation_id, "user", transcript, detected_lang)
                        
                        # Save assistant response to database
                        save_message(conversation_id, "assistant", response_native, detected_lang)
                        
                        # Update in-memory history
                        conversation_histories[conversation_id].append({
                            "role": "user",
                            "content": transcript,
                            "language": detected_lang
                        })
                        conversation_histories[conversation_id].append({
                            "role": "assistant",
                            "content": response_native,
                            "language": detected_lang
                        })
                        print(f"Conversation history updated (messages: {len(conversation_histories[conversation_id])})")

                    if not response_native or not response_transliterated:
                        await websocket.send_json({
                            "type": "error",
                            "message": "Processing failed"
                        })
                        if os.path.exists(tmp_path):
                            os.unlink(tmp_path)
                        continue
                    
                    await websocket.send_json({
                        "type": "response",
                        "text": response_native
                    })
                    
                    await websocket.send_json({
                        "type": "pipeline",
                        "stage": "llm",
                        "status": "active",
                        "message": "Generating response with Gemini LLM..."
                    })
                    
                    await asyncio.sleep(0.3)
                    
                    await websocket.send_json({
                        "type": "pipeline",
                        "stage": "tts",
                        "status": "active",
                        "message": "Synthesizing with Polly TTS..."
                    })
                    
                    audio_data = polly_synthesize(response_transliterated)
                    
                    if audio_data:
                        import base64
                        audio_base64 = base64.b64encode(audio_data).decode()
                        audio_id = str(uuid.uuid4())
                        
                        print(f"Sending audio (ID: {audio_id}, size: {len(audio_base64)} chars)")
                        
                        await websocket.send_json({
                            "type": "audio",
                            "data": audio_base64,
                            "format": "mp3",
                            "audioId": audio_id
                        })
                        
                        print(f"Audio sent successfully")
                    else:
                        print(f"⚠️ No audio data generated")
                        await websocket.send_json({
                            "type": "error",
                            "message": "⚠️ Audio generation failed"
                        })
                    
                    await websocket.send_json({
                        "type": "pipeline",
                        "stage": "complete",
                        "status": "complete",
                        "message": "Pipeline Complete! Press to talk again"
                    })
                    
                    if os.path.exists(tmp_path):
                        os.unlink(tmp_path)
                    
                elif message.get("type") == "text":
                    # Handle typed text directly (skip STT)
                    text = message.get("text", "").strip()
                    language_code = message.get("language_code", "unknown")
                    
                    # Auto-detect language from text if not explicitly set
                    if language_code == "unknown":
                        language_code = detect_language_from_text(text)
                    
                    if not text:
                        await websocket.send_json({
                            "type": "error",
                            "message": "No text provided"
                        })
                        continue
                    
                    # ===== CHECK FOR DIRECT COMMAND (no LLM processing) =====
                    # Get conversation messages for export
                    messages = get_conversation_messages(conversation_id) if conversation_id else []
                    
                    is_direct_command, command_response = route_command(text, conversation_id, messages)
                    
                    if is_direct_command and command_response:
                        # Direct command - execute and return immediately
                        print(f"✅ Direct command detected: {command_response.get('type')}")
                        
                        # Save user message to database
                        save_message(conversation_id, "user", text, language_code)
                        
                        # Send command response to client
                        await websocket.send_json({
                            "type": "command_response",
                            "command": command_response
                        })
                        
                        # Save command response as assistant message for conversation context
                        response_text = command_response.get("text", "")
                        save_message(conversation_id, "assistant", response_text, language_code)
                        
                        # Update in-memory history
                        conversation_histories[conversation_id].append({
                            "role": "user",
                            "content": text,
                            "language": language_code
                        })
                        conversation_histories[conversation_id].append({
                            "role": "assistant",
                            "content": response_text,
                            "language": language_code
                        })
                        
                        # Complete pipeline
                        await websocket.send_json({
                            "type": "pipeline",
                            "stage": "complete",
                            "status": "complete",
                            "message": "Command executed! Press to talk again"
                        })
                        
                        continue
                    
                    # Not a direct command - continue with LLM processing
                    await websocket.send_json({
                        "type": "pipeline",
                        "stage": "nlp",
                        "status": "active",
                        "message": "Processing with Gemini..."
                    })
                    
                    # Get conversation history
                    history = conversation_histories.get(conversation_id, [])
                    
                    # Process with history
                    response_native, response_transliterated = gemini_process(text, language_code, history)
                    
                    # Store in conversation history
                    if response_native and response_transliterated:
                        # Save user message to database
                        save_message(conversation_id, "user", text, language_code)
                        
                        # Save assistant response to database
                        save_message(conversation_id, "assistant", response_native, language_code)
                        
                        # Update in-memory history
                        conversation_histories[conversation_id].append({
                            "role": "user",
                            "content": text,
                            "language": language_code
                        })
                        conversation_histories[conversation_id].append({
                            "role": "assistant",
                            "content": response_native,
                            "language": language_code
                        })
                        print(f"Conversation history updated (messages: {len(conversation_histories[conversation_id])})")
                        
                        # Auto-title on first message
                        if not has_user_message:
                            title = generate_title_from_message(text, language_code)
                            update_conversation_title(conversation_id, title)
                            has_user_message = True
                            print(f"✅ Auto-titled conversation: {title}")

                    if not response_native or not response_transliterated:
                        await websocket.send_json({
                            "type": "error",
                            "message": "Processing failed"
                        })
                        continue
                    
                    await websocket.send_json({
                        "type": "response",
                        "text": response_native
                    })
                    
                    await websocket.send_json({
                        "type": "pipeline",
                        "stage": "tts",
                        "status": "active",
                        "message": "Synthesizing with Polly TTS..."
                    })
                    
                    audio_data = polly_synthesize(response_transliterated)
                    
                    if audio_data:
                        import base64
                        audio_base64 = base64.b64encode(audio_data).decode()
                        audio_id = str(uuid.uuid4())
                        
                        print(f"Sending audio (ID: {audio_id}, size: {len(audio_base64)} chars)")
                        
                        await websocket.send_json({
                            "type": "audio",
                            "data": audio_base64,
                            "format": "mp3",
                            "audioId": audio_id
                        })
                        
                        print(f"Audio sent successfully")
                    else:
                        print(f"No audio data generated")
                        await websocket.send_json({
                            "type": "error",
                            "message": "Audio generation failed"
                        })
                    
                    await websocket.send_json({
                        "type": "pipeline",
                        "stage": "complete",
                        "status": "complete",
                        "message": "Pipeline Complete!"
                    })
                    
                elif message.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
                    
            except json.JSONDecodeError as json_err:
                print(f"JSON error: {json_err}")
                try:
                    await websocket.send_json({"type": "error", "message": "Invalid message format"})
                except Exception:
                    break
            except Exception as msg_err:
                print(f"Message processing error: {msg_err}")
                try:
                    await websocket.send_json({"type": "error", "message": f"Error: {str(msg_err)[:100]}"})
                except Exception:
                    break
    
    except Exception as e:
        print(f"WebSocket loop ended: {e}")
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
        print("WebSocket client disconnected")



# === CORE FUNCTIONS ===

def sarvam_transcribe(audio_file_path, language_code="unknown"):
    import shutil
    
    output_dir = tempfile.mkdtemp(prefix="sarvam_")
    transcript = None
    detected_language = "unknown"
    
    try:
        client = SarvamAI(api_subscription_key=SARVAM_API_KEY)
        
        job = client.speech_to_text_job.create_job(
            model="saaras:v3",
            mode="transcribe",
            language_code=language_code,
            with_diarization=False,
            num_speakers=1
        )
        
        job.upload_files(file_paths=[audio_file_path])
        job.start()
        job.wait_until_complete()
        
        file_results = job.get_file_results()
        
        if file_results['successful']:
            job.download_outputs(output_dir=output_dir)
            
            for file in os.listdir(output_dir):
                if file.endswith('.json'):
                    with open(os.path.join(output_dir, file), 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        transcript = data.get('transcript', '')
                        detected_language = data.get('language_code', 'unknown')
                        print(f"Sarvam transcribed: {transcript[:50]}... (Language: {detected_language})")
                        break
        else:
            print("Sarvam transcription failed")
    
    except Exception as e:
        print(f"Sarvam error: {e}")
    
    finally:
        try:
            shutil.rmtree(output_dir, ignore_errors=True)
        except:
            pass
    
    return transcript, detected_language

def gemini_process(transcript, language_code="en", history=None):
    try:
        # Build conversation context from history
        context = ""
        if history and len(history) > 0:
            # Include last 5 exchanges to keep context relevant
            recent_history = history[-10:]  # Get last 5 user-assistant exchanges
            context = "\n\nPrevious conversation:\n"
            for msg in recent_history:
                role = msg.get("role", "")
                content = msg.get("content", "")
                if role == "user":
                    context += f"User: {content}\n"
                elif role == "assistant":
                    context += f"Assistant: {content}\n"
        
        language_map = {
            "hi": "Hindi", "hi-IN": "Hindi",
            "kn": "Kannada", "kn-IN": "Kannada",
            "ta": "Tamil", "ta-IN": "Tamil",
            "te": "Telugu", "te-IN": "Telugu",
            "mr": "Marathi", "mr-IN": "Marathi",
            "gu": "Gujarati", "gu-IN": "Gujarati",
            "en": "English", "en-IN": "English",
            "unknown": "English"
        }
        
        language_name = language_map.get(language_code, "English")
        
        # Check if input is Hinglish (Roman Hindi)
        is_hinglish = is_text_hinglish(transcript)
        
        if language_code in ["en", "en-IN", "unknown"]:
            prompt = f"""You are a helpful assistant having a natural conversation in English. Remember the conversation context to provide relevant, coherent responses.{context}

Current user input: "{transcript}"

Respond naturally and helpfully:
- Keep response to 1-2 sentences
- Be conversational and natural
- Answer the user's question properly
- Do NOT repeat the input
- Do NOT use any non-English text
- Consider previous context when responding

NOW RESPOND:"""
            
            response = gemini_client.generate_content(prompt)
            result = response.text.strip()
            return result, result
        
        elif is_hinglish or (language_code in ["hi", "hi-IN"] and has_roman_characters(transcript)):
            # Handle Hinglish input - respond in Hinglish (Roman Hindi)
            prompt_hinglish = f"""You are a helpful assistant. The user is speaking Hinglish (Roman Hindi - Hindi written with Latin letters). Remember the conversation context to maintain consistency.{context}

Current user input: "{transcript}"

RESPOND IN HINGLISH (Hindi written with Latin/Roman letters):
- Use Roman/Latin letters only (like "haan", "nahi", "kaise", "mereko")
- Keep response to 1-2 sentences
- Be natural and conversational
- Answer the user's question properly
- Consider previous context when responding
- Do NOT use Devanagari script
- Do NOT use pure English

RESPOND IN HINGLISH:"""
            
            response = gemini_client.generate_content(prompt_hinglish)
            hinglish_response = response.text.strip()
            return hinglish_response, hinglish_response
        
        else:
            # Handle pure native script input
            prompt_native = f"""You MUST respond ONLY in {language_name} using native characters. Remember the conversation context to provide consistent, relevant responses.{context}

Current user input: "{transcript}"

STRICT RULES:
1. ONLY use {language_name} native script
2. NO English words
3. NO Latin letters
4. NO mixing languages
5. Keep response 1-2 sentences
6. Natural and conversational tone
7. Answer the user's question
8. Consider previous context in your response

RESPOND NOW IN PURE {language_name} NATIVE SCRIPT ONLY:"""
            
            response_native = gemini_client.generate_content(prompt_native)
            native_response = response_native.text.strip()
            
            prompt_transliteration = f"""Transliterate this {language_name} text to English/Latin letters (Romanization):

{language_name} text: "{native_response}"

Rules:
- Only English/Latin letters
- Preserve pronunciation
- Keep punctuation
- No explanations
- Output ONLY the transliterated text

Transliterated:"""
            
            response_transliteration = gemini_client.generate_content(prompt_transliteration)
            transliteration = response_transliteration.text.strip()
            
            return native_response, transliteration
    except Exception as e:
        print("Gemini error:", e)
        import traceback
        traceback.print_exc()
        return None, None
    
def polly_synthesize(text):
    try:
        print(f"Polly synthesizing: {text[:50]}...")
        
        response = polly_client.synthesize_speech(
            Text=text,
            OutputFormat="mp3",
            VoiceId="Aditi"
        )
        
        audio_bytes = response["AudioStream"].read()
        print(f"Polly generated {len(audio_bytes)} bytes of audio")
        return audio_bytes
    except Exception as e:
        print(f"Polly error: {e}")
        import traceback
        traceback.print_exc()
        return None
    

def is_text_hinglish(text):
    """Check if text appears to be Hinglish (Roman Hindi with Hindi words)"""
    hinglish_indicators = [
        'haan', 'nahi', 'mereko', 'mujhe', 'tujhe', 'inhe', 'unhe',
        'kya', 'kaise', 'kyun', 'kaun', 'kaha', 'kab',
        'acha', 'accha', 'theek', 'sahi', 'galat',
        'hum', 'tum', 'main', 'maine', 'tumare', 'uske',
        'padao', 'bataao', 'dikhaao', 'samjhao', 'sikhao',
        'kar', 'karo', 'kiya', 'hai', 'hain', 'ho', 'tha', 'the',
        'isme', 'usme', 'ismein', 'usmein',
        'aur', 'ya', 'par', 'lekin', 'to', 'toh',
        'bahut', 'bohat', 'achha', 'bilkul', 'theek',
        'dhanyavaad', 'shukriya', 'namaste', 'namaskar'
    ]
    
    text_lower = text.lower()
    words = text_lower.split()
    
    count = sum(1 for word in words if any(indicator in ''.join(c for c in word if c.isalnum()) for indicator in hinglish_indicators))
    return len(words) > 0 and count / len(words) >= 0.2

def has_roman_characters(text):
    """Check if text is primarily in Roman/Latin characters"""
    for char in text:
        code = ord(char)
        # Check if any character is a native Indian script character
        if (0x0900 <= code <= 0x097F or  # Devanagari
            0x0C80 <= code <= 0x0CFF or  # Kannada
            0x0B80 <= code <= 0x0BFF or  # Tamil
            0x0C00 <= code <= 0x0C7F or  # Telugu
            0x0A80 <= code <= 0x0AFF):   # Gujarati
            return False
    return True

def detect_language_from_text(text):
    """Auto-detect language from text by checking Unicode ranges and Hinglish patterns"""
    # First check for native scripts
    for char in text:
        code = ord(char)
        if 0x0900 <= code <= 0x097F:  # Devanagari (Hindi/Marathi)
            return "hi-IN"
        elif 0x0C80 <= code <= 0x0CFF:  # Kannada
            return "kn-IN"
        elif 0x0B80 <= code <= 0x0BFF:  # Tamil
            return "ta-IN"
        elif 0x0C00 <= code <= 0x0C7F:  # Telugu
            return "te-IN"
        elif 0x0A80 <= code <= 0x0AFF:  # Gujarati
            return "gu-IN"
    
    # Check for Hinglish (Roman Hindi) patterns
    hinglish_words = [
        # Common Hindi words in Roman script
        'haan', 'nahi', 'mereko', 'mujhe', 'tujhe', 'inhe', 'unhe',
        'kya', 'kaise', 'kyun', 'kaun', 'kaha', 'kab',
        'acha', 'accha', 'theek', 'sahi', 'galat',
        'hum', 'tum', 'main', 'maine', 'tumare', 'uske',
        'padao', 'bataao', 'dikhaao', 'samjhao', 'sikhao',
        'kar', 'karo', 'kiya', 'hai', 'hain', 'ho', 'tha', 'the',
        'isme', 'usme', 'ismein', 'usmein',
        'aur', 'ya', 'par', 'lekin', 'to', 'toh',
        'bahut', 'bohat', 'achha', 'bilkul', 'theek',
        'dhanyavaad', 'shukriya', 'namaste', 'namaskar'
    ]
    
    text_lower = text.lower()
    words = text_lower.split()
    
    hinglish_count = 0
    for word in words:
        # Remove punctuation and check
        clean_word = ''.join(c for c in word if c.isalnum())
        if clean_word in hinglish_words:
            hinglish_count += 1
    
    # If 30% or more of words are common Hindi words, treat as Hinglish
    if len(words) > 0 and hinglish_count / len(words) >= 0.3:
        return "hi-IN"
    
    return "en-IN"  # Default to English if no other script detected

def detect_emotion(transcript):
    try:
        prompt = f"""Classify the emotion in this message into EXACTLY ONE word from this list:
happy, sad, angry, anxious, neutral, curious, excited

Message: "{transcript}"

Respond with ONLY the single emotion word. No punctuation, no explanation."""
        result = gemini_client.generate_content(prompt)
        emotion = result.text.strip().lower().split()[0]
        if emotion not in EMOTION_SSML:
            emotion = "neutral"
        return emotion
    except Exception as e:
        print(f"Emotion detection error: {e}")
        return "neutral"


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)