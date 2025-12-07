import { addMessage, addProcessingBubble, startAssistantStream, renderHistory, renderStatusEvent } from './ui/messages.js';
import { attachSettingsListeners, loadChat, refreshGenerationSettings, refreshModel, refreshSessions, refreshTools } from './ui/settings.js';
import { ChatStream } from './ui/stream.js';


const promptEl = document.getElementById('prompt');
const formEl = document.getElementById('chat-form');
const sendBtn = document.getElementById('send-btn');
const newChatBtn = document.getElementById('new-chat');
const settingsToggle = document.getElementById('settings-toggle');
const settingsClose = document.getElementById('settings-close');
const settingsPanel = document.getElementById('settings-panel');
const suggestionButtons = document.querySelectorAll('.suggestion-card');
const suggestionsContainer = document.querySelector('.suggestions');

let chatId = null;
let streaming = false;
let settingsOpen = false;
let activeProgress = null;

const handleChatSelect = async (id) => {
    chatId = id;
    try {
        await loadChat(id);
    } catch (err) {
        console.error(err);
        addMessage('assistant', 'Could not load chat history.');
    } finally {
        refreshSessions(chatId, handleChatSelect);
    }
};

if (settingsToggle && settingsPanel) {
    settingsToggle.addEventListener('click', () => {
        settingsOpen = !settingsOpen;
        settingsPanel.classList.toggle('open', settingsOpen);
    });
}

if (settingsClose && settingsPanel) {
    settingsClose.addEventListener('click', () => {
        settingsOpen = false;
        settingsPanel.classList.remove('open');
    });
}

async function sendMessage(text) {
    streaming = true;
    sendBtn.disabled = true;
    sendBtn.textContent = 'Sending...';
    const progress = addProcessingBubble();
    activeProgress = progress;
    const stream = startAssistantStream();
    let chatIdReceived = null;
    let completed = false;

    try {
        const response = await fetch('/api/chat/stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: text, chat_id: chatId || null }),
        });

        for await (const { event, data } of ChatStream(response)) {
            if (event === 'error') {
                throw new Error(data || 'Stream error');
            }

            if (['status', 'tool_start', 'tool_result', 'reasoning'].includes(event)) {
                try {
                    const parsed = data ? JSON.parse(data) : {};
                    renderStatusEvent(activeProgress, event, parsed);
                } catch (e) {
                    console.error('Failed to parse status event', e);
                }
                continue;
            }

            if (event === 'done') {
                if (data) chatIdReceived = data;
                progress.complete();
                completed = true;
                if (stream.attach) stream.attach();
                stream.done();
                break;
            }

            if (data) stream.append(data);
        }

        if (chatIdReceived) chatId = chatIdReceived;

    } catch (err) {
        console.error(err);
        addMessage('assistant', 'Something went wrong. Please try again.');
    } finally {
        if (!completed) {
            progress.complete();
        }
        activeProgress = null;
        streaming = false;
        sendBtn.disabled = false;
        sendBtn.textContent = 'Send';
        await refreshSessions();
    }
}

formEl.addEventListener('submit', (e) => {
    e.preventDefault();
    const text = promptEl.value.trim();
    if (!text || streaming) return;
    addMessage('user', text);
    promptEl.value = '';
    sendMessage(text);
});

promptEl.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        formEl.dispatchEvent(new Event('submit'));
    }
});

newChatBtn.addEventListener('click', () => {
    chatId = null;
    renderHistory([]);
    addMessage('assistant', 'New chat started. How can I help?');
    refreshSessions(chatId, handleChatSelect);
});

suggestionButtons.forEach((btn) =>
    btn.addEventListener('click', () => {
        const prompt = btn.dataset.prompt || btn.textContent;
        promptEl.value = prompt;
        promptEl.focus();
    })
);

async function refreshSamples() {
    try {
        const res = await fetch('/api/samples');
        if (!res.ok) return;
        const samples = await res.json();
        if (!Array.isArray(samples) || !suggestionsContainer) return;
        suggestionsContainer.innerHTML = '';
        samples.forEach((s) => {
            const btn = document.createElement('button');
            btn.className = 'suggestion-card';
            btn.dataset.prompt = s.prompt || '';
            btn.innerHTML = `
                <div class="suggestion-title">${s.title || 'Sample'}</div>
                <p>${s.description || ''}</p>
            `;
            btn.addEventListener('click', () => {
                const prompt = btn.dataset.prompt || btn.textContent;
                promptEl.value = prompt;
                promptEl.focus();
            });
            suggestionsContainer.appendChild(btn);
        });
    } catch (err) {
        console.error(err);
    }
}

// seed welcome message & data
addMessage('assistant', 'Hey! I am BlueGPT. I use OpenAI plus optional MCP tools via a local agentic loop. Ask me anything, or click a suggestion to start.');
refreshSessions(chatId, handleChatSelect);
refreshModel();
refreshTools();
refreshSamples();
refreshGenerationSettings();
attachSettingsListeners();
