const reportContent = document.getElementById("report-content");
const datePicker = document.getElementById("date-picker");
const pushToggle = document.getElementById("push-toggle");
const reportMeta = document.getElementById("report-meta");

let sparklineData = null;

// Ticker-to-name mapping (must match PORTFOLIO in main.py)
const TICKER_NAMES = {
    "Amazon": "AMZN", "Berkshire Hathaway B": "BRK-B", "Meta Platforms": "META",
    "Microsoft": "MSFT", "nVent Electric": "NVT", "Royal Caribbean Cruises": "RCL",
    "Rivian Automotive": "RIVN", "Vertiv Holdings": "VRT",
    "L'Or\u00e9al": "OR.PA", "LVMH": "MC.PA", "BMW": "BMW.DE", "Siemens Energy": "ENR.DE",
    "Aker": "AKER.OL", "Gjensidige Forsikring": "GJF.OL",
    "Klaveness Combination Carriers": "KCC.OL", "KID": "KID.OL", "Kitron": "KIT.OL",
    "Komplett": "KOMPL.OL", "Kongsberg Gruppen": "KOG.OL",
    "Nordic Semiconductor": "NOD.OL", "Norsk Hydro": "NHY.OL", "Pareto Bank": "PARB.OL",
    "SalMar": "SALM.OL", "Telenor": "TEL.OL", "Vend Marketplaces": "VEND.OL",
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

// --- Markdown rendering ---

function renderMarkdown(md) {
    // Strip emoji circles (from older reports)
    md = md.replace(/\u{1F7E2}\s*/gu, "").replace(/\u{1F534}\s*/gu, "");

    // Strip leading "- " from stock entry lines (before markdown processing)
    md = md.replace(/^- \*\*/gm, "**");

    let html = md
        // Headers
        .replace(/^### (.+)$/gm, "<h3>$1</h3>")
        .replace(/^## (.+)$/gm, "<h2>$1</h2>")
        .replace(/^# (.+)$/gm, "<h1>$1</h1>")
        // Horizontal rules
        .replace(/^---$/gm, "<hr>")
        // Bold
        .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
        // Italic
        .replace(/\*(.+?)\*/g, "<em>$1</em>")
        // Links
        .replace(/\[(.+?)\]\((.+?)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
        // Unordered lists (only non-stock lines)
        .replace(/^[*-] (.+)$/gm, "<li>$1</li>")
        // Numbered lists
        .replace(/^\d+\. (.+)$/gm, "<li>$1</li>");

    // Color percentage values: (+X.X%) or (-X.X%)
    html = html.replace(
        /\((\+\d+\.?\d*%)\)/g,
        '<span class="pct-up">($1)</span>'
    );
    html = html.replace(
        /\((-\d+\.?\d*%)\)/g,
        '<span class="pct-down">($1)</span>'
    );

    // Inject sparklines below each stock's text block
    // Match stock entries with or without the em-dash separator
    html = html.replace(
        /(<strong>([^<]+)<\/strong>\s*<span class="pct-(?:up|down)">(?:[^<]+)<\/span>)\s*(?:\u2014\s*)?(.*)/g,
        (match, prefix, name, explanation) => {
            const ticker = TICKER_NAMES[name];
            if (!ticker) return match; // Not a stock entry, leave as-is
            let spark = "";
            if (sparklineData && sparklineData[ticker]) {
                spark = `<div class="sparkline-row">${buildSparklineSVG(sparklineData[ticker])}<span class="sparkline-label">3 mnd</span></div>`;
            }
            return `<div class="stock-entry">${prefix}<br>${explanation}${spark}</div>`;
        }
    );

    // Wrap consecutive <li> in <ul>
    html = html.replace(/((?:<li>.*<\/li>\n?)+)/g, "<ul>$1</ul>");

    // Paragraphs: split by double newline
    html = html
        .split(/\n{2,}/)
        .map((block) => {
            block = block.trim();
            if (!block) return "";
            if (/^<[hulo]/.test(block)) return block;
            if (/^<div/.test(block)) return block;
            if (block === "<hr>") return block;
            return `<p>${block.replace(/\n/g, "<br>")}</p>`;
        })
        .join("\n");

    return html;
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
    reportContent.innerHTML = renderMarkdown(data.content);
    reportMeta.textContent = `Generert ${new Date(data.created_at).toLocaleString("no-NO")}`;
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
    if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
        pushToggle.style.display = "none";
        return;
    }

    const reg = await navigator.serviceWorker.ready;
    const sub = await reg.pushManager.getSubscription();
    if (sub) {
        pushToggle.classList.add("active");
    }
}

pushToggle.addEventListener("click", async () => {
    const reg = await navigator.serviceWorker.ready;
    const existing = await reg.pushManager.getSubscription();

    if (existing) {
        await fetch("/api/push/subscribe", {
            method: "DELETE",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ endpoint: existing.endpoint }),
        });
        await existing.unsubscribe();
        pushToggle.classList.remove("active");
        return;
    }

    try {
        const res = await fetch("/api/push/vapid-key");
        if (!res.ok) {
            alert("Push-varsler er ikke konfigurert enn\u00e5.");
            return;
        }
        const { publicKey } = await res.json();

        const sub = await reg.pushManager.subscribe({
            userVisibleOnly: true,
            applicationServerKey: urlBase64ToUint8Array(publicKey),
        });

        await fetch("/api/push/subscribe", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(sub.toJSON()),
        });

        pushToggle.classList.add("active");
    } catch (e) {
        console.error("Push subscription failed:", e);
        alert("Kunne ikke aktivere push-varsler.");
    }
});

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
    // Fetch sparklines and report in parallel
    await fetchSparklines();
    fetchLatestReport();
    fetchReportHistory();
    initPush();
}

init();
