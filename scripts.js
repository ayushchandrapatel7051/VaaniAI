const WS_URL = `ws://${window.location.hostname}:8000/ws/chat`;
let ws = null;
let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;
let currentLanguage = "unknown";
let audioContext = null;
let mediaStream = null;
let currentAudio = null;
let currentAudioId = null;
let currentAudioUrl = null;
let wsConnected = false;
let lastTranscript = null;
let conversationId = null;
let allConversations = [];
let filteredConversations = [];
let sidebarOpen = false;

// Silence Detection
let analyser = null;
let silenceTimer = null;
let lastSoundTime = Date.now();
const SILENCE_THRESHOLD = 30;
const SILENCE_DURATION = 5000; // 5 seconds

document.addEventListener('DOMContentLoaded', () => {
    // Initialize sidebar and mobile menu FIRST
    setupSidebar();
    setupMobileMenu();
    
    // Request notification permission for reminders
    if ('Notification' in window && Notification.permission === 'default') {
        Notification.requestPermission();
    }
    
    // Load conversations from API
    loadConversations();
    
    // Initialize chat functionality
    initWebSocket();
    setupLanguageButtons();
    setupMicButton();
    setupTextInput();
    initAudioContext();
    resetPipelineIndicator();
});

// === SIDEBAR FUNCTIONALITY ===

function setupSidebar() {
    // New Chat Button
    document.getElementById('newChatBtn').addEventListener('click', createNewConversation);
    
    // Search Input
    const searchInput = document.getElementById('searchInput');
    searchInput.addEventListener('input', debounce(handleSearch, 300));
    
    // Conversation item click delegation will be handled in renderConversationsList
}

function setupMobileMenu() {
    const hamburgerBtn = document.getElementById('hamburgerBtn');
    const sidebar = document.getElementById('sidebar');
    const closeSidebarBtn = document.getElementById('closeSidebarBtn');
    
    hamburgerBtn.addEventListener('click', () => {
        sidebar.classList.toggle('open');
        sidebarOpen = !sidebarOpen;
    });
    
    closeSidebarBtn.addEventListener('click', () => {
        sidebar.classList.remove('open');
        sidebarOpen = false;
    });
    
    // Close sidebar when clicking outside
    document.addEventListener('click', (e) => {
        if (sidebarOpen && !sidebar.contains(e.target) && !hamburgerBtn.contains(e.target)) {
            sidebar.classList.remove('open');
            sidebarOpen = false;
        }
    });
}

function debounce(func, delay) {
    let timeoutId;
    return function (...args) {
        clearTimeout(timeoutId);
        timeoutId = setTimeout(() => func.apply(this, args), delay);
    };
}

async function loadConversations() {
    try {
        const response = await fetch('/api/conversations?limit=50');
        
        if (!response.ok) {
            console.error('❌ API returned status:', response.status, response.statusText);
            allConversations = [];
            filteredConversations = [];
            renderConversationsList([]);
            return;
        }
        
        const data = await response.json();
        allConversations = data.conversations || [];
        filteredConversations = allConversations;
        renderConversationsList(filteredConversations);
        console.log('✅ Loaded', allConversations.length, 'conversations');
    } catch (error) {
        console.error('❌ Error loading conversations:', error);
        allConversations = [];
        filteredConversations = [];
        renderConversationsList([]);
    }
}

function renderConversationsList(conversations) {
    const listContainer = document.getElementById('conversationsList');
    
    if (!conversations || conversations.length === 0) {
        listContainer.innerHTML = `
            <div class="empty-state">
                <i class="fas fa-inbox"></i>
                <p>No conversations yet</p>
            </div>
        `;
        return;
    }
    
    listContainer.innerHTML = '';
    conversations.forEach(conv => {
        const item = document.createElement('button');
        item.className = `conversation-item ${conv.id === conversationId ? 'active' : ''}`;
        
        const timestamp = new Date(conv.updated_at).toLocaleDateString('en-US', {
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        });
        
        item.innerHTML = `
            <div class="conversation-title">${conv.title}</div>
            <div class="conversation-time">${timestamp}</div>
        `;
        
        item.addEventListener('click', () => selectConversation(conv.id));
        
        // Delete button (show on hover)
        const wrapper = document.createElement('div');
        wrapper.style.position = 'relative';
        wrapper.style.width = '100%';
        wrapper.appendChild(item);
        
        const deleteBtn = document.createElement('button');
        deleteBtn.className = 'conversation-delete';
        deleteBtn.innerHTML = '<i class="fas fa-trash" style="font-size: 12px; margin-left: auto;"></i>';
        deleteBtn.style.position = 'absolute';
        deleteBtn.style.right = '8px';
        deleteBtn.style.top = '50%';
        deleteBtn.style.transform = 'translateY(-50%)';
        deleteBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            confirmDeleteConversation(conv.id, conv.title);
        });
        
        item.appendChild(deleteBtn);
        listContainer.appendChild(wrapper);
    });
}

