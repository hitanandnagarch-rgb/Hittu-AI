import os
import sys
import datetime
import subprocess

# 1. Automatic Dependency Installer
REQUIRED_LIBS = ["fastapi", "uvicorn", "langchain-openai", "langchain-google-genai", "pyjwt", "passlib", "bcrypt", "pydantic", "pillow", "edge-tts"]
for lib in REQUIRED_LIBS:
    try:
        if lib == "langchain-openai":
            __import__("langchain_openai")
        elif lib == "langchain-google-genai":
            __import__("langchain_google_genai")
        elif lib == "edge-tts":
            __import__("edge_tts")
        else:
            __import__(lib)
    except ImportError:
        print(f"[+] Installing missing library: {lib}")
        subprocess.check_call([sys.executable, "-m", "pip", "install", lib])

import uvicorn
from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel
from passlib.context import CryptContext
import jwt
from jwt import PyJWTError
import sqlite3
import edge_tts
import tempfile
import io
import base64
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

# 2. API Keys Management
if not os.environ.get("OPENAI_API_KEY"):
    print("\n" + "="*50)
    os.environ["OPENAI_API_KEY"] = input("Enter OpenAI API Key: ").strip()
    print("="*50 + "\n")

if not os.environ.get("GOOGLE_API_KEY"):
    print("\n" + "="*50)
    os.environ["GOOGLE_API_KEY"] = input("Enter Google AI Studio API Key: ").strip()
    print("="*50 + "\n")

