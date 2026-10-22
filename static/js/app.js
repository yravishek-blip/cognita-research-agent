/**
 * Cognita Deep Research Engine - Client Orchestration Script
 */

let activeWebSocket = null;
let currentReportData = null;

document.addEventListener("DOMContentLoaded", () => {
    checkEngineStatus();
    setupEventListeners();
    loadSavedSettings();
});

// =========================================================================
// SETUP & EVENT LISTENERS
// =========================================================================

function setupEventListeners() {
    const startBtn = document.getElementById("startResearchBtn");
    const queryInput = document.getElementById("queryInput");
    const chips = document.querySelectorAll(".chip");
    const newResearchBtn = document.getElementById("newResearchBtn");
    const copyMarkdownBtn = document.getElementById("copyMarkdownBtn");
    const downloadMdBtn = document.getElementById("downloadMdBtn");
    
    // Modal elements
    const openSettingsBtn = document.getElementById("openSettingsBtn");
    const closeSettingsBtn = document.getElementById("closeSettingsBtn");
    const settingsModal = document.getElementById("settingsModal");
    const saveSettingsBtn = document.getElementById("saveSettingsBtn");

    startBtn.addEventListener("click", initiateResearch);
    queryInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            initiateResearch();
        }
    });

    chips.forEach(chip => {
        chip.addEventListener("click", () => {
            queryInput.value = chip.getAttribute("data-query");
            queryInput.focus();
        });
    });

    if (newResearchBtn) {
        newResearchBtn.addEventListener("click", resetToHero);
    }

    if (copyMarkdownBtn) {
        copyMarkdownBtn.addEventListener("click", copyReportMarkdown);
    }

    if (downloadMdBtn) {
        downloadMdBtn.addEventListener("click", downloadReportMarkdown);
    }

    // Settings Modal handlers
    openSettingsBtn.addEventListener("click", () => settingsModal.style.display = "flex");
    closeSettingsBtn.addEventListener("click", () => settingsModal.style.display = "none");
    saveSettingsBtn.addEventListener("click", saveSettings);
}

async function checkEngineStatus() {
    const badgeText = document.getElementById("activeEngineText");
    try {
        const res = await fetch("/api/providers");
        if (res.ok) {
            const data = await res.json();
            const providerNames = {
                "gemini": "Gemini 2.5 Flash",
                "openai": "GPT-4o",
                "groq": "Groq Llama-3.3",
                "ollama": "Local Ollama",
                "local": "Offline NLP Engine"
            };
            const activeName = providerNames[data.active_default] || data.active_default;
            badgeText.textContent = `Engine: ${activeName}`;
        }
    } catch (e) {
        badgeText.textContent = "Engine: Active";
    }
}

// =========================================================================
// DEEP RESEARCH WEBSOCKET ORCHESTRATION
// =========================================================================

