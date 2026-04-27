(function () {
    const CONFIG = window.CHAT_CONFIG || {};
    const urls = CONFIG.urls || {};
    const texts = CONFIG.texts || {};
    const lang = CONFIG.lang || 'pl';

    const chatInput = document.getElementById('chat-input');
    const modelSelect = document.getElementById('model-select');
    const algoSelect = document.getElementById('algorithm-select');
    const newChatFlag = document.getElementById('new-chat-flag');
    const chatOutput = document.getElementById('chat-output');
    const btnNewChat = document.getElementById('btn-new-chat');
    const chatEmpty = document.getElementById('chat-empty');
    const spinner = document.getElementById('loading-spinner');
    const btnSend = document.getElementById('btn-send');
    const localHistoryEnabled = document.getElementById('local-history-enabled');
    const historySidebar = document.getElementById('history-sidebar');
    const historyList = document.getElementById('history-list');
    const historySearch = document.getElementById('history-search');
    const sysPromptPanel = document.getElementById('system-prompt-panel');
    const sysPromptInput = document.getElementById('system-prompt');
    const inputStats = document.getElementById('input-stats');
    const currentChatTitle = document.getElementById('current-chat-title');
    const promptModal = document.getElementById('prompt-modal');
    const btnOpenPrompts = document.getElementById('btn-open-prompts');
    const btnClosePrompts = document.getElementById('btn-close-prompts');
    const privacyWarningModal = document.getElementById('privacy-warning-modal');
    const btnConfirmNoAnno = document.getElementById('btn-confirm-no-anno');
    const btnCancelNoAnno = document.getElementById('btn-cancel-no-anno');

    let currentChatId = null;

    function autoResize() {
        chatInput.style.height = 'auto';
        chatInput.style.height = chatInput.scrollHeight + 'px';
    }

    chatInput.addEventListener('input', autoResize);

    function formatDate(timestamp) {
        const date = new Date(timestamp);
        return new Intl.DateTimeFormat(lang === 'pl' ? 'pl-PL' : 'en-US', {
            day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit'
        }).format(date);
    }

    function updateInputStats() {
        const t = chatInput.value;
        const chars = t.length;
        const words = t.trim() ? t.trim().split(/\s+/).length : 0;
        inputStats.textContent = texts.statsCharsWords?.replace('{chars}', chars).replace('{words}', words) || `${chars} chars | ${words} words`;
    }

    function updateSessionStatus() {
        const statusEl = document.getElementById('session-status');
        if (algoSelect.value === 'no_anno') {
            statusEl.innerHTML = `<span class="session-warning" style="display:flex; align-items:center; gap:0.6rem;"><span class="pill pill-danger">${texts.sessionUnsecure || 'UNSECURE'}</span></span>`;
        } else {
            const algoText = algoSelect.options[algoSelect.selectedIndex].text;
            statusEl.innerHTML = `${texts.sessionSecure || 'Secure'} <span class="pill pill-success">${algoText}</span>`;
        }
    }

    function getLocalChats() {
        const data = localStorage.getItem('llm_router_chats');
        return data ? JSON.parse(data) : {};
    }

    function saveLocalChats(chats) {
        localStorage.setItem('llm_router_chats', JSON.stringify(chats));
    }

    function toggleHistory() {
        const isHidden = historySidebar.classList.toggle('hidden');
        localStorage.setItem('chat_history_visible', !isHidden);
        if (!isHidden) renderHistoryList();
    }

    function renderHistoryList() {
        const chats = getLocalChats();
        const searchTerm = historySearch.value.toLowerCase();
        historyList.innerHTML = '';
        const sortedChats = Object.entries(chats).sort((a, b) => b[1].timestamp - a[1].timestamp);
        sortedChats.forEach(([id, chat]) => {
            if (searchTerm && !chat.name.toLowerCase().includes(searchTerm)) return;
            const item = document.createElement('div');
            item.className = `history-item ${id === currentChatId ? 'active' : ''}`;
            item.innerHTML = `
                <div class="history-item-info">
                    <span class="history-item-name" title="${chat.name}">${chat.name}</span>
                    <span class="history-item-date">${formatDate(chat.timestamp)}</span>
                </div>
                <div class="history-actions">
                    <button type="button" class="btn-icon-small" data-id="${id}" title="Rename"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg></button>
                    <button type="button" class="btn-icon-small del" data-id="${id}" title="Delete"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg></button>
                </div>`;
            item.onclick = (e) => {
                if (!e.target.closest('.history-actions')) loadChatById(id);
            };
            item.querySelector('[data-id]').onclick = (e) => {
                e.stopPropagation();
                renameChatById(id);
            };
            item.querySelector('.del').onclick = (e) => {
                e.stopPropagation();
                deleteChatById(id);
            };
            historyList.appendChild(item);
        });
    }

    async function loadChatById(id) {
        const chats = getLocalChats();
        const chat = chats[id];
        if (!chat) return;
        currentChatId = id;
        currentChatTitle.textContent = chat.name;
        try {
            await fetch(urls.importChat, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({history: chat.messages})
            });
        } catch (e) {
            alert((texts.jsSyncError || 'Sync error: ') + e.message);
        }
        chatOutput.innerHTML = '';
        chat.messages.forEach(msg => addMessage(msg.role, msg.content));
        if (chatEmpty) chatEmpty.style.display = 'none';
        newChatFlag.value = 'false';
        renderHistoryList();
    }

    function renameChatById(id) {
        const chats = getLocalChats();
        const oldName = chats[id].name;
        const newName = prompt(texts.jsRenamePrompt || 'New name:', oldName);
        if (newName && newName.trim()) {
            chats[id].name = newName.trim();
            saveLocalChats(chats);
            if (currentChatId === id) currentChatTitle.textContent = chats[id].name;
            renderHistoryList();
        }
    }

    function deleteChatById(id) {
        if (!confirm(texts.jsDeleteConfirm || 'Delete?')) return;
        const chats = getLocalChats();
        delete chats[id];
        saveLocalChats(chats);
        if (currentChatId === id) {
            currentChatId = null;
            btnNewChat.click();
        }
        renderHistoryList();
    }

    function persistCurrentChat() {
        if (!localHistoryEnabled.checked) return;
        const messages = Array.from(document.querySelectorAll('.msg')).map(msg => ({
            role: msg.dataset.role,
            content: msg.dataset.content
        }));
        if (messages.length === 0) return;
        const chats = getLocalChats();
        if (!currentChatId) {
            currentChatId = 'chat_' + Date.now();
            const firstMsg = messages[0].content || 'New chat';
            const name = firstMsg.slice(0, 30) + (firstMsg.length > 30 ? '...' : '');
            chats[currentChatId] = {name, timestamp: Date.now(), messages};
        } else {
            chats[currentChatId].messages = messages;
            chats[currentChatId].timestamp = Date.now();
        }
        saveLocalChats(chats);
    }

    function saveState() {
        localStorage.setItem('chat_last_text', chatInput.value);
        localStorage.setItem('chat_last_model', modelSelect.value);
        localStorage.setItem('chat_last_algo', algoSelect.value);
        localStorage.setItem('chat_last_sys_prompt', sysPromptInput.value);
        localStorage.setItem('chat_local_history', localHistoryEnabled.checked);
    }

    function loadState() {
        const txt = localStorage.getItem('chat_last_text');
        const mdl = localStorage.getItem('chat_last_model');
        const alg = localStorage.getItem('chat_last_algo');
        const sys = localStorage.getItem('chat_last_sys_prompt');
        const locHist = localStorage.getItem('chat_local_history');
        if (txt) chatInput.value = txt;
        if (sys) sysPromptInput.value = sys;
        if (locHist !== null) localHistoryEnabled.checked = locHist === 'true';
        if (alg && [...algoSelect.options].some(o => o.value === alg)) algoSelect.value = alg;
        return {mdl, alg};
    }

    chatInput.addEventListener('input', () => {
        saveState();
        updateInputStats();
        autoResize();
    });
    sysPromptInput.addEventListener('input', saveState);
    modelSelect.addEventListener('change', saveState);

    algoSelect.addEventListener('change', () => {
        if (algoSelect.value === 'no_anno') privacyWarningModal.classList.add('active');
        else {
            saveState();
            updateSessionStatus();
        }
    });
    btnConfirmNoAnno.onclick = () => {
        privacyWarningModal.classList.remove('active');
        saveState();
        updateSessionStatus();
    };
    btnCancelNoAnno.onclick = () => {
        algoSelect.value = localStorage.getItem('chat_last_algo') || 'fast';
        privacyWarningModal.classList.remove('active');
        updateSessionStatus();
    };
    localHistoryEnabled.addEventListener('change', saveState);
    historySearch.addEventListener('input', renderHistoryList);

    async function loadModels() {
        try {
            const resp = await fetch(urls.models);
            const data = await resp.json();
            const models = data.models || [];
            modelSelect.innerHTML = '';
            models.forEach(m => {
                const name = typeof m === 'string' ? m : (m.id || m.name);
                const opt = document.createElement('option');
                opt.value = name;
                opt.textContent = name;
                modelSelect.appendChild(opt);
            });
            const {mdl} = loadState();
            if (mdl && [...modelSelect.options].some(o => o.value === mdl)) modelSelect.value = mdl;
            else if (modelSelect.options.length) modelSelect.selectedIndex = 0;
        } catch (e) {
            modelSelect.innerHTML = '<option disabled selected>Error loading models</option>';
        }
    }

    document.addEventListener('DOMContentLoaded', () => {
        loadModels();
        updateSessionStatus();
        updateInputStats();
        autoResize();
        const isVisible = localStorage.getItem('chat_history_visible') !== 'false';
        if (!isVisible) historySidebar.classList.add('hidden'); else renderHistoryList();
        document.getElementById('btn-toggle-history').onclick = toggleHistory;
        document.getElementById('btn-sidebar-new-chat').onclick = () => btnNewChat.click();
        document.getElementById('btn-toggle-sys-prompt').onclick = () => sysPromptPanel.classList.toggle('active');
    });

    btnOpenPrompts.onclick = () => promptModal.classList.add('active');
    btnClosePrompts.onclick = () => promptModal.classList.remove('active');
    promptModal.onclick = (e) => {
        if (e.target === promptModal) promptModal.classList.remove('active');
    };
    document.querySelectorAll('.prompt-chip').forEach(chip => {
        chip.onclick = () => {
            chatInput.value += (chatInput.value ? '\n\n' : '') + chip.dataset.text;
            updateInputStats();
            autoResize();
            chatInput.focus();
            promptModal.classList.remove('active');
        };
    });

    const ANON_RE = /\{[^{}\s]+\}/g;

    function createHighlightedFragment(text) {
        const frag = document.createDocumentFragment();
        let last = 0, match;
        while ((match = ANON_RE.exec(text)) !== null) {
            if (match.index > last) frag.appendChild(document.createTextNode(text.slice(last, match.index)));
            const span = document.createElement('span');
            span.className = 'anon-tag';
            span.textContent = match[0];
            frag.appendChild(span);
            last = match.index + match[0].length;
        }
        if (last < text.length) frag.appendChild(document.createTextNode(text.slice(last)));
        return frag;
    }

    function highlightInElement(el) {
        const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, {
            acceptNode(node) {
                if (!ANON_RE.test(node.nodeValue)) return NodeFilter.FILTER_REJECT;
                if (node.parentElement && node.parentElement.closest('pre, code')) return NodeFilter.FILTER_REJECT;
                return NodeFilter.FILTER_ACCEPT;
            }
        });
        const nodes = [];
        while (walker.nextNode()) nodes.push(walker.currentNode);
        nodes.forEach(n => n.parentNode.replaceChild(createHighlightedFragment(n.nodeValue), n));
    }

    function addMessage(role, raw, {streaming = false} = {}) {
        if (chatEmpty) chatEmpty.style.display = 'none';
        const wrap = document.createElement('div');
        wrap.className = `msg ${role}`;
        wrap.dataset.role = role;
        wrap.dataset.content = raw;
        const meta = document.createElement('div');
        meta.className = 'msg-meta';
        meta.innerHTML = `<span style="font-weight:600">${role === 'user' ? (texts.roleUser || 'You') : (texts.roleAssistant || 'AI')}</span> <span>${new Date().toLocaleTimeString([], {
            hour: '2-digit',
            minute: '2-digit'
        })}</span>`;
        const bubble = document.createElement('div');
        bubble.className = 'bubble';
        if (role === 'assistant') {
            const inner = document.createElement('div');
            inner.innerHTML = streaming ? '...' : marked.parse(raw);
            bubble.appendChild(inner);
            const actions = document.createElement('div');
            actions.className = 'msg-actions';
            actions.style.cssText = 'display: flex; gap: 0.5rem; margin-top: 0.5rem; justify-content: flex-end; opacity: 0.7;';
            const copyBtn = document.createElement('button');
            copyBtn.type = 'button';
            copyBtn.className = 'btnx copy-btn';
            copyBtn.style.cssText = 'padding: 4px 8px; display: inline-flex; align-items: center; justify-content: center; cursor: pointer;';
            copyBtn.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>`;
            copyBtn.onclick = async () => {
                const textToCopy = wrap.dataset.content || '';
                if (!textToCopy) return;
                try {
                    if (navigator.clipboard && navigator.clipboard.writeText) await navigator.clipboard.writeText(textToCopy);
                    else {
                        const ta = document.createElement('textarea');
                        ta.value = textToCopy;
                        ta.style.position = 'fixed';
                        ta.style.opacity = '0';
                        document.body.appendChild(ta);
                        ta.select();
                        document.execCommand('copy');
                        document.body.removeChild(ta);
                    }
                    const originalHtml = copyBtn.innerHTML;
                    copyBtn.textContent = '✓';
                    setTimeout(() => copyBtn.innerHTML = originalHtml, 2000);
                } catch (err) {
                    console.error(err);
                }
            };
            const regenBtn = document.createElement('button');
            regenBtn.type = 'button';
            regenBtn.className = 'btnx regenerate-btn';
            regenBtn.style.cssText = 'padding: 4px 8px; display: inline-flex; align-items: center; justify-content: center; cursor: pointer;';
            regenBtn.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M23 4v6h-6"></path><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"></path></svg>`;
            actions.append(copyBtn, regenBtn);
            bubble.appendChild(actions);
            wrap._assistantInner = inner;
            highlightInElement(inner);
            document.querySelectorAll('.regenerate-btn').forEach(btn => btn.style.display = 'none');
            regenBtn.style.display = 'inline-block';
        } else {
            bubble.appendChild(createHighlightedFragment(raw));
        }
        wrap.append(meta, bubble);
        chatOutput.appendChild(wrap);
        chatOutput.scrollTop = chatOutput.scrollHeight;
        return wrap;
    }

    document.addEventListener('click', async function (e) {
        const regenBtn = e.target.closest('.regenerate-btn');
        if (!regenBtn) return;
        const assistantWrap = regenBtn.closest('.msg.assistant');
        const userWrap = assistantWrap.previousElementSibling;
        if (!userWrap || !userWrap.classList.contains('user')) return;
        const userText = userWrap.dataset.content || '';
        let current = assistantWrap;
        while (current) {
            const next = current.nextElementSibling;
            current.remove();
            current = next;
        }
        const remaining = Array.from(document.querySelectorAll('.msg'));
        const beforeUser = remaining.slice(0, -1);
        try {
            await fetch(urls.importChat, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    history: beforeUser.map(msg => ({
                        role: msg.dataset.role,
                        content: msg.dataset.content
                    }))
                })
            });
            const assistantWrapNew = addMessage('assistant', '', {streaming: true});
            const inner = assistantWrapNew._assistantInner;
            spinner.classList.add('active');
            btnSend.disabled = true;
            const formData = new FormData();
            formData.append('message', userText);
            formData.append('algorithm', algoSelect.value);
            formData.append('model_name', modelSelect.value);
            formData.append('system_prompt', sysPromptInput.value);
            formData.append('new_chat', 'false');
            const resp = await fetch(urls.chatMessage, {method: 'POST', body: formData});
            if (!resp.body) {
                const txt = await resp.text();
                inner.innerHTML = marked.parse(txt);
                highlightInElement(inner);
                assistantWrapNew.dataset.content = txt;
            } else {
                const reader = resp.body.getReader();
                const dec = new TextDecoder();
                let markdown = '';
                while (true) {
                    const {value, done} = await reader.read();
                    if (done) break;
                    markdown += dec.decode(value, {stream: true});
                    inner.innerHTML = marked.parse(markdown);
                    highlightInElement(inner);
                    chatOutput.scrollTop = chatOutput.scrollHeight;
                }
                assistantWrapNew.dataset.content = markdown;
                await fetch(urls.chatFinalize, {
                    method: 'POST',
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({assistant: markdown})
                });
            }
        } catch (err) {
            console.error(err);
            addMessage('assistant', `Error: ${err}`);
        } finally {
            spinner.classList.remove('active');
            btnSend.disabled = false;
        }
    });

    btnNewChat.addEventListener('click', () => {
        if (!confirm(texts.jsNewChatConfirm || 'New chat?')) return;
        newChatFlag.value = 'true';
        currentChatId = null;
        currentChatTitle.textContent = texts.chatTitle || 'Chat';
        chatOutput.innerHTML = '';
        chatOutput.appendChild(chatEmpty);
        chatEmpty.style.display = '';
        renderHistoryList();
    });

    const btnExport = document.getElementById('btn-export-chat');
    const btnImport = document.getElementById('btn-import-chat');
    const fileInput = document.getElementById('chat-file-input');
    btnExport.addEventListener('click', () => {
        const messages = Array.from(document.querySelectorAll('.msg')).map(msg => ({
            role: msg.dataset.role,
            content: msg.dataset.content || ''
        }));
        if (messages.length === 0) return alert('No messages!');
        const blob = new Blob([JSON.stringify(messages, null, 2)], {type: 'application/json'});
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `chat-export-${new Date().toISOString().slice(0, 20)}.json`;
        a.click();
    });
    btnImport.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', async (e) => {
        const file = e.target.files[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = async (event) => {
            try {
                const history = JSON.parse(event.target.result);
                await fetch(urls.importChat, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({history})
                });
                chatOutput.innerHTML = '';
                history.forEach(msg => addMessage(msg.role, msg.content));
                if (chatEmpty) chatEmpty.style.display = 'none';
                newChatFlag.value = 'false';
            } catch (err) {
                alert('Import error: ' + err.message);
            } finally {
                fileInput.value = '';
            }
        };
        reader.readAsText(file);
    });

    window.addEventListener('keydown', e => {
        if ((e.ctrlKey || e.metaKey)) {
            if (e.key === 'Enter') {
                e.preventDefault();
                btnSend.click();
            } else if (e.key === '/') {
                e.preventDefault();
                toggleHistory();
            } else if (e.key === 's') {
                e.preventDefault();
                btnExport.click();
            } else if (e.key === 'l') {
                e.preventDefault();
                btnNewChat.click();
            }
        }
    });

    document.getElementById('chat-form').addEventListener('submit', async e => {
        e.preventDefault();
        const text = chatInput.value.trim();
        if (!text) return;
        addMessage('user', text);
        chatInput.style.height = 'auto';
        updateInputStats();
        const assistantWrap = addMessage('assistant', '', {streaming: true});
        const assistantInner = assistantWrap._assistantInner;
        spinner.classList.add('active');
        btnSend.disabled = true;
        try {
            const formData = new FormData(e.target);
            formData.append('system_prompt', sysPromptInput.value);
            const resp = await fetch(urls.chatMessage, {method: 'POST', body: formData});
            if (!resp.body) {
                const txt = await resp.text();
                assistantInner.innerHTML = marked.parse(txt);
                highlightInElement(assistantInner);
                assistantWrap.dataset.content = txt;
            } else {
                const reader = resp.body.getReader();
                const dec = new TextDecoder();
                let markdown = '';
                while (true) {
                    const {value, done} = await reader.read();
                    if (done) break;
                    markdown += dec.decode(value, {stream: true});
                    assistantInner.innerHTML = marked.parse(markdown);
                    highlightInElement(assistantInner);
                    chatOutput.scrollTop = chatOutput.scrollHeight;
                }
                assistantWrap.dataset.content = markdown;
                await fetch(urls.chatFinalize, {
                    method: 'POST',
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({assistant: markdown})
                });
            }
        } catch (err) {
            assistantInner.textContent = `Error: ${err}`;
        } finally {
            spinner.classList.remove('active');
            chatInput.value = '';
            chatInput.style.height = 'auto';
            updateInputStats();
            autoResize();
            saveState();
            newChatFlag.value = 'false';
            btnSend.disabled = false;
            chatInput.focus();
            persistCurrentChat();
        }
    });
})();