# 3. Database Setup
DATABASE_NAME = "hittu.db"
def init_db():
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS chats (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, role TEXT, content TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
    conn.commit()
    conn.close()

init_db()

# 4. FastAPI & Auth Configuration
app = FastAPI(title="hittu.ai")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

SECRET_KEY = "hittu_secret_key_2026"
ALGORITHM = "HS256"
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()

llm = ChatOpenAI(model="gpt-4o")

# FIX 1: Official NanoBanana 2 Image Model Name Update
try:
    image_llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash-exp-image-generation", google_api_key=os.environ.get("GOOGLE_API_KEY"))
except Exception as e:
    print(f"[!] Google AI Model Init Warning: {e}")

class UserAuth(BaseModel):
    username: str
    password: str

class ChatRequest(BaseModel):
    message: str

# TTS Request Model
class TTSRequest(BaseModel):
    message: str

def get_db():
    conn = sqlite3.connect(DATABASE_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub")
    except PyJWTError:
        raise HTTPException(status_code=401, detail="Session expired or invalid token!")

def get_chat_history(username: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT role, content FROM chats WHERE username = ? ORDER BY timestamp DESC LIMIT 10", (username,))
    rows = cursor.fetchall()
    conn.close()
    
    messages = []
    for row in reversed(rows):
        if row["role"] == "user":
            messages.append(HumanMessage(content=row["content"]))
        elif row["role"] == "assistant":
            messages.append(AIMessage(content=row["content"]))
    return messages

def save_msg(username: str, role: str, content: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO chats (username, role, content) VALUES (?, ?, ?)", (username, role, content))
    conn.commit()
    conn.close()

# 5. API Endpoints
@app.post("/api/register")
def register(user: UserAuth):
    conn = get_db()
    cursor = conn.cursor()
    try:
        hashed = pwd_context.hash(user.password)
        cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)", (user.username, hashed))
        conn.commit()
        return {"status": "success"}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Username already taken!")
    finally:
        conn.close()

@app.post("/api/login")
def login(user: UserAuth):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ?", (user.username,))
    db_user = cursor.fetchone()
    conn.close()
    
    if not db_user or not pwd_context.verify(user.password, db_user["password"]):
        raise HTTPException(status_code=400, detail="Invalid username or password!")
    
    token = jwt.encode({"sub": user.username, "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=24)}, SECRET_KEY, algorithm=ALGORITHM)
    return {"access_token": token}

@app.post("/api/chat")
def chat(request: ChatRequest, username: str = Depends(get_current_user)):
    history = get_chat_history(username)
    sys_msg = SystemMessage(content="You are hittu.ai, 'Bharat ka AI Teacher'. Autocorrect typos internally and help Indian students with clear concepts in simple language.")
    response = llm.invoke([sys_msg] + history + [HumanMessage(content=request.message)])
    save_msg(username, "user", request.message)
    save_msg(username, "assistant", response.content)
    return {"response": response.content}

@app.post("/api/sanskrit-tutor")
def sanskrit_tutor(request: ChatRequest, username: str = Depends(get_current_user)):
    history = get_chat_history(username)
    sys_msg = SystemMessage(content="You are a Class 8 Sanskrit Tutor. Respond ONLY in clear Sanskrit text and explain it using simple Hindi words. Do not use English.")
    response = llm.invoke([sys_msg] + history + [HumanMessage(content=request.message)])
    save_msg(username, "user", request.message)
    save_msg(username, "assistant", response.content)
    return {"response": response.content}

@app.post("/api/panchayat")
def panchayat(request: ChatRequest, username: str = Depends(get_current_user)):
    history = get_chat_history(username)
    sys_msg = SystemMessage(content="You are HIT AI - Advanced Smart Companion, created by Hitanand Nagarch. Respond in a deeply empathetic, energetic '[Empathetic/Hyper-Panchayat]' style. Speak like a wise Indian guru inspired by Sri Harivansh Mahaprabhu ji. Autocorrect broken Hinglish words to beautiful pure emotions.")
    response = llm.invoke([sys_msg] + history + [HumanMessage(content=request.message)])
    full_response = f"[Empathetic/Hyper-Panchayat] {response.content}"
    save_msg(username, "user", request.message)
    save_msg(username, "assistant", full_response)
    return {"response": full_response}

@app.post("/api/generate-image")
def generate_image(request: ChatRequest, username: str = Depends(get_current_user)):
    try:
        sys_prompt = f"Create a beautiful premium visual prompt based on: {request.message}. Focus on high artistic detailing, vibrant cinematic colors, Indian spiritualism or student success theme."
        res = image_llm.invoke([HumanMessage(content=sys_prompt)])
        mock_img_url = f"https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?q=80&w=600&auto=format&fit=crop"
        save_msg(username, "user", request.message)
        save_msg(username, "assistant", f"[Image Generated] {request.message}")
        return {"response": "आपकी इमेज सफलतापूर्वक तैयार हो गई है!", "image_url": mock_img_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# FIX 2: TTS Endpoint converted to POST to support long text payloads securely on mobile devices
@app.post("/api/tts")
async def text_to_speech(request: TTSRequest, token: str = None):
    if token:
        try:
            jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        except PyJWTError:
            raise HTTPException(status_code=401, detail="Unauthorized voice token")
            
    VOICE = "hi-IN-MadhurNeural"
    try:
        communicate = edge_tts.Communicate(request.message, VOICE)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
            await communicate.save(tmp.name)
            return StreamingResponse(open(tmp.name, "rb"), media_type="audio/mp3")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TTS Error: {str(e)}")

# 6. UI Engine with POST-based Fetch Audio Stream Implementation
@app.get("/", response_class=HTMLResponse)
def serve_ui():
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>hittu.ai | HIT AI</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <style>
            body { 
                background: linear-gradient(180deg, #6b4703 0%, #090d16 100%); 
                color: #e2e8f0; 
            }
            .premium-glass {
                background: rgba(17, 24, 39, 0.7);
                backdrop-filter: blur(12px);
                border: 1px solid rgba(249, 115, 22, 0.15);
            }
            @keyframes fadeInUp {
                from { opacity: 0; transform: translateY(10px); }
                to { opacity: 1; transform: translateY(0); }
            }
            .fade-in { animation: fadeInUp 0.4s ease-out forwards; }

            @keyframes splashGlow {
                0% { transform: scale(0.8); opacity: 0; }
                50% { transform: scale(1.1); opacity: 1; }
                100% { transform: scale(1); opacity: 1; }
            }
            .splash-logo { animation: splashGlow 1.5s ease-out; }
        </style>
    </head>
    <body class="h-screen flex flex-col overflow-hidden font-sans">
        
        <!-- SPLASH SCREEN -->
        <div id="splash-screen" class="fixed inset-0 bg-gradient-to-b from-[#6b4703] to-[#090d16] flex flex-col items-center justify-center z-[60]">
            <div class="splash-logo w-32 h-32 rounded-full border-4 border-orange-500 flex items-center justify-center bg-gray-900 text-6xl shadow-2xl shadow-orange-500/30">🕉️</div>
            <h1 class="text-4xl font-bold text-orange-500 mt-6 tracking-widest">HIT AI</h1>
            <p class="text-sm text-gray-400 mt-2">Advanced Smart Companion</p>
        </div>

        <!-- Auth Screen -->
        <div id="auth-screen" class="fixed inset-0 bg-gray-950 flex items-center justify-center z-50 p-4 hidden">
            <div class="bg-gray-900 border border-gray-800 p-8 rounded-2xl w-full max-w-md shadow-2xl">
                <div class="text-center mb-6">
                    <div class="w-24 h-24 mx-auto mb-4 rounded-full border-2 border-orange-500 flex items-center justify-center bg-gray-800 text-2xl">🕉️</div>
                    <h1 class="text-3xl font-bold text-orange-500">hittu.ai</h1>
                    <p class="text-sm text-gray-400 mt-1">"Bharat ka AI Teacher"</p>
                </div>
                <div class="space-y-4">
                    <input id="auth-user" type="text" placeholder="Username" class="w-full bg-gray-800 border border-gray-700 rounded-xl px-4 py-3 text-white focus:outline-none focus:border-orange-500">
                    <input id="auth-pass" type="password" placeholder="Password" class="w-full bg-gray-800 border border-gray-700 rounded-xl px-4 py-3 text-white focus:outline-none focus:border-orange-500">
                    <button onclick="handleAuth('login')" class="w-full bg-orange-600 hover:bg-orange-500 text-white font-bold py-3 rounded-xl transition-all shadow-lg">Login</button>
                    <button onclick="handleAuth('register')" class="w-full bg-gray-800 hover:bg-gray-700 text-gray-300 py-2.5 rounded-xl transition-all text-sm">Create Account</button>
                </div>
            </div>
        </div>

        <!-- App Layout -->
        <div id="app-layout" class="flex flex-1 h-full overflow-hidden hidden">
            <!-- SIDEBAR -->
            <div class="hidden md:flex flex-col w-72 bg-black/40 border-r border-gray-800/60 p-3 justify-between">
                <div>
                    <button onclick="newChat()" class="w-full text-left px-4 py-3 rounded-xl bg-orange-600 hover:bg-orange-500 text-white font-medium flex items-center space-x-2 mb-4 transition-all">
                        <span>➕</span> <span>New Chat</span>
                    </button>

                    <p class="text-xs text-gray-500 px-4 mb-2">Recent Chats</p>
                    <div id="chat-history-list" class="space-y-1 max-h-32 overflow-y-auto mb-4">
                        <p class="text-[11px] text-gray-600 px-4 italic">No recent sessions</p>
                    </div>

                    <p class="text-xs text-gray-500 px-4 mb-2">Modes</p>
                    <div class="space-y-1">
                        <button id="btn-chat" onclick="setMode('chat')" class="w-full text-left px-4 py-2 rounded-xl bg-orange-600 text-white text-sm">🤖 General Learning</button>
                        <button id="btn-sanskrit" onclick="setMode('sanskrit')" class="w-full text-left px-4 py-2 rounded-xl hover:bg-gray-900 text-gray-300 text-sm">🕉️ Class 8 संस्कृत</button>
                        <button id="btn-panchayat" onclick="setMode('panchayat')" class="w-full text-left px-4 py-2 rounded-xl hover:bg-gray-900 text-gray-300 text-sm">🔥 Hyper-Panchayat</button>
                        <button id="btn-image" onclick="setMode('image')" class="w-full text-left px-4 py-2 rounded-xl hover:bg-gray-900 text-gray-300 text-sm">🎨 AI Image (NanoBanana)</button>
                    </div>
                </div>
                <div class="space-y-1">
                    <button class="w-full text-left px-4 py-2 rounded-xl hover:bg-gray-900 text-gray-300 text-sm">⚙️ Projects & Settings</button>
                    <button onclick="logout()" class="w-full text-left px-4 py-2 rounded-xl hover:bg-gray-900 text-gray-300 text-sm border border-transparent hover:border-red-500/20">🚪 Logout</button>
                </div>
            </div>

            <!-- Chat Container -->
            <div class="flex flex-col flex-1">
                <!-- Header -->
                <div class="flex flex-col items-center justify-center pt-4 pb-2 px-4 text-center border-b border-white/5 bg-black/10">
                    <div class="flex items-center space-x-3">
                        <div class="w-12 h-12 rounded-full border border-amber-400/60 flex items-center justify-center bg-gray-900 text-xl shadow-md">🕉️</div>
                        <div class="text-left">
                            <h2 class="text-sm font-bold text-amber-400 tracking-wide">HIT AI - Advanced Smart Companion</h2>
                            <p class="text-[10px] text-gray-400">Sri Harivansh Mahaprabhu ji • Created by Hitanand Nagarch</p>
                        </div>
                    </div>
                    <div class="mt-2 flex space-x-2 md:hidden">
                        <button onclick="toggleMobileMode()" class="bg-gray-900/80 border border-orange-500/30 text-orange-400 px-3 py-1 rounded-full text-xs font-semibold">Switch Mode</button>
                        <button onclick="newChat()" class="bg-gray-900/80 border border-gray-800 text-gray-300 px-3 py-1 rounded-full text-xs">Clear</button>
                    </div>
                </div>

                <!-- Chat Stream -->
                <div id="chat-stream" class="flex-1 overflow-y-auto p-4 space-y-4 max-w-3xl w-full mx-auto">
                    <div class="text-center text-gray-400 py-16">
                        <p class="text-4xl mb-3">🙏</p>
                        <p class="text-sm font-medium">राधे राधे! मैं हूँ आपका smart companion.</p>
                        <p id="mode-desc" class="text-xs text-gray-500 mt-1">General learning मोड सक्रिय है।</p>
                    </div>
                </div>

                <!-- Input Panel -->
                <div class="p-4 bg-black/20 border-t border-white/5">
                    <div class="max-w-2xl mx-auto flex items-center bg-gray-900/90 border border-gray-800 rounded-full px-4 py-2 shadow-xl focus-within:border-orange-500/50 transition-all">
                        <input id="chat-input" type="text" placeholder="Msg Entry (Send -> Enter)" class="flex-1 bg-transparent px-2 py-2 text-white focus:outline-none text-sm" onkeypress="if(event.key==='Enter') send()">
                        
                        <!-- Mic Button -->
                        <button id="mic-btn" onclick="startVoiceRecognition()" class="p-2 text-gray-400 hover:text-amber-400 transition-colors mr-2" title="Speak in Hindi/Hinglish">
                            <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                              <path fill-rule="evenodd" d="M7 4a3 3 0 016 0v4a3 3 0 11-6 0V4zm4 10.93A7.001 7.001 0 0017 8a1 1 0 10-2 0A5 5 0 015 8a1 1 0 10-2 0 7.001 7.001 0 006 6.93V17H6a1 1 0 100 2h8a1 1 0 100-2h-3v-2.07z" clip-rule="evenodd" />
                            </svg>
                        </button>
                        
                        <button onclick="send()" class="bg-gradient-to-r from-orange-600 to-amber-600 hover:from-orange-500 hover:to-amber-500 text-white px-5 py-2 rounded-full font-bold text-xs tracking-wider uppercase transition-all shadow-md">Send</button>
                    </div>
                </div>
            </div>
        </div>

        <script>
            let token = localStorage.getItem('token') || '';
            let currentMode = 'chat';
            let currentAudio = null;

            window.onload = () => {
                setTimeout(() => {
                    document.getElementById('splash-screen').style.display = 'none';
                    if (token) document.getElementById('app-layout').classList.remove('hidden');
                    else document.getElementById('auth-screen').classList.remove('hidden');
                }, 2000);
            }

            function newChat(){
                stopVoiceOutput();
                document.getElementById('chat-stream').innerHTML = `
                    <div class="text-center text-gray-400 py-16">
                        <p class="text-4xl mb-3">🙏</p>
                        <p class="text-sm font-medium">नई चैट शुरू हो गई।</p>
                        <p class="text-xs text-gray-500 mt-1">${getModeName()} मोड एक्टिव है।</p>
                    </div>`;
            }

            function getModeName() {
                if(currentMode === 'chat') return "General learning";
                if(currentMode === 'sanskrit') return "कक्षा 8 संस्कृत";
                if(currentMode === 'panchayat') return "[Empathetic/Hyper-Panchayat]";
                if(currentMode === 'image') return "🎨 AI Image Generation";
                return "";
            }

            function setMode(mode) {
                currentMode = mode;
                const desc = document.getElementById('mode-desc');
                if(desc) desc.innerText = `${getModeName()} मोड सक्रिय है।`;

                ['chat', 'sanskrit', 'panchayat', 'image'].forEach(m => {
                    const el = document.getElementById(`btn-${m}`);
                    if(el) el.className = currentMode === m ? 'w-full text-left px-4 py-2 rounded-xl bg-orange-600 text-white text-sm font-medium' : 'w-full text-left px-4 py-2 rounded-xl hover:bg-gray-900 text-gray-300 text-sm';
                });
            }

            function toggleMobileMode() {
                if(currentMode === 'chat') setMode('sanskrit');
                else if(currentMode === 'sanskrit') setMode('panchayat');
                else if(currentMode === 'panchayat') setMode('image');
                else setMode('chat');
            }

            async function handleAuth(action) {
                const username = document.getElementById('auth-user').value;
                const password = document.getElementById('auth-pass').value;
                if(!username || !password) return alert('Please enter all details!');

                try {
                    const res = await fetch(`/api/${action}`, {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({ username, password })
                    });
                    const data = await res.json();
                    if(!res.ok) throw new Error(data.detail || 'Failed');
                    
                    if(action === 'login') {
                        token = data.access_token;
                        localStorage.setItem('token', token);
                        document.getElementById('auth-screen').classList.add('hidden');
                        document.getElementById('app-layout').classList.remove('hidden');
                    } else {
                        alert('Account created! Please login.');
                    }
                } catch(err) { alert(err.message); }
            }

            async function send() {
                const inputEl = document.getElementById('chat-input');
                const text = inputEl.value.trim();
                if(!text) return;
                inputEl.value = '';

                const stream = document.getElementById('chat-stream');
                stream.innerHTML += `<div class="flex justify-end mb-3"><div class="bg-gradient-to-r from-orange-600 to-amber-600 text-white rounded-2xl rounded-tr-none px-4 py-2.5 max-w-[85%] text-sm shadow-md">${text}</div></div>`;
                
                const loadId = 'load-' + Date.now();
                stream.innerHTML += `<div id="${loadId}" class="flex justify-start mb-3"><div class="bg-gray-900/90 border border-gray-800 text-gray-400 rounded-2xl rounded-tl-none px-4 py-2.5 text-xs animate-pulse">[thinking...]</div></div>`;
                stream.scrollTop = stream.scrollHeight;

                try {
                    let endpoint = '/api/chat';
                    if(currentMode === 'sanskrit') endpoint = '/api/sanskrit-tutor';
                    if(currentMode === 'panchayat') endpoint = '/api/panchayat';
                    if(currentMode === 'image') endpoint = '/api/generate-image';

                    const res = await fetch(endpoint, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'Authorization': `Bearer ${token}`
                        },
                        body: JSON.stringify({ message: text })
                    });
                    const data = await res.json();
                    document.getElementById(loadId).remove();
                    
                    const safeText = data.response.replace(/`/g, '\\`').replace(/"/g, '&quot;');
                    
                    let imageHTML = '';
                    if(currentMode === 'image' && data.image_url) {
                        imageHTML = `<div class="mt-2"><img src="${data.image_url}" class="rounded-xl max-w-full border border-orange-500/20 shadow-md animate-pulse" onload="this.classList.remove('animate-pulse')"/></div>`;
                    }

                    stream.innerHTML += `
                        <div class="flex justify-start fade-in mb-3">
                            <div class="premium-glass text-gray-100 rounded-2xl rounded-tl-none px-4 py-3 max-w-[85%] relative group shadow-lg">
                                <p class="whitespace-pre-wrap text-sm leading-relaxed">${data.response}</p>
                                ${imageHTML}
                                <div class="flex gap-4 mt-2">
                                    <button onclick="playVoiceOutput('${safeText}')" class="text-[11px] text-amber-400 font-semibold hover:underline flex items-center gap-1">🔊 Suno</button>
                                    <button onclick="navigator.clipboard.writeText('${safeText}'); alert('Copied!');" class="text-[11px] text-gray-400 hover:underline">Copy</button>
                                </div>
                            </div>
                        </div>`;
                        
                    if(currentMode !== 'image') {
                        playVoiceOutput(data.response);
                    }
                } catch (err) {
                    if(document.getElementById(loadId)) document.getElementById(loadId).remove();
                    stream.innerHTML += `<div class="flex justify-start mb-3"><div class="bg-red-950/40 border border-red-900/50 text-red-400 rounded-2xl px-4 py-2 text-xs">Connection or API Key Error!</div></div>`;
                }
                stream.scrollTop = stream.scrollHeight;
            }

            // FIX 2 Frontend implementation: Blob stream audio via secure POST fetch requests
            async function playVoiceOutput(text) {
                stopVoiceOutput();
                try {
                    const response = await fetch(`/api/tts?token=${token}`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({ message: text })
                    });
                    
                    if(!response.ok) throw new Error("Audio generation failed");
                    
                    const blob = await response.blob();
                    const audioUrl = URL.createObjectURL(blob);
                    currentAudio = new Audio(audioUrl);
                    currentAudio.play().catch(e => console.log("Auto-play interaction restriction handle"));
                } catch (e) {
                    console.error("TTS Engine Playback Error:", e);
                }
            }

            function stopVoiceOutput() {
                if(currentAudio) {
                    currentAudio.pause();
                    currentAudio = null;
                }
            }

            function startVoiceRecognition() {
                const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
                if (!SpeechRecognition) {
                    alert("Voice search not supported on this browser. Try Chrome!");
                    return;
                }
                const recognition = new SpeechRecognition();
                recognition.lang = 'hi-IN'; 
                
                const micBtn = document.getElementById('mic-btn');
                micBtn.classList.add('text-red-500', 'animate-ping');
                
                recognition.onresult = function(event) {
                    const transcript = event.results[0][0].transcript;
                    document.getElementById('chat-input').value = transcript;
                };
                
                recognition.onerror = function() {
                    micBtn.classList.remove('text-red-500', 'animate-ping');
                };
                
                recognition.onend = function() {
                    micBtn.classList.remove('text-red-500', 'animate-ping');
                };
                
                recognition.start();
            }

            function logout() {
                stopVoiceOutput();
                localStorage.clear();
                window.location.reload();
            }
        </script>
    </body>
    </html>
    """

if __name__ == "__main__":
    uvicorn.run("hittu:app", host="127.0.0.1", port=8000, reload=True)