function initiateResearch() {
    const query = document.getElementById("queryInput").value.trim();
    if (!query) {
        alert("Please enter a research topic or question.");
        return;
    }

    const depth = document.getElementById("depthSelect").value;
    const provider = document.getElementById("providerSelect").value;

    let breadth = 4;
    if (depth === "quick") breadth = 2;
    if (depth === "exhaustive") breadth = 6;

    // Switch views: Hide Hero & Report, Show Telemetry
    document.getElementById("researchHero").style.display = "none";
    document.getElementById("reportSection").style.display = "none";
    document.getElementById("telemetrySection").style.display = "block";

    resetTelemetry();
    appendLog(`[INIT] Connecting to Cognita Research Agent...`, "info");

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/ws/research`;

    if (activeWebSocket) {
        activeWebSocket.close();
    }

    activeWebSocket = new WebSocket(wsUrl);

    activeWebSocket.onopen = () => {
        appendLog(`[CONNECTED] Agent session initialized. Transmitting research parameters...`, "info");
        
        // Grab optional custom keys from storage
        const savedKeys = JSON.parse(localStorage.getItem("cognita_keys") || "{}");
        let activeApiKey = null;
        if (provider === "gemini" && savedKeys.gemini) activeApiKey = savedKeys.gemini;
        if (provider === "openai" && savedKeys.openai) activeApiKey = savedKeys.openai;
        if (provider === "groq" && savedKeys.groq) activeApiKey = savedKeys.groq;

        const payload = {
            query: query,
            depth: depth,
            breadth: breadth,
            provider: provider,
            api_key: activeApiKey
        };

        activeWebSocket.send(JSON.stringify(payload));
    };

    activeWebSocket.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            handleAgentEvent(data);
        } catch (err) {
            console.error("Error parsing WebSocket event:", err);
        }
    };

    activeWebSocket.onerror = (err) => {
        appendLog(`[ERROR] WebSocket error encountered.`, "warn");
    };

    activeWebSocket.onclose = () => {
        appendLog(`[SESSION] Research session ended.`, "info");
    };
}

function handleAgentEvent(event) {
    if (event.step === "final_report") {
        currentReportData = event.report;
        renderFinalReport(event.report);
        return;
    }

    // Update Progress Bar & Phase Title
    const progress = event.progress || 0;
    document.getElementById("progressBarFill").style.width = `${progress}%`;
    document.getElementById("progressPercent").textContent = `${progress}%`;
    document.getElementById("telemetryPhaseTitle").textContent = event.phase_title || "Investigating...";
    document.getElementById("telemetryStepTag").textContent = event.step.toUpperCase();

    // Update pipeline nodes
    updatePipelineBreadcrumbs(event.step);

    // Append thought to terminal
    appendLog(`[${event.step.toUpperCase()}] ${event.message}`, event.step === "error" ? "warn" : "info");

    // Handle incoming sub-queries data
    if (event.data && event.data.sub_queries) {
        renderSubqueries(event.data.sub_queries);
    }

    // Handle scraped documents data
    if (event.data && event.data.documents) {
        renderScrapedSources(event.data.documents);
    }
}

function updatePipelineBreadcrumbs(step) {
    const nodes = {
        planning: document.getElementById("nodePlanning"),
        searching: document.getElementById("nodeSearching"),
        scraping: document.getElementById("nodeScraping"),
        analyzing: document.getElementById("nodeAnalyzing"),
        completed: document.getElementById("nodeCompleted"),
    };

    const order = ["planning", "searching", "scraping", "analyzing", "completed"];
    const currentIndex = order.indexOf(step);

    if (currentIndex >= 0) {
        order.forEach((s, idx) => {
            const node = nodes[s];
            if (!node) return;
            if (idx < currentIndex) {
                node.className = "pipeline-node completed";
            } else if (idx === currentIndex) {
                node.className = "pipeline-node active";
            } else {
                node.className = "pipeline-node";
            }
        });
    }
}

function renderSubqueries(subqueries) {
    const container = document.getElementById("subqueriesContainer");
    container.innerHTML = "";
    subqueries.forEach((sq, i) => {
        const div = document.createElement("div");
        div.className = "subquery-card";
        div.innerHTML = `<span class="subquery-num">#${i + 1}</span> <span class="subquery-text">${escapeHtml(sq.query)}</span>`;
        container.appendChild(div);
    });
}

function renderScrapedSources(docs) {
    const feed = document.getElementById("scrapedSourcesFeed");
    docs.forEach(doc => {
        const badge = document.createElement("span");
        badge.className = "source-badge";
        const auth = Math.round(doc.credibility * 100);
        badge.textContent = `${doc.domain} (${auth}%)`;
        feed.appendChild(badge);
    });
}

