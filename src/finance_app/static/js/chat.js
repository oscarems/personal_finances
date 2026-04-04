(() => {
    const THREAD_ID = crypto.randomUUID();
    const chatArea = document.getElementById('chatArea');
    const chatInput = document.getElementById('chatInput');
    const sendBtn = document.getElementById('sendBtn');
    const modelSelect = document.getElementById('modelSelect');
    const modelLabel = document.getElementById('modelLabel');
    const ollamaBanner = document.getElementById('ollamaBanner');

    let isLoading = false;

    // ── Load models ──
    async function loadModels() {
        try {
            const resp = await fetch('/api/chat/modelos');
            const models = await resp.json();
            if (!models.length) {
                ollamaBanner.classList.remove('hidden');
                modelSelect.innerHTML = '<option value="">Sin modelos</option>';
                return;
            }
            modelSelect.innerHTML = models.map(m =>
                `<option value="${m.nombre}">${m.nombre} (${m.tamaño_gb} GB)</option>`
            ).join('');
            modelLabel.textContent = 'Modelo:';
        } catch {
            ollamaBanner.classList.remove('hidden');
            modelSelect.innerHTML = '<option value="">Sin modelos</option>';
        }
    }

    // ── Render helpers ──
    function escapeHtml(str) {
        const d = document.createElement('div');
        d.textContent = str;
        return d.innerHTML;
    }

    function addBubble(content, isUser) {
        // Remove placeholder if present
        const placeholder = chatArea.querySelector('.text-center');
        if (placeholder) placeholder.remove();

        const wrapper = document.createElement('div');
        wrapper.className = `flex ${isUser ? 'justify-end' : 'justify-start'}`;

        const bubble = document.createElement('div');
        bubble.className = isUser
            ? 'max-w-[80%] rounded-2xl rounded-br-md px-4 py-2.5 text-sm bg-primary-600 text-white'
            : 'max-w-[80%] rounded-2xl rounded-bl-md px-4 py-2.5 text-sm bg-secondary-100 text-secondary-800 dark:bg-secondary-700 dark:text-secondary-100';
        bubble.innerHTML = escapeHtml(content);

        wrapper.appendChild(bubble);
        chatArea.appendChild(wrapper);
        chatArea.scrollTop = chatArea.scrollHeight;
        return wrapper;
    }

    function addSqlBlock(parentWrapper, sql) {
        const details = document.createElement('details');
        details.className = 'mt-1 ml-0';

        const summary = document.createElement('summary');
        summary.className = 'text-xs text-secondary-400 cursor-pointer hover:text-secondary-600 select-none';
        summary.textContent = 'Ver SQL generado';

        const code = document.createElement('pre');
        code.className = 'mt-1 text-xs bg-secondary-50 dark:bg-secondary-800 text-secondary-600 dark:text-secondary-300 rounded-lg p-3 overflow-x-auto border border-secondary-200 dark:border-secondary-600';
        code.textContent = sql;

        details.appendChild(summary);
        details.appendChild(code);
        parentWrapper.appendChild(details);
    }

    function addSpinner() {
        const wrapper = document.createElement('div');
        wrapper.id = 'spinner';
        wrapper.className = 'flex justify-start';
        wrapper.innerHTML = `
            <div class="flex items-center gap-2 px-4 py-2.5 rounded-2xl rounded-bl-md bg-secondary-100 dark:bg-secondary-700 text-sm text-secondary-500">
                <span class="animate-spin inline-block w-4 h-4 border-2 border-secondary-300 border-t-primary-500 rounded-full"></span>
                Pensando...
            </div>`;
        chatArea.appendChild(wrapper);
        chatArea.scrollTop = chatArea.scrollHeight;
    }

    function removeSpinner() {
        const s = document.getElementById('spinner');
        if (s) s.remove();
    }

    // ── Send query ──
    async function send() {
        const pregunta = chatInput.value.trim();
        const modelo = modelSelect.value;
        if (!pregunta || !modelo || isLoading) return;

        isLoading = true;
        sendBtn.disabled = true;
        chatInput.value = '';

        addBubble(pregunta, true);
        addSpinner();

        try {
            const resp = await fetch('/api/chat/query', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ pregunta, modelo, thread_id: THREAD_ID }),
            });
            removeSpinner();

            if (!resp.ok) {
                const err = await resp.json();
                addBubble(err.error || 'Error desconocido', false);
                return;
            }

            const data = await resp.json();
            const wrapper = addBubble(data.respuesta, false);
            if (data.sql_generado) {
                addSqlBlock(wrapper, data.sql_generado);
            }
        } catch (err) {
            removeSpinner();
            addBubble('Error de conexión con el servidor.', false);
        } finally {
            isLoading = false;
            sendBtn.disabled = false;
            chatInput.focus();
        }
    }

    // ── Events ──
    sendBtn.addEventListener('click', send);
    chatInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            send();
        }
    });

    loadModels();
})();