async function selectConversation(convId) {
    try {
        // Close sidebar on mobile
        const sidebar = document.getElementById('sidebar');
        sidebar.classList.remove('open');
        sidebarOpen = false;
        
        // Load conversation data
        const response = await fetch(`/api/conversations/${convId}`);
        const data = await response.json();
        
        // Set current conversation
        conversationId = convId;
        
        // Clear messages and load conversation history
        const messagesDiv = document.getElementById('messages');
        messagesDiv.innerHTML = '';
        
        // Display all messages from the conversation
        data.messages.forEach(msg => {
            if (msg.role !== 'system') {
                addMessage(msg.role, msg.content);
            }
        });
        
        // Update sidebar active state
        renderConversationsList(filteredConversations);
        
        console.log('✅ Loaded conversation:', convId);
    } catch (error) {
        console.error('❌ Error loading conversation:', error);
        addSystemMessage('Failed to load conversation');
    }
}

async function createNewConversation() {
    try {
        // Close sidebar on mobile
        const sidebar = document.getElementById('sidebar');
        sidebar.classList.remove('open');
        sidebarOpen = false;
        
        // Clear current chat
        const messagesDiv = document.getElementById('messages');
        messagesDiv.innerHTML = '';
        lastTranscript = null;
        
        // A new conversation will be created by the backend on first message
        conversationId = null;
        
        // Reload conversations list
        await loadConversations();
        
        resetPipelineIndicator();
        console.log('✅ New conversation started');
    } catch (error) {
        console.error('❌ Error creating conversation:', error);
        addSystemMessage('Failed to create new conversation');
    }
}

function handleSearch(e) {
    const query = e.target.value.trim().toLowerCase();
    
    if (!query) {
        filteredConversations = allConversations;
    } else {
        filteredConversations = allConversations.filter(conv =>
            conv.title.toLowerCase().includes(query)
        );
    }
    
    renderConversationsList(filteredConversations);
}

async function confirmDeleteConversation(convId, title) {
    if (confirm(`Delete "${title}"?`)) {
        await deleteConversation(convId);
    }
}

async function deleteConversation(convId) {
    try {
        const response = await fetch(`/api/conversations/${convId}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            // Remove from local list
            allConversations = allConversations.filter(c => c.id !== convId);
            filteredConversations = filteredConversations.filter(c => c.id !== convId);
            
            // If deleted conversation was current, start new one
            if (conversationId === convId) {
                await createNewConversation();
            } else {
                renderConversationsList(filteredConversations);
            }
            
            console.log('✅ Conversation deleted:', convId);
        }
    } catch (error) {
        console.error('❌ Error deleting conversation:', error);
        addSystemMessage('Failed to delete conversation');
    }
}

function addSystemMessage(text) {
    console.log('ℹ️ System:', text);
    // Optionally add system messages to the chat
    // addMessage('system', text);
}

// ===== VOICE COMMAND HELPER =====
function prefillInput(template) {
    const input = document.getElementById('textInput');
    input.value = template;
    input.focus();
    // Move cursor to end of text
    input.setSelectionRange(input.value.length, input.value.length);
}

// === WebSocket ===
function initWebSocket() {
    ws = new WebSocket(WS_URL);
    
    ws.onopen = () => {
        console.log("✅ WebSocket connected");
        wsConnected = true;
        // Remove connection message to keep UI clean
    };

    ws.onmessage = (event) => {
        try {
            console.log("📥 WebSocket message received, size:", event.data?.length);
            const message = JSON.parse(event.data);
            handleMessage(message);
        } catch (e) {
            console.error("❌ Error parsing WebSocket message:", e);
        }
    };

    ws.onerror = (error) => {
        console.error("WebSocket error:", error);
        wsConnected = false;
        addMessage("system", "❌ Connection error");
    };

    ws.onclose = () => {
        console.log("WebSocket closed");
        wsConnected = false;
        addMessage("system", "⚠️ Connection closed. Reconnecting...");
        setTimeout(initWebSocket, 3000);
    };
}

function handleMessage(message) {
    const { type, text, message: statusMsg, data, format, audioId, stage, status, conversation_id, command } = message;
    
    console.log("📨 Message received:", type, message);

    switch(type) {
        case "conversation_id":
            console.log("🆔 Conversation ID received:", conversation_id);
            if (!conversationId) {
                conversationId = conversation_id;
                // Reload conversations to show the new one
                loadConversations();
            }
            break;
        case "command_response":
            console.log("⚡ Command response:", command.type);
            handleCommandResponse(command);
            break;
        case "pipeline":
            console.log("🔄 Pipeline update:", stage, status);
            updatePipelineIndicator(stage, status, statusMsg);
            break;
        case "status":
            console.log("📍 Status:", statusMsg);
            updateMicLabel(statusMsg);
            break;
        case "transcript":
            console.log("📝 Transcript:", text);
            if (text !== lastTranscript) {
                addMessage("user", text);
                lastTranscript = text;
            } else {
                console.log("⏭️  Skipping duplicate transcript");
            }
            break;
        case "response":
            console.log("💬 Response:", text);
            addMessage("assistant", text);
            break;
        case "audio":
            console.log("🎵 Audio message received:", { audioId, format, dataSize: data?.length });
            playAudio(data, format, audioId);
            break;
        case "error":
            console.log("❌ Error:", text || statusMsg);
            addMessage("system", text || statusMsg);
            break;
        default:
            console.warn("⚠️ Unknown message type:", type);
    }
}

// ===== COMMAND RESPONSE HANDLERS =====
function handleCommandResponse(command) {
    const cmdType = command.type;
    console.log(`Processing command: ${cmdType}`);
    
    switch(cmdType) {
        case "youtube":
            addMessage("command", renderYouTubeCard(command));
            break;
        case "google_search":
            addMessage("command", renderGoogleSearchCard(command));
            break;
        case "timer":
            addMessage("command", renderTimerCard(command));
            break;
        case "stopwatch":
            addMessage("command", renderStopwatchCard(command));
            break;
        case "weather":
            addMessage("command", renderWeatherCard(command));
            break;
        case "save_note":
            addMessage("command", renderSaveNoteCard(command));
            break;
        case "view_notes":
            addMessage("command", renderNotesCard(command));
            break;
        case "set_reminder":
            addMessage("command", renderReminderCard(command));
            scheduleReminderNotification(command);
            break;
        case "view_reminders":
            addMessage("command", renderRemindersCard(command));
            break;
        case "export":
            addMessage("command", renderExportCard(command));
            break;
        case "toggle_favorite":
            addMessage("command", renderFavoriteCard(command));
            loadConversations(); // Refresh sidebar
            break;
        case "calendar_event":
            addMessage("command", renderCalendarCard(command));
            break;
        default:
            addMessage("command", `<div class="command-card">${command.text}</div>`);
    }
}

// YouTube Card Renderer
function renderYouTubeCard(cmd) {
    return `
        <div class="command-card youtube-card">
            <div class="card-header">
                <i class="fas fa-youtube"></i>
                <span>${cmd.title}</span>
            </div>
            <div class="card-body">
                <p>${cmd.text}</p>
                <a href="${cmd.url}" target="_blank" rel="noopener noreferrer" class="card-button">
                    <i class="fas fa-external-link-alt"></i> Open YouTube
                </a>
            </div>
        </div>
    `;
}

// Google Search Card Renderer
function renderGoogleSearchCard(cmd) {
    return `
        <div class="command-card google-card">
            <div class="card-header">
                <i class="fas fa-search"></i>
                <span>${cmd.title}</span>
            </div>
            <div class="card-body">
                <p>${cmd.text}</p>
                <a href="${cmd.url}" target="_blank" rel="noopener noreferrer" class="card-button">
                    <i class="fas fa-external-link-alt"></i> Search Google
                </a>
            </div>
        </div>
    `;
}

// Timer Card Renderer
function renderTimerCard(cmd) {
    const timerId = `timer-${Date.now()}`;
    setTimeout(() => startTimer(timerId, cmd.seconds), 100);
    return `
        <div class="command-card timer-card" id="${timerId}">
            <div class="card-header">
                <i class="fas fa-hourglass-start"></i>
                <span>${cmd.title}</span>
            </div>
            <div class="card-body">
                <div class="timer-display" id="${timerId}-display">
                    ${cmd.display}
                </div>
                <div class="timer-controls">
                    <button class="timer-btn" onclick="pauseResumeTimer('${timerId}')">Pause</button>
                    <button class="timer-btn" onclick="cancelTimer('${timerId}')">Cancel</button>
                </div>
            </div>
        </div>
    `;
}

// Timer Logic
const timers = {};
function startTimer(timerId, seconds) {
    const displayEl = document.getElementById(`${timerId}-display`);
    if (!displayEl) return;
    
    timers[timerId] = {
        remaining: seconds,
        total: seconds,
        active: true,
        startTime: Date.now()
    };
    
    const updateTimer = () => {
        if (!timers[timerId]) return;
        
        const elapsed = Math.floor((Date.now() - timers[timerId].startTime) / 1000);
        timers[timerId].remaining = Math.max(0, timers[timerId].total - elapsed);
        
        const mins = Math.floor(timers[timerId].remaining / 60);
        const secs = timers[timerId].remaining % 60;
        displayEl.textContent = `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
        
        if (timers[timerId].remaining === 0 && timers[timerId].active) {
            timers[timerId].active = false;
            playBeep();
            displayEl.textContent = "COMPLETED!";
        } else if (timers[timerId].active) {
            requestAnimationFrame(updateTimer);
        }
    };
    
    updateTimer();
}

function pauseResumeTimer(timerId) {
    if (!timers[timerId]) return;
    timers[timerId].active = !timers[timerId].active;
    if (timers[timerId].active) {
        timers[timerId].startTime = Date.now() - (timers[timerId].total - timers[timerId].remaining) * 1000;
        startTimer(timerId, 0);
    }
}

function cancelTimer(timerId) {
    delete timers[timerId];
    const el = document.getElementById(timerId);
    if (el) el.remove();
}

// Beep sound for timer completion
function playBeep() {
    try {
        const audioContext = new (window.AudioContext || window.webkitAudioContext)();
        const osc = audioContext.createOscillator();
        const gain = audioContext.createGain();
        
        osc.connect(gain);
        gain.connect(audioContext.destination);
        
        osc.frequency.value = 1000;
        osc.type = 'sine';
        
        gain.gain.setValueAtTime(0.3, audioContext.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.5);
        
        osc.start(audioContext.currentTime);
        osc.stop(audioContext.currentTime + 0.5);
    } catch(e) {
        console.log("Beep failed:", e);
    }
}

// Stopwatch Card Renderer
function renderStopwatchCard(cmd) {
    const stopwatchId = `stopwatch-${Date.now()}`;
    return `
        <div class="command-card stopwatch-card" id="${stopwatchId}">
            <div class="card-header">
                <i class="fas fa-stopwatch"></i>
                <span>${cmd.title}</span>
            </div>
            <div class="card-body">
                <div class="timer-display" id="${stopwatchId}-display">00:00:00</div>
                <div class="timer-controls">
                    <button class="timer-btn" onclick="toggleStopwatch('${stopwatchId}')">Pause</button>
                    <button class="timer-btn" onclick="resetStopwatch('${stopwatchId}')">Reset</button>
                </div>
            </div>
        </div>
    `;
}

// Stopwatch Logic
const stopwatches = {};
function toggleStopwatch(stopwatchId) {
    if (!stopwatches[stopwatchId]) {
        stopwatches[stopwatchId] = {
            running: true,
            elapsed: 0,
            startTime: Date.now()
        };
    }
    
    stopwatches[stopwatchId].running = !stopwatches[stopwatchId].running;
    if (stopwatches[stopwatchId].running) {
        stopwatches[stopwatchId].startTime = Date.now() - stopwatches[stopwatchId].elapsed;
        updateStopwatch(stopwatchId);
    }
}

function resetStopwatch(stopwatchId) {
    if (stopwatches[stopwatchId]) {
        stopwatches[stopwatchId].elapsed = 0;
        stopwatches[stopwatchId].running = false;
    }
    const displayEl = document.getElementById(`${stopwatchId}-display`);
    if (displayEl) {
        displayEl.textContent = "00:00:00";
    }
}

function updateStopwatch(stopwatchId) {
    const displayEl = document.getElementById(`${stopwatchId}-display`);
    if (!displayEl || !stopwatches[stopwatchId] || !stopwatches[stopwatchId].running) return;
    
    stopwatches[stopwatchId].elapsed = Date.now() - stopwatches[stopwatchId].startTime;
    
    const totalSeconds = Math.floor(stopwatches[stopwatchId].elapsed / 1000);
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;
    
    displayEl.textContent = `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
    
    requestAnimationFrame(() => updateStopwatch(stopwatchId));
}

// Weather Card Renderer
function renderWeatherCard(cmd) {
    if (cmd.error) {
        return `
            <div class="command-card weather-card error">
                <div class="card-header">
                    <i class="fas fa-cloud"></i>
                    <span>${cmd.title}</span>
                </div>
                <div class="card-body">
                    <p>${cmd.error}</p>
                </div>
            </div>
        `;
    }
    return `
        <div class="command-card weather-card">
            <div class="card-header">
                <i class="fas fa-cloud-sun"></i>
                <span>${cmd.title}</span>
            </div>
            <div class="card-body">
                <div class="weather-grid">
                    <div class="weather-item">
                        <span class="label">Temperature</span>
                        <span class="value">${cmd.temperature}°C</span>
                    </div>
                    <div class="weather-item">
                        <span class="label">Condition</span>
                        <span class="value">${cmd.condition}</span>
                    </div>
                    <div class="weather-item">
                        <span class="label">Humidity</span>
                        <span class="value">${cmd.humidity}%</span>
                    </div>
                    <div class="weather-item">
                        <span class="label">Wind Speed</span>
                        <span class="value">${cmd.wind_speed} km/h</span>
                    </div>
                </div>
            </div>
        </div>
    `;
}

// Notes Card Renderers
function renderSaveNoteCard(cmd) {
    return `
        <div class="command-card note-card ${cmd.status}">
            <div class="card-header">
                <i class="fas fa-sticky-note"></i>
                <span>${cmd.title}</span>
            </div>
            <div class="card-body">
                <p>${cmd.text}</p>
            </div>
        </div>
    `;
}

function renderNotesCard(cmd) {
    if (cmd.count === 0) {
        return `
            <div class="command-card notes-card">
                <div class="card-header">
                    <i class="fas fa-list"></i>
                    <span>${cmd.title}</span>
                </div>
                <div class="card-body">
                    <p>No notes yet. Say "save note: [content]" to create one.</p>
                </div>
            </div>
        `;
    }
    
    const notesList = cmd.notes.map(note => `
        <div class="note-item">
            <p>${note.content}</p>
            <small>${new Date(note.created_at).toLocaleString()}</small>
        </div>
    `).join('');
    
    return `
        <div class="command-card notes-card">
            <div class="card-header">
                <i class="fas fa-list"></i>
                <span>${cmd.title} (${cmd.count})</span>
            </div>
            <div class="card-body notes-list">
                ${notesList}
            </div>
        </div>
    `;
}

// Reminder Card Renderers
function renderReminderCard(cmd) {
    return `
        <div class="command-card reminder-card ${cmd.status}">
            <div class="card-header">
                <i class="fas fa-bell"></i>
                <span>${cmd.title}</span>
            </div>
            <div class="card-body">
                <p>${cmd.text}</p>
                <small>Trigger: ${new Date(cmd.trigger_time).toLocaleString()}</small>
            </div>
        </div>
    `;
}

function renderRemindersCard(cmd) {
    if (cmd.count === 0) {
        return `
            <div class="command-card reminders-card">
                <div class="card-header">
                    <i class="fas fa-bells"></i>
                    <span>${cmd.title}</span>
                </div>
                <div class="card-body">
                    <p>No active reminders. Say "remind me in..." to create one.</p>
                </div>
            </div>
        `;
    }
    
    const remindersList = cmd.reminders.map(rem => `
        <div class="reminder-item">
            <p>${rem.content}</p>
            <small>${new Date(rem.trigger_time).toLocaleString()}</small>
        </div>
    `).join('');
    
    return `
        <div class="command-card reminders-card">
            <div class="card-header">
                <i class="fas fa-bells"></i>
                <span>${cmd.title} (${cmd.count})</span>
            </div>
            <div class="card-body reminders-list">
                ${remindersList}
            </div>
        </div>
    `;
}

// Schedule reminder notification
function scheduleReminderNotification(cmd) {
    if (cmd.status !== "success") return;
    
    const triggerTime = new Date(cmd.trigger_time);
    const now = new Date();
    const delayMs = triggerTime - now;
    
    if (delayMs > 0) {
        setTimeout(() => {
            if ('Notification' in window && Notification.permission === 'granted') {
                new Notification('Reminder', {
                    body: cmd.content,
                    icon: '/favicon.ico',
                    tag: cmd.reminder_id
                });
            }
            playBeep();
        }, delayMs);
    }
}

// Export Card Renderer
function renderExportCard(cmd) {
    if (cmd.status === "error") {
        return `
            <div class="command-card export-card error">
                <div class="card-header">
                    <i class="fas fa-download"></i>
                    <span>${cmd.title}</span>
                </div>
                <div class="card-body">
                    <p>${cmd.text}</p>
                </div>
            </div>
        `;
    }
    
    const blob = new Blob([cmd.content], { type: cmd.mime_type });
    const url = URL.createObjectURL(blob);
    
    return `
        <div class="command-card export-card success">
            <div class="card-header">
                <i class="fas fa-download"></i>
                <span>${cmd.title}</span>
            </div>
            <div class="card-body">
                <p>${cmd.text}</p>
                <a href="${url}" download="${cmd.filename}" class="card-button">
                    <i class="fas fa-file-download"></i> Download ${cmd.format.toUpperCase()}
                </a>
            </div>
        </div>
    `;
}

// Favorite Card Renderer
function renderFavoriteCard(cmd) {
    return `
        <div class="command-card favorite-card ${cmd.status}">
            <div class="card-header">
                <i class="fas fa-star"></i>
                <span>${cmd.title}</span>
            </div>
            <div class="card-body">
                <p>${cmd.text}</p>
            </div>
        </div>
    `;
}

// Calendar Card Renderer
function renderCalendarCard(cmd) {
    if (cmd.status === "error") {
        return `
            <div class="command-card calendar-card error">
                <div class="card-header">
                    <i class="fas fa-calendar-plus"></i>
                    <span>${cmd.title}</span>
                </div>
                <div class="card-body">
                    <p>${cmd.text}</p>
                </div>
            </div>
        `;
    }
    
    // Success case - event created in Google Calendar
    if (cmd.status === "success") {
        return `
            <div class="command-card calendar-card success">
                <div class="card-header">
                    <i class="fas fa-calendar-check" style="color: #10B981;"></i>
                    <span>${cmd.title}</span>
                </div>
                <div class="card-body">
                    <p style="color: #10B981; font-weight: 600; margin-bottom: 12px;">✅ Event created in Google Calendar!</p>
                    <div class="event-preview">
                        <div class="event-field">
                            <label>Event:</label>
                            <strong>${cmd.event.title}</strong>
                        </div>
                        <div class="event-field">
                            <label>Event ID:</label>
                            <code style="background: #1a1a1a; padding: 4px 8px; border-radius: 4px; font-size: 12px;">${cmd.event_id}</code>
                        </div>
                    </div>
                    <a href="${cmd.calendar_link}" target="_blank" class="card-button" style="display: inline-block; margin-top: 12px;">
                        <i class="fas fa-external-link-alt"></i> Open in Google Calendar
                    </a>
                </div>
            </div>
        `;
    }
    
    // Preview case - awaiting Google Calendar connection
    const event = cmd.event;
    return `
        <div class="command-card calendar-card preview">
            <div class="card-header">
                <i class="fas fa-calendar-check"></i>
                <span>${cmd.title}</span>
            </div>
            <div class="card-body">
                <div class="event-preview">
                    <div class="event-field">
                        <label>Event:</label>
                        <strong>${event.title}</strong>
                    </div>
                    <div class="event-field">
                        <label>Date:</label>
                        <span>${event.date}</span>
                    </div>
                    <div class="event-field">
                        <label>Time:</label>
                        <span>${event.time}</span>
                    </div>
                    ${event.attendees ? `<div class="event-field">
                        <label>With:</label>
                        <span>${event.attendees}</span>
                    </div>` : ''}
                </div>
                <p class="preview-note">📝 Event preview - Connect your Google Calendar to create</p>
            </div>
        </div>
    `;
}

// === Pipeline Indicator ===
function updatePipelineIndicator(stage, status, statusMsg) {
    const stages = ['stt', 'nlp', 'llm', 'tts'];
    const stageIds = {
        'stt': 'stageSTT',
        'nlp': 'stageNLP',
        'llm': 'stageLLM',
        'tts': 'stageTTS'
    };
    const stageLabelIds = {
        'stt': 'stageLabelSTT',
        'nlp': 'stageLabelNLP',
        'llm': 'stageLabelLLM',
        'tts': 'stageLabelTTS'
    };

    stages.forEach(s => {
        const element = document.getElementById(stageIds[s]);
        const label = document.getElementById(stageLabelIds[s]);
        if (element) {
            element.classList.remove('active', 'completed');
            label.classList.remove('active', 'completed');
        }
    });

    if (status === 'active') {
        const element = document.getElementById(stageIds[stage]);
        const label = document.getElementById(stageLabelIds[stage]);
        if (element) {
            element.classList.add('active');
            label.classList.add('active');
        }
        
        const currentIndex = stages.indexOf(stage);
        for (let i = 0; i < currentIndex; i++) {
            const prevElement = document.getElementById(stageIds[stages[i]]);
            const prevLabel = document.getElementById(stageLabelIds[stages[i]]);
            if (prevElement) {
                prevElement.classList.add('completed');
                prevLabel.classList.add('completed');
            }
        }

        // Update progress bar
        const progress = ((currentIndex + 1) / stages.length) * 100;
        document.getElementById('progressBar').style.width = progress + '%';
    } else if (status === 'complete') {
        stages.forEach(s => {
            const element = document.getElementById(stageIds[s]);
            const label = document.getElementById(stageLabelIds[s]);
            if (element) {
                element.classList.add('completed');
                element.classList.remove('active');
                label.classList.add('completed');
                label.classList.remove('active');
            }
        });
        // Complete progress bar
        document.getElementById('progressBar').style.width = '100%';
    }

    const statusElement = document.getElementById('pipelineStatus');
    if (statusElement) {
        statusElement.textContent = statusMsg || '';
        if (status === 'active') {
            statusElement.classList.add('active');
        } else {
            statusElement.classList.remove('active');
        }
    }
}

function resetPipelineIndicator() {
    const stages = ['stt', 'nlp', 'llm', 'tts'];
    const stageIds = {
        'stt': 'stageSTT',
        'nlp': 'stageNLP',
        'llm': 'stageLLM',
        'tts': 'stageTTS'
    };
    const stageLabelIds = {
        'stt': 'stageLabelSTT',
        'nlp': 'stageLabelNLP',
        'llm': 'stageLabelLLM',
        'tts': 'stageLabelTTS'
    };

    stages.forEach(s => {
        const element = document.getElementById(stageIds[s]);
        const label = document.getElementById(stageLabelIds[s]);
        if (element) {
            element.classList.remove('active', 'completed');
            label.classList.remove('active', 'completed');
        }
    });

    const statusElement = document.getElementById('pipelineStatus');
    if (statusElement) {
        statusElement.textContent = '';
        statusElement.classList.remove('active');
    }
}

// === Audio Recording ===
async function initAudioContext() {
    try {
        audioContext = new (window.AudioContext || window.webkitAudioContext)();
    } catch (e) {
        console.error("AudioContext not supported", e);
    }
}

async function startRecording() {
    try {
        if (!wsConnected || ws.readyState !== WebSocket.OPEN) {
            addMessage("system", "⏳ Waiting for connection...");
            return;
        }

        // Generate conversation ID only if one doesn't exist
        if (!conversationId) {
            conversationId = null; // Will be set by server
        }
        lastTranscript = null;
        currentAudioId = null;

        if (currentAudio) {
            currentAudio.pause();
            currentAudio.onended = null;
        }
        if (currentAudioUrl) {
            URL.revokeObjectURL(currentAudioUrl);
            currentAudioUrl = null;
        }

        mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        mediaRecorder = new MediaRecorder(mediaStream);
        audioChunks = [];

        mediaRecorder.ondataavailable = (e) => {
            audioChunks.push(e.data);
        };

        mediaRecorder.onstop = () => {
            const audioBlob = new Blob(audioChunks, { type: 'audio/wav' });
            sendAudioToServer(audioBlob);
            stopWaveformAnimation();
        };

        mediaRecorder.start();
        isRecording = true;
        updateMicUI();
        updateMicLabel("🎙️ Recording... Click to stop");
        
        // Setup analyser for silence detection
        setupAnalyser();
        startSilenceDetection();
    } catch (error) {
        console.error("Microphone access denied:", error);
        addMessage("system", "❌ Microphone access denied");
    }
}

function stopRecording() {
    if (mediaRecorder && isRecording) {
        mediaRecorder.stop();
        mediaStream.getTracks().forEach(track => track.stop());
        isRecording = false;
        updateMicUI();
        updateMicLabel("Processing...");
        clearSilenceDetection();
    }
}

// === WAVEFORM & SILENCE DETECTION ===

function setupAnalyser() {
    if (!audioContext || !mediaStream) return;
    
    const source = audioContext.createMediaStreamSource(mediaStream);
    analyser = audioContext.createAnalyser();
    analyser.fftSize = 256;
    source.connect(analyser);
}

function startSilenceDetection() {
    lastSoundTime = Date.now();
    
    function checkSilence() {
        if (!analyser || !isRecording) return;
        
        const dataArray = new Uint8Array(analyser.frequencyBinCount);
        analyser.getByteFrequencyData(dataArray);
        
        // Calculate average volume
        const average = dataArray.reduce((a, b) => a + b) / dataArray.length;
        
        if (average > SILENCE_THRESHOLD) {
            // Sound detected
            lastSoundTime = Date.now();
        } else {
            // Silence detected
            const timeSinceSoundMs = Date.now() - lastSoundTime;
            
            if (timeSinceSoundMs >= SILENCE_DURATION && audioChunks.length > 0) {
                // Auto-stop after 5 seconds of silence
                console.log(`🤐 Silence detected for ${timeSinceSoundMs}ms - Auto-stopping`);
                stopRecording();
                return;
            }
        }
        
        silenceTimer = requestAnimationFrame(checkSilence);
    }
    
    checkSilence();
}

function clearSilenceDetection() {
    if (silenceTimer) {
        cancelAnimationFrame(silenceTimer);
        silenceTimer = null;
    }
}

function sendAudioToServer(audioBlob) {
    if (!wsConnected || ws.readyState !== WebSocket.OPEN) {
        console.error("WebSocket not ready. State:", ws.readyState);
        addMessage("system", "❌ Connection not ready. Please wait...");
        return;
    }

    const reader = new FileReader();
    reader.onload = (e) => {
        const audioData = e.target.result;
        
        // Convert ArrayBuffer to base64 safely (avoid stack overflow)
        const bytes = new Uint8Array(audioData);
        let binary = '';
        for (let i = 0; i < bytes.byteLength; i += 8192) {
            const chunk = bytes.subarray(i, i + 8192);
            binary += String.fromCharCode.apply(null, chunk);
        }
        const base64 = btoa(binary);

        const message = {
            type: "audio",
            audio: base64,
            language_code: currentLanguage
        };

        try {
            ws.send(JSON.stringify(message));
        } catch (err) {
            console.error("Send error:", err);
            addMessage("system", "❌ Failed to send audio");
        }
    };
    reader.readAsArrayBuffer(audioBlob);
}

// === Audio Playback ===
function playAudio(base64Data, format, audioId) {
    try {
        console.log("🔊 Playing audio - ID:", audioId, "Format:", format, "Current ID:", currentAudioId);

        if (currentAudioId === null || audioId === currentAudioId) {
            console.log("✅ Accepting audio:", audioId);
        } else {
            console.log("⏭️  Ignoring old audio:", audioId, "Current:", currentAudioId);
            return;
        }

        if (currentAudio) {
            currentAudio.pause();
            currentAudio.onended = null;
        }
        if (currentAudioUrl) {
            URL.revokeObjectURL(currentAudioUrl);
        }

        const binaryString = atob(base64Data);
        const bytes = new Uint8Array(binaryString.length);
        for (let i = 0; i < binaryString.length; i++) {
            bytes[i] = binaryString.charCodeAt(i);
        }
        const audioBlob = new Blob([bytes], { type: 'audio/mp3' });
        const audioUrl = URL.createObjectURL(audioBlob);
        currentAudioUrl = audioUrl;
        currentAudioId = audioId;
        
        console.log("🎵 Created audio blob, size:", audioBlob.size);
        
        currentAudio = new Audio(audioUrl);
        
        currentAudio.onloadstart = () => console.log("📥 Audio loading...");
        currentAudio.oncanplay = () => console.log("▶️  Audio ready to play");
        currentAudio.onplay = () => console.log("🔊 Audio PLAYING NOW");
        currentAudio.onended = () => {
            console.log("✅ Audio finished");
            if (currentAudioUrl === audioUrl) {
                URL.revokeObjectURL(audioUrl);
                currentAudioUrl = null;
            }
        };
        currentAudio.onerror = (e) => console.error("❌ Audio error:", e);
        
        console.log("⏯️  Calling play()...");
        currentAudio.play().then(() => {
            console.log("✅ Play initiated successfully");
        }).catch(e => {
            console.error("❌ Play error:", e);
            addMessage("system", "❌ Audio playback failed: " + e.message);
        });
    } catch (e) {
        console.error("❌ Audio decode error:", e);
        addMessage("system", "❌ Audio decode error: " + e.message);
    }
}

// === UI Updates ===
function setupMicButton() {
    const btn = document.getElementById("micBtn");
    btn.addEventListener("click", () => {
        if (isRecording) {
            stopRecording();
        } else {
            startRecording();
        }
    });
}

function setupTextInput() {
    const textInput = document.getElementById("textInput");
    const sendBtn = document.getElementById("sendBtn");
    
    // Send on button click
    sendBtn.addEventListener("click", () => {
        const text = textInput.value.trim();
        if (text) {
            sendTextMessage(text);
            textInput.value = '';
            textInput.focus();
        }
    });
    
    // Send on Enter key
    textInput.addEventListener("keypress", (e) => {
        if (e.key === "Enter") {
            const text = textInput.value.trim();
            if (text) {
                sendTextMessage(text);
                textInput.value = '';
            }
        }
    });
}

function sendTextMessage(text) {
    if (!wsConnected || ws.readyState !== WebSocket.OPEN) {
        console.error("WebSocket not ready. State:", ws.readyState);
        addMessage("system", "❌ Connection not ready. Please wait...");
        return;
    }

    // Generate conversation ID only if one doesn't exist
    if (!conversationId) {
        conversationId = null; // Will be set by server
    }
    lastTranscript = null;
    currentAudioId = null;

    // Display user message
    addMessage("user", text);

    // Send text message to backend (skip STT, go straight to Gemini)
    const message = {
        type: "text",
        text: text,
        language_code: currentLanguage
    };

    try {
        ws.send(JSON.stringify(message));
    } catch (err) {
        console.error("Send error:", err);
        addMessage("system", "❌ Failed to send message");
    }
}

function updateMicUI() {
    const btn = document.getElementById("micBtn");
    const indicator = document.getElementById("recordingIndicator");
    
    if (isRecording) {
        btn.classList.add("recording");
        indicator.classList.add("active");
    } else {
        btn.classList.remove("recording");
        indicator.classList.remove("active");
    }
}

function updateMicLabel(text) {
    document.getElementById("micLabel").textContent = text;
}

function setupLanguageButtons() {
    document.querySelectorAll(".lang-chip").forEach(btn => {
        btn.addEventListener("click", () => {
            document.querySelectorAll(".lang-chip").forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            currentLanguage = btn.dataset.lang;
            addMessage("system", `🗣️ Language set to: ${btn.textContent}`);
        });
    });
}

function addMessage(role, text) {
    const messagesDiv = document.getElementById("messages");
    
    // Optionally skip displaying system messages in chat
    // if (role === "system") {
    //     console.log("ℹ️ System:", text);
    //     return;
    // }
    
    const messageDiv = document.createElement("div");
    messageDiv.className = `message ${role}`;
    
    const contentDiv = document.createElement("div");
    contentDiv.className = "message-content";
    
    // For command responses, allow HTML; for regular text, use textContent for safety
    if (role === "command") {
        contentDiv.innerHTML = text;
    } else {
        contentDiv.textContent = text;
    }
    
    messageDiv.appendChild(contentDiv);
    messagesDiv.appendChild(messageDiv);
    
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
}
