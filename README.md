# VaaniAI 🎤

A real-time AI-powered voice assistant application with multi-language support, persistent conversation history, and emotion detection.

## 🌟 Features

- **Real-time Voice Processing**: Stream audio input and get instant AI responses
- **Multi-language Support**: English, Hindi, and Hinglish language detection
- **Conversation History**: Persistent SQLite database for storing and retrieving conversations
- **Emotion Detection**: Identifies 7 emotions (happy, sad, angry, anxious, neutral, curious, excited)
- **AI Integration**: Powered by Google Gemini 2.5 Flash for intelligent responses
- **Text-to-Speech**: AWS Polly integration for natural audio output
- **WebSocket Pipeline**: Real-time event-driven processing (STT → NLP → LLM → TTS)
- **Responsive UI**: Clean frontend with conversation sidebar and chat interface

## 🏗️ Architecture

### Backend
- **Framework**: FastAPI with async WebSocket support
- **Database**: SQLite (persistent storage for conversations and messages)
- **AI Services**:
  - **STT**: Sarvam AI (Multilingual speech-to-text)
  - **LLM**: Google Generative AI (Gemini 2.5 Flash)
  - **TTS**: AWS Polly (Natural voice synthesis)

### Frontend
- **Vanilla JavaScript** (no frameworks)
- **Web Audio API** for audio recording
- **WebSocket** for real-time communication
- **Responsive Design** with conversation history sidebar

## 📋 Prerequisites

- Python 3.8+
- Node.js (optional, for frontend development)
- API Keys:
  - Sarvam AI API Key
  - Google Generative AI API Key (Gemini)
  - AWS Credentials (for Polly)
  - (Optional) Google OAuth credentials for drive operations

## 🚀 Installation

### 1. Clone the Repository
```bash
git clone <repository-url>
cd VaaniAI
```

### 2. Create Virtual Environment
```bash
python -m venv .venv
# On Windows
.venv\Scripts\activate
# On macOS/Linux
source .venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Set Environment Variables
Create a `.env` file in the project root:
```
SARVAM_API_KEY=your_sarvam_api_key
GEMINI_API_KEY=your_gemini_api_key
AWS_ACCESS_KEY_ID=your_aws_access_key
AWS_SECRET_ACCESS_KEY=your_aws_secret_key
```

### 5. Configure AWS Credentials (Optional)
If using drive operations, ensure Google OAuth credentials are set up:
```bash
# Credentials will be automatically stored in token.json
```

## 💻 Running the Application

### Start the Server
```bash
python app.py
```

The server will:
- Initialize the SQLite database (auto-creates `chats.db` with required schema)
- Start on `http://localhost:8000`
- Serve the frontend at `http://localhost:8000`
- WebSocket endpoint: `ws://localhost:8000/ws/chat`

### Access the Application
Open your browser and navigate to:
```
http://localhost:8000
```

## 🔌 API Endpoints

### WebSocket
- **`ws://localhost:8000/ws/chat`** - Real-time audio/text chat pipeline

### REST API

#### Health Check
```
GET /health
```

#### Conversations Management
```
GET /api/conversations              # List all conversations
POST /api/conversations             # Create new conversation
GET /api/conversations/{id}         # Get conversation details
PUT /api/conversations/{id}         # Update conversation
DELETE /api/conversations/{id}      # Delete conversation
GET /api/conversations/search       # Search conversations (query parameter)
```

## 📦 Project Structure

```
VaaniAI/
├── app.py                  # FastAPI server & WebSocket handler
├── commands.py             # Command routing & processing logic
├── index.html             # Main chat interface
├── landing.html           # Landing/intro page
├── style.css              # Frontend styling
├── scripts.js             # Frontend logic & WebSocket handling
├── requirements.txt       # Python dependencies
├── .env                   # Environment variables (create this)
├── chats.db               # SQLite database (auto-created)
├── token.json             # Google OAuth token (auto-created)
└── README.md              # This file
```

## 🗄️ Database Schema

### conversations table
```sql
CREATE TABLE conversations (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    language TEXT DEFAULT 'unknown',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
```

### messages table
```sql
CREATE TABLE messages (
    id TEXT PRIMARY KEY,
    conv_id TEXT,
    role TEXT,  -- 'user' or 'assistant'
    content TEXT,
    language TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (conv_id) REFERENCES conversations(id)
)
```

## 🎯 Key Processing Functions

### `sarvam_transcribe()`
Converts audio to text using Sarvam AI with language detection

### `gemini_process()`
Processes user input through Google Gemini LLM with conversation history context

### `polly_synthesize()`
Converts text responses to natural speech using AWS Polly (Aditi voice)

### Language Detection
- Uses Unicode ranges for Devanagari, Latin script detection
- Hinglish pattern matching for mixed language input

## ⚙️ Configuration

### Supported Languages
- English (en)
- Hindi (hi)
- Hinglish (mixed English-Hindi)

### Emotions Detected
- Happy, Sad, Angry, Anxious, Neutral, Curious, Excited

### Voice Settings
- **TTS Voice**: Aditi (Polly)
- **LLM Model**: Gemini 2.5 Flash
- **STT Model**: Sarvam Saaras:v3

## 📝 Usage Example

### Via Web Interface
1. Open `http://localhost:8000`
2. Click the microphone button to start recording
3. Speak in English, Hindi, or Hinglish
4. Receive AI response with text and audio playback
5. Conversations auto-save to history sidebar

### Via WebSocket (Manual)
```javascript
const ws = new WebSocket('ws://localhost:8000/ws/chat');
ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    console.log('Pipeline Status:', data.status);
};
```

## 🔒 Security Notes

- ⚠️ **No Authentication**: Currently no user auth system implemented
- ⚠️ **No User Isolation**: All users share the same database
- ⚠️ **Single-threaded**: Suitable for small teams, not production-scale
- Store API keys securely in `.env` file (never commit to version control)

## 🐛 Known Limitations

1. Single-threaded/non-scalable for concurrent users
2. No user authentication or profiles
3. No multi-user isolation
4. Limited to Polly's available voices and languages

## 🚢 Deployment

For production deployment:
1. Add user authentication system
2. Implement database connection pooling
3. Use async workers (Gunicorn with Uvicorn workers)
4. Add HTTPS/SSL certificates
5. Implement rate limiting and request validation
6. Add monitoring and logging

## 📖 Dependencies

| Package | Purpose |
|---------|---------|
| `fastapi` | Web framework |
| `uvicorn` | ASGI server |
| `google-generativeai` | Gemini LLM |
| `boto3` | AWS Polly TTS |
| `sarvamai` | Sarvam AI STT |
| `pydub` | Audio processing |
| `scipy`, `numpy` | Audio analysis |
| `python-dotenv` | Environment management |

## 🤝 Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Open a Pull Request

## 💬 Support

For issues and questions:
1. Check existing GitHub issues
2. Create a new issue with detailed description
3. Include error logs and reproduction steps

## 🎉 Acknowledgments

- Sarvam AI for speech recognition
- Google for Generative AI / Gemini API
- AWS for Polly text-to-speech
- FastAPI community for excellent framework

---

**Last Updated**: April 2, 2026  
**Status**: Active Development
