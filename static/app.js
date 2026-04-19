const reportContent = document.getElementById("report-content");
const datePicker = document.getElementById("date-picker");
const reportMeta = document.getElementById("report-meta");

let sparklineData = null;

function esc(s) {
    if (!s) return "";
    const d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
}

const MARKET_LABELS = {
    "Nordic": "Norden",
    "Europe": "Europa",
    "US": "USA",
};

// --- Sparkline SVG ---

function buildSparklineSVG(prices) {
    if (!prices || prices.length < 2) return "";
    const w = 80, h = 24, pad = 1;
    const min = Math.min(...prices);
    const max = Math.max(...prices);
    const range = max - min || 1;

    const points = prices.map((p, i) => {
        const x = pad + (i / (prices.length - 1)) * (w - 2 * pad);
        const y = pad + (1 - (p - min) / range) * (h - 2 * pad);
        return `${x.toFixed(1)},${y.toFixed(1)}`;
    });

    const trend = prices[prices.length - 1] >= prices[0];
    const color = trend ? "var(--green)" : "var(--red)";

    return `<svg class="sparkline" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">` +
        `<polyline fill="none" stroke="${color}" stroke-width="1.5" points="${points.join(" ")}"/>` +
        `</svg>`;
}

// --- Legacy markdown rendering (for old reports) ---

function renderMarkdown(md) {
    md = md.replace(/\u{1F7E2}\s*/gu, "").replace(/\u{1F534}\s*/gu, "");
    let html = md
        .replace(/^### (.+)$/gm, "<h2>$1</h2>")
        .replace(/^## (.+)$/gm, "<h2>$1</h2>")
        .replace(/^# (.+)$/gm, "<h1>$1</h1>")
        .replace(/^---$/gm, "<hr>")
        .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
        .replace(/\((\+\d+\.?\d*%)\)/g, '<span class="pct-up">(+$1)</span>')
        .replace(/\(([−-]\d+\.?\d*%)\)/g, '<span class="pct-down">($1)</span>');
    html = html.split(/\n{2,}/).map(block => {
        block = block.trim();
        if (!block || /^<[h]/.test(block) || block === "<hr>") return block;
        return `<p>${block.replace(/\n/g, "<br>")}</p>`;
    }).join("\n");
    return html;
}

// --- Report rendering ---

function renderReport(data) {
    const report = data.report || data;

    // Legacy: old markdown-based reports stored as "content" string
    if (data.content && typeof data.content === "string") {
        reportContent.innerHTML = renderMarkdown(data.content);
        return;
    }

    let html = "";

    // Date header
    html += `<h1>${data.date}</h1>`;

    // Summary
    if (report.summary) {
        html += `<p class="summary">${report.summary}</p>`;
    }

    // Group movers by market
    const groups = {};
    for (const m of report.movers || []) {
        const market = m.market || "Other";
        if (!groups[market]) groups[market] = [];
        groups[market].push(m);
    }

    // Render in order: Nordic, Europe, US
    for (const market of ["Nordic", "Europe", "US"]) {
        const movers = groups[market];
        if (!movers || movers.length === 0) continue;

        const label = MARKET_LABELS[market] || market;
        html += `<h2>${label}</h2>`;

        for (const m of movers) {
            const pct = m.change_pct;
            const pctClass = pct >= 0 ? "pct-up" : "pct-down";
            const pctStr = pct >= 0 ? `+${pct}%` : `${pct}%`;
            const tag = m.confirmed
                ? `<span class="tag tag-confirmed">Bekreftet</span>`
                : `<span class="tag tag-likely">Sannsynlig</span>`;

            let spark = "";
            if (sparklineData && sparklineData[m.ticker]) {
                spark = `<div class="sparkline-row">${buildSparklineSVG(sparklineData[m.ticker])}<span class="sparkline-label">3 mnd</span></div>`;
            }

            const source = m.source ? `<span class="source">${esc(m.source)}</span>` : "";

            html += `<div class="stock-entry">
                <div class="stock-header">
                    <strong>${esc(m.name)}</strong>
                    <span class="${pctClass}">${pctStr}</span>
                </div>
                <p class="explanation">${tag} ${esc(m.explanation)} ${source}</p>
                ${spark}
            </div>`;
        }
    }

    reportContent.innerHTML = html;
}

// --- API calls ---

async function fetchSparklines() {
    try {
        const res = await fetch("/api/sparklines");
        if (res.ok) sparklineData = await res.json();
    } catch (e) {
        console.error("Failed to fetch sparklines:", e);
    }
}

async function fetchLatestReport() {
    try {
        const res = await fetch("/api/report");
        if (res.status === 404) {
            reportContent.innerHTML = '<div class="loading">Ingen rapporter enn\u00e5.</div>';
            return;
        }
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        showReport(data);
    } catch (e) {
        reportContent.innerHTML = `<div class="error">Kunne ikke hente rapport: ${e.message}</div>`;
    }
}

async function fetchReportByDate(date) {
    try {
        reportContent.innerHTML = '<div class="loading">Henter rapport...</div>';
        const res = await fetch(`/api/report/${date}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        showReport(data);
    } catch (e) {
        reportContent.innerHTML = `<div class="error">Kunne ikke hente rapport: ${e.message}</div>`;
    }
}

async function fetchReportHistory() {
    try {
        const res = await fetch("/api/reports");
        if (!res.ok) return;
        const reports = await res.json();
        datePicker.innerHTML = "";
        if (reports.length === 0) {
            datePicker.innerHTML = '<option value="">Ingen rapporter</option>';
            return;
        }
        reports.forEach((r, i) => {
            const opt = document.createElement("option");
            opt.value = r.date;
            opt.textContent = r.date;
            if (i === 0) opt.selected = true;
            datePicker.appendChild(opt);
        });
    } catch (e) {
        console.error("Failed to fetch history:", e);
    }
}

function showReport(data) {
    renderReport(data);
    if (data.created_at) {
        reportMeta.textContent = `Generert ${new Date(data.created_at).toLocaleString("no-NO")}`;
    } else {
        reportMeta.textContent = "";
    }
    if (datePicker.value !== data.date) {
        datePicker.value = data.date;
    }
}

// --- Date picker ---

datePicker.addEventListener("change", () => {
    if (datePicker.value) {
        fetchReportByDate(datePicker.value);
    }
});

// --- Push notifications ---

async function initPush() {
    // Check if running inside Capacitor (native app)
    if (window.Capacitor && window.Capacitor.isNativePlatform()) {
        initNativePush();
        return;
    }

    // Web Push fallback (for browser access)
    if (!("serviceWorker" in navigator) || !("PushManager" in window)) return;

    try {
        const reg = await navigator.serviceWorker.ready;
        let sub = await reg.pushManager.getSubscription();

        if (!sub) {
            const res = await fetch("/api/push/vapid-key");
            if (!res.ok) return;
            const { publicKey } = await res.json();

            sub = await reg.pushManager.subscribe({
                userVisibleOnly: true,
                applicationServerKey: urlBase64ToUint8Array(publicKey),
            });
        }

        await fetch("/api/push/subscribe", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(sub.toJSON()),
        });
    } catch (e) {
        console.error("Web push setup failed:", e);
    }
}

async function initNativePush() {
    try {
        const { PushNotifications } = await import("https://esm.sh/@capacitor/push-notifications");

        const permission = await PushNotifications.requestPermissions();
        if (permission.receive !== "granted") return;

        await PushNotifications.register();

        PushNotifications.addListener("registration", async (token) => {
            console.log("APNs token:", token.value);
            await fetch("/api/push/subscribe", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ endpoint: "apns", token: token.value }),
            });
        });

        PushNotifications.addListener("registrationError", (err) => {
            console.error("Push registration failed:", err);
        });
    } catch (e) {
        console.error("Native push setup failed:", e);
    }
}

function urlBase64ToUint8Array(base64String) {
    const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
    const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
    const raw = atob(base64);
    const arr = new Uint8Array(raw.length);
    for (let i = 0; i < raw.length; i++) arr[i] = raw.charCodeAt(i);
    return arr;
}

// --- Sparkline toggle ---

const sparklineToggle = document.getElementById("sparkline-toggle");

if (localStorage.getItem("hideSparklines") === "true") {
    document.body.classList.add("hide-sparklines");
} else {
    sparklineToggle.classList.add("active");
}

sparklineToggle.addEventListener("click", () => {
    document.body.classList.toggle("hide-sparklines");
    sparklineToggle.classList.toggle("active");
    localStorage.setItem("hideSparklines", document.body.classList.contains("hide-sparklines"));
});

// --- Service Worker ---

if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js");
}

// --- Init ---

async function init() {
    await fetchSparklines();
    await Promise.all([fetchLatestReport(), fetchReportHistory()]);
    initPush();
}

init();
