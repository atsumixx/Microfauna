// ── Apply theme immediately (before paint, no flash) ──────────────
(function () {
    var t = localStorage.getItem('theme') || 'dark';
    document.documentElement.setAttribute('data-theme', t);
})();

// ── Toggle ─────────────────────────────────────────────────────────
function toggleTheme() {
    var html     = document.documentElement;
    var current  = html.getAttribute('data-theme');
    var next     = current === 'light' ? 'dark' : 'light';
    html.setAttribute('data-theme', next);
    localStorage.setItem('theme', next);
}
