(function () {
    const CONFIG = window.ANON_CONFIG || {};
    const resultPlaceholder = CONFIG.resultPlaceholder || 'Wynik pojawi się tutaj po przetworzeniu...';

    function highlightTags() {
        const container = document.getElementById('result-content');
        if (!container) return;

        let mappings = {};
        const raw = container.getAttribute('data-mappings');
        if (raw) {
            try {
                mappings = JSON.parse(raw);
            } catch (e) {
                console.warn('Failed to parse mappings', e);
            }
        }

        const originalText = container.textContent.trimStart();
        container.innerHTML = originalText.replace(/(\{[A-Z]{2,}[^}]*\})/g, function (match) {
            const value = mappings[match] || match;
            return `<span class="anon-tag" title="${value.replace(/"/g, '&quot;')}">${match.replace(/"/g, '&quot;')}</span>`;
        });
    }

    async function copyTextToClipboard(text, btn) {
        if (navigator.clipboard && window.isSecureContext) {
            try {
                await navigator.clipboard.writeText(text);
                toggleSuccessIcon(btn);
                return;
            } catch (e) {
                console.error('Clipboard API failed', e);
            }
        }
        try {
            const ta = document.createElement("textarea");
            ta.value = text;
            ta.style.position = "fixed";
            ta.style.left = "-9999px";
            document.body.appendChild(ta);
            ta.select();
            const ok = document.execCommand('copy');
            document.body.removeChild(ta);
            if (ok) toggleSuccessIcon(btn);
        } catch (e) {
            console.error(e);
        }
    }

    function toggleSuccessIcon(btn) {
        const original = btn.textContent;
        btn.textContent = '✓';
        setTimeout(() => btn.textContent = original, 2000);
    }

    async function copyResult(btn) {
        const el = document.getElementById('result-content');
        if (!el) return;
        await copyTextToClipboard(el.textContent.trim(), btn);
    }

    async function copyMappings(btn) {
        const el = document.getElementById('result-content');
        if (!el) return;
        const raw = el.getAttribute('data-mappings');
        if (!raw) return console.warn('No mappings data found');

        let mappingsText = '';
        try {
            mappingsText = JSON.stringify(JSON.parse(raw), null, 2);
        } catch (e) {
            mappingsText = raw;
        }
        await copyTextToClipboard(mappingsText, btn);
    }

    function clearText() {
        document.getElementById('input-text').value = '';
        document.getElementById('result-content').innerHTML = `<span style="opacity:0.5; font-style:italic;">${resultPlaceholder}</span>`;
    }

    function syncScroll(source) {
        const targetId = source.id === 'input-text' ? 'result-content' : 'input-text';
        const target = document.getElementById(targetId);
        if (!target) return;
        const sourceMaxScroll = source.scrollHeight - source.clientHeight;
        if (sourceMaxScroll <= 0) {
            target.scrollTop = 0;
            return;
        }
        const scrollPercentage = source.scrollTop / sourceMaxScroll;
        target.scrollTop = scrollPercentage * (target.scrollHeight - target.clientHeight);
    }

    // Expose functions globally for inline onclick attributes
    window.clearText = clearText;
    window.copyResult = copyResult;
    window.copyMappings = copyMappings;

    const inputEl = document.getElementById('input-text');
    const resultEl = document.getElementById('result-content');

    if (inputEl) inputEl.addEventListener('scroll', e => syncScroll(e.target));
    if (resultEl) resultEl.addEventListener('scroll', e => syncScroll(e.target));

    document.body.addEventListener('htmx:afterSwap', e => {
        if (e.detail?.target?.id === 'result-wrapper') {
            highlightTags();
            const newResultEl = document.getElementById('result-content');
            if (newResultEl) newResultEl.addEventListener('scroll', e => syncScroll(e.target));
        }
    });

    const anonForm = document.getElementById('anonymize-form');
    if (anonForm) {
        anonForm.addEventListener('htmx:beforeRequest', () => {
            anonForm.querySelector('button[type="submit"]').disabled = true;
            document.getElementById('input-text').disabled = true;
            const progress = document.getElementById('anon-progress');
            if (progress) progress.classList.add('active');
        });
        anonForm.addEventListener('htmx:afterRequest', () => {
            anonForm.querySelector('button[type="submit"]').disabled = false;
            document.getElementById('input-text').disabled = false;
            const progress = document.getElementById('anon-progress');
            if (progress) progress.classList.remove('active');
        });
    }

    document.addEventListener('DOMContentLoaded', highlightTags);
})();