function renderFinalReport(report) {
    // Hide telemetry and show Report
    document.getElementById("telemetrySection").style.display = "none";
    document.getElementById("reportSection").style.display = "block";

    // Update badges
    document.getElementById("reportDateBadge").textContent = report.timestamp || "Just now";
    document.getElementById("reportWordsBadge").textContent = `${report.total_words.toLocaleString()} Words`;
    document.getElementById("reportSourcesBadge").textContent = `${report.sources.length} Sources Cited`;

    // Render Markdown into HTML
    const reportContainer = document.getElementById("reportContent");
    reportContainer.innerHTML = parseMarkdown(report.markdown_report);

    // Scroll to top
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

// =========================================================================
// UTILITIES: MARKDOWN PARSER & ACTIONS
// =========================================================================

function parseMarkdown(md) {
    if (!md) return "";

    let html = md;

    // Escape raw tags to prevent injection
    html = html.replace(/&/g, '&amp;')
               .replace(/</g, '&lt;')
               .replace(/>/g, '&gt;');

    // Tables
    html = html.replace(/\n\|(.+)\|\n\|[-:| ]+\|\n((?:\|.+\|\n?)+)/g, (match, header, rows) => {
        const ths = header.split('|').map(h => h.trim()).filter(h => h).map(h => `<th>${h}</th>`).join('');
        const trs = rows.trim().split('\n').map(row => {
            const tds = row.split('|').map(d => d.trim()).filter(d => d).map(d => `<td>${d}</td>`).join('');
            return `<tr>${tds}</tr>`;
        }).join('');
        return `<table><thead><tr>${ths}</tr></thead><tbody>${trs}</tbody></table>`;
    });

    // Headers
    html = html.replace(/^### (.*$)/gim, '<h3>$1</h3>');
    html = html.replace(/^## (.*$)/gim, '<h2>$1</h2>');
    html = html.replace(/^# (.*$)/gim, '<h1>$1</h1>');

    // Bold & Italics
    html = html.replace(/\*\*(.*?)\*\*/gim, '<strong>$1</strong>');
    html = html.replace(/\*(.*?)\*/gim, '<em>$1</em>');

    // Links [text](url)
    html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');

    // Inline citations [1], [2] styling
    html = html.replace(/\[(\d+)\]/g, '<span class="citation-tag" title="Source reference">[$1]</span>');

    // Lists
    html = html.replace(/^\s*-\s+(.*$)/gim, '<li>$1</li>');
    html = html.replace(/(<li>.*<\/li>)/gim, '<ul>$1</ul>');
    html = html.replace(/<\/ul>\s*<ul>/gim, '');

    // Paragraphs
    html = html.replace(/\n\s*\n/gim, '</p><p>');
    html = `<p>${html}</p>`;

    // Clean up empty tags
    html = html.replace(/<p>\s*<\/p>/gim, '');
    html = html.replace(/<p>\s*(<h[1-3]>)/gim, '$1');
    html = html.replace(/(<\/h[1-3]>)\s*<\/p>/gim, '$1');
    html = html.replace(/<p>\s*(<table>)/gim, '$1');
    html = html.replace(/(<\/table>)\s*<\/p>/gim, '$1');

    return html;
}

function copyReportMarkdown() {
    if (!currentReportData) return;
    navigator.clipboard.writeText(currentReportData.markdown_report).then(() => {
        const btn = document.getElementById("copyMarkdownBtn");
        const orig = btn.textContent;
        btn.textContent = "✅ Copied!";
        setTimeout(() => btn.textContent = orig, 2000);
    });
}

function downloadReportMarkdown() {
    if (!currentReportData) return;
    const blob = new Blob([currentReportData.markdown_report], { type: "text/markdown;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `Cognita_Briefing_${currentReportData.id || "report"}.md`;
    link.click();
    URL.revokeObjectURL(url);
}

function resetToHero() {
    document.getElementById("reportSection").style.display = "none";
    document.getElementById("telemetrySection").style.display = "none";
    document.getElementById("researchHero").style.display = "block";
    document.getElementById("queryInput").value = "";
    document.getElementById("queryInput").focus();
}

function resetTelemetry() {
    document.getElementById("progressBarFill").style.width = "5%";
    document.getElementById("progressPercent").textContent = "0%";
    document.getElementById("terminalLogs").innerHTML = "";
    document.getElementById("subqueriesContainer").innerHTML = '<div class="empty-state-notice">Planning research vectors...</div>';
    document.getElementById("scrapedSourcesFeed").innerHTML = "";
}

function appendLog(message, type = "normal") {
    const logs = document.getElementById("terminalLogs");
    const line = document.createElement("div");
    line.className = `log-line ${type}`;
    line.textContent = message;
    logs.appendChild(line);
    logs.scrollTop = logs.scrollHeight;
}

function saveSettings() {
    const gemini = document.getElementById("geminiKeyInput").value.trim();
    const openai = document.getElementById("openaiKeyInput").value.trim();
    const groq = document.getElementById("groqKeyInput").value.trim();

    localStorage.setItem("cognita_keys", JSON.stringify({ gemini, openai, groq }));
    document.getElementById("settingsModal").style.display = "none";
    checkEngineStatus();
    alert("API Keys saved in browser session!");
}

function loadSavedSettings() {
    const keys = JSON.parse(localStorage.getItem("cognita_keys") || "{}");
    if (keys.gemini) document.getElementById("geminiKeyInput").value = keys.gemini;
    if (keys.openai) document.getElementById("openaiKeyInput").value = keys.openai;
    if (keys.groq) document.getElementById("groqKeyInput").value = keys.groq;
}

function escapeHtml(str) {
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
