#!/usr/bin/env python3
"""
Microfauna — apply_gcash_patch.py
Applies GCash QR receipt changes to all three templates.

Run from your project root:
    python3 apply_gcash_patch.py

Creates a timestamped .bak backup of each file before modifying it.
"""
import os, re, shutil
from datetime import datetime

# ── Helpers ───────────────────────────────────────────────────────────────────

def backup(path):
    ts  = datetime.now().strftime('%Y%m%d_%H%M%S')
    bak = f"{path}.bak_{ts}"
    shutil.copy2(path, bak)
    return bak

def ok(msg):   print(f"    \u2713  {msg}")
def skip(msg): print(f"    \u2014  {msg}")
def fail(msg): print(f"    \u2717  {msg}")

def str_swap(src, old, new, label):
    """Replace first occurrence; report result."""
    if old in src:
        ok(label)
        return src.replace(old, new, 1), True
    if new in src:
        skip(f"{label} (already applied)")
        return src, False
    fail(f"{label} — pattern not found (check indentation)")
    return src, False

def patch_file(path, fn):
    if not os.path.exists(path):
        print(f"\n  \u2717  {path} not found — skipping\n")
        return
    print(f"\n  Patching {path} …")
    with open(path, encoding='utf-8') as f:
        original = f.read()
    bak = backup(path)
    print(f"    (backup \u2192 {bak})")
    modified = fn(original)
    if modified != original:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(modified)
        ok("File saved.")
    else:
        skip("No changes written (all steps already applied or not found).")


# ── Shared snippet: html2canvas → +receipt.js ─────────────────────────────────

HTML2CANVAS_TAG = (
    '    <script src="https://cdnjs.cloudflare.com/ajax/libs/'
    'html2canvas/1.4.1/html2canvas.min.js"></script>'
)
RECEIPT_JS_TAG = (
    '    <script src="https://cdnjs.cloudflare.com/ajax/libs/'
    'html2canvas/1.4.1/html2canvas.min.js"></script>\n'
    "    <script src=\"{{ url_for('static', filename='receipt.js') }}\"></script>"
)


# ═══════════════════════════════════════════════════════════════════════════════
# dashboard.html
# Adds: receipt.js tag · GCash toggle button · showReceipt() (was missing)
# ═══════════════════════════════════════════════════════════════════════════════

_DASH_OLD_FOOT = (
    '        <div class="r-foot">\n'
    '            <button class="r-btn dark" onclick="closeReceiptModal()">Close</button>\n'
    '            <button class="r-btn" id="downloadReceiptPngBtn">Save PNG</button>\n'
    '            <button class="r-btn" id="shareReceiptBtn">Share / Copy</button>\n'
    '        </div>'
)
_DASH_NEW_FOOT = (
    '        <div class="r-foot">\n'
    '            <button class="r-btn dark" onclick="closeReceiptModal()">Close</button>\n'
    '            <button class="r-btn" id="gcashToggleBtn">GCash</button>\n'
    '            <button class="r-btn" id="downloadReceiptPngBtn">Save PNG</button>\n'
    '            <button class="r-btn" id="shareReceiptBtn">Share / Copy</button>\n'
    '        </div>'
)

# New showReceipt function that replaces the old receipt-helpers block.
# Boundary: from the first "function escapeHTML" (inclusive of its preceding
# section comment) up to — but NOT including — "function closeReceiptModal".
_DASH_NEW_RECEIPT_SECTION = '''\
        // ── Receipt ───────────────────────────────────────────────
        async function showReceipt(saleId) {
            try {
                const res  = await fetch('/sales/' + saleId + '/receipt');
                const data = await res.json();
                if (data.error) { alert(data.error); return; }

                MFReceipt.renderInModal(document.getElementById('receiptContent'), data);

                const toggleBtn = document.getElementById('gcashToggleBtn');
                toggleBtn.textContent = MFReceipt.isGcashOn() ? 'Hide GCash' : 'Show GCash';
                toggleBtn.onclick = () => {
                    const isOn = MFReceipt.toggleGcash();
                    toggleBtn.textContent = isOn ? 'Hide GCash' : 'Show GCash';
                    MFReceipt.renderInModal(document.getElementById('receiptContent'), data);
                };

                document.getElementById('downloadReceiptPngBtn').onclick = () =>
                    MFReceipt.captureAsPng('download', data.sale_id, data.customer_name, data);
                document.getElementById('shareReceiptBtn').onclick = () =>
                    MFReceipt.captureAsPng('share', data.sale_id, data.customer_name, data);

                document.getElementById('receiptModal').style.display = 'flex';
            } catch(e) {
                alert('Could not load receipt: ' + e.message);
            }
        }

'''

def patch_dashboard(src):
    # 1. receipt.js script tag
    src, _ = str_swap(src, HTML2CANVAS_TAG, RECEIPT_JS_TAG, 'Add receipt.js <script> tag')

    # 2. GCash toggle button
    src, _ = str_swap(src, _DASH_OLD_FOOT, _DASH_NEW_FOOT, 'Add GCash toggle button to receipt footer')

    # 3. Replace receipt helpers block with showReceipt().
    #    Start anchor: the comment line just above "function escapeHTML"
    #    (we search backwards from escapeHTML to find it).
    #    End anchor:   "\n        function closeReceiptModal" (kept).
    esc_pos = src.find('        function escapeHTML(str) {')
    if esc_pos == -1:
        fail('Replace receipt helpers — function escapeHTML not found (may already be patched)')
        return src

    # Walk back to find the start of the section comment
    section_start = src.rfind('\n        // ', 0, esc_pos)
    if section_start == -1:
        fail('Replace receipt helpers — could not find section comment')
        return src
    section_start += 1  # skip the leading \n

    end_anchor = '\n        function closeReceiptModal'
    section_end = src.find(end_anchor, esc_pos)
    if section_end == -1:
        fail('Replace receipt helpers — closeReceiptModal boundary not found')
        return src

    old_block = src[section_start:section_end]
    src = src[:section_start] + _DASH_NEW_RECEIPT_SECTION + src[section_end:]
    ok('Replaced old receipt helpers + added showReceipt()')
    return src


# ═══════════════════════════════════════════════════════════════════════════════
# view_sales.html
# Adds: receipt.js tag · GCash toggle button
# Updates: showReceipt() · downloadReceiptPng()
# ═══════════════════════════════════════════════════════════════════════════════

_VS_OLD_FOOT_ANCHOR = (
    '            <div class="r-foot">\n'
    '                <button class="r-btn dark" onclick="closeReceiptModal()">Close</button>\n'
    '                <button class="r-btn" onclick="location.href='
)
_VS_NEW_FOOT_ANCHOR = (
    '            <div class="r-foot">\n'
    '                <button class="r-btn dark" onclick="closeReceiptModal()">Close</button>\n'
    '                <button class="r-btn" id="gcashToggleBtn">GCash</button>\n'
    '                <button class="r-btn" onclick="location.href='
)

_VS_NEW_SHOW_RECEIPT = '''\
        // ── Show receipt in modal ──────────────────────────────────
        async function showReceipt(saleId) {
            try {
                const res  = await fetch('/sales/' + saleId + '/receipt');
                const data = await res.json();
                if (data.error) { alert(data.error); return; }
                _currentReceiptData = data;
                currentSaleId       = saleId;
                currentCustomerName = data.customer_name;

                MFReceipt.renderInModal(document.getElementById('receiptContent'), data);

                const toggleBtn = document.getElementById('gcashToggleBtn');
                toggleBtn.textContent = MFReceipt.isGcashOn() ? 'Hide GCash' : 'Show GCash';
                toggleBtn.onclick = () => {
                    const isOn = MFReceipt.toggleGcash();
                    toggleBtn.textContent = isOn ? 'Hide GCash' : 'Show GCash';
                    MFReceipt.renderInModal(document.getElementById('receiptContent'), data);
                };

                document.getElementById('downloadPngBtn').onclick = () =>
                    MFReceipt.captureAsPng('download', saleId, data.customer_name, data);
                document.getElementById('copyReceiptBtn').onclick = () =>
                    MFReceipt.captureAsPng('share', saleId, data.customer_name, data);

                document.getElementById('receiptModal').style.display = 'flex';
            } catch(e) {
                alert('Could not load receipt: ' + e.message);
            }
        }'''

_VS_OLD_DL_LINE = "                captureReceiptPng('download', saleId, customerName, data);"
_VS_NEW_DL_LINE = "                MFReceipt.captureAsPng('download', saleId, customerName, data);"

def patch_view_sales(src):
    # 1. receipt.js script tag
    src, _ = str_swap(src, HTML2CANVAS_TAG, RECEIPT_JS_TAG, 'Add receipt.js <script> tag')

    # 2. GCash toggle button
    src, _ = str_swap(src, _VS_OLD_FOOT_ANCHOR, _VS_NEW_FOOT_ANCHOR, 'Add GCash toggle button to receipt footer')

    # 3. Replace showReceipt() function.
    #    Start: "async function showReceipt(saleId) {"
    #    End:   the blank line just before "// ── Direct PNG download"
    fn_start = src.find('        async function showReceipt(saleId) {')
    if fn_start == -1:
        fail('Replace showReceipt() — function declaration not found')
    else:
        # Walk back one line to include the preceding comment
        comment_start = src.rfind('\n        // ', 0, fn_start)
        if comment_start != -1:
            fn_start = comment_start + 1

        # End: stop at the blank line before the next section comment
        end_anchor = '\n\n        // \u2500\u2500 Direct PNG download'
        fn_end = src.find(end_anchor, fn_start)
        if fn_end == -1:
            fail('Replace showReceipt() — end boundary not found')
        else:
            src = src[:fn_start] + _VS_NEW_SHOW_RECEIPT + src[fn_end:]
            ok('Replaced showReceipt() with MFReceipt version')

    # 4. downloadReceiptPng: one-line swap
    src, _ = str_swap(src, _VS_OLD_DL_LINE, _VS_NEW_DL_LINE,
                      'Updated downloadReceiptPng() to use MFReceipt')
    return src


# ═══════════════════════════════════════════════════════════════════════════════
# add_sale.html
# Adds: receipt.js tag · GCash toggle button
# Updates: displayReceipt()
# ═══════════════════════════════════════════════════════════════════════════════

_AS_OLD_FOOT = (
    '                <button class="rbtn dark" onclick="closeReceiptModal()">Close</button>\n'
    '                <button class="rbtn" id="goDashBtn">'
)
_AS_NEW_FOOT = (
    '                <button class="rbtn dark" onclick="closeReceiptModal()">Close</button>\n'
    '                <button class="rbtn" id="gcashToggleBtn">GCash</button>\n'
    '                <button class="rbtn" id="goDashBtn">'
)

_AS_NEW_DISPLAY_RECEIPT = '''\
    // ── Render receipt into an isolated iframe (zero CSS bleed) ───
    function displayReceipt(data) {
        MFReceipt.renderInModal(document.getElementById('receiptContent'), data);

        const toggleBtn = document.getElementById('gcashToggleBtn');
        toggleBtn.textContent = MFReceipt.isGcashOn() ? 'Hide GCash' : 'Show GCash';
        toggleBtn.onclick = () => {
            const isOn = MFReceipt.toggleGcash();
            toggleBtn.textContent = isOn ? 'Hide GCash' : 'Show GCash';
            MFReceipt.renderInModal(document.getElementById('receiptContent'), data);
        };

        document.getElementById('receiptModal').style.display = 'block';
        document.getElementById('goDashBtn').onclick      = () => { window.location.href = "{{ url_for('dashboard') }}"; };
        document.getElementById('downloadPngBtn').onclick = () => MFReceipt.captureAsPng('download', data.sale_id, data.customer_name, data);
        document.getElementById('copyReceiptBtn').onclick = () => MFReceipt.captureAsPng('copy',     data.sale_id, data.customer_name, data);
    }'''

def patch_add_sale(src):
    # 1. receipt.js script tag
    src, _ = str_swap(src, HTML2CANVAS_TAG, RECEIPT_JS_TAG, 'Add receipt.js <script> tag')

    # 2. GCash toggle button  (add_sale uses .rbtn not .r-btn)
    src, _ = str_swap(src, _AS_OLD_FOOT, _AS_NEW_FOOT, 'Add GCash toggle button to receipt footer')

    # 3. Replace displayReceipt() function.
    #    Start: "function displayReceipt(data) {"
    #    End:   blank line before "// ── PNG capture via hidden iframe"
    fn_start = src.find('    function displayReceipt(data) {')
    if fn_start == -1:
        fail('Replace displayReceipt() — function declaration not found')
    else:
        # Include preceding comment
        comment_start = src.rfind('\n    // ', 0, fn_start)
        if comment_start != -1:
            fn_start = comment_start + 1

        end_anchor = '\n\n    // \u2500\u2500 PNG capture via hidden iframe'
        fn_end = src.find(end_anchor, fn_start)
        if fn_end == -1:
            fail('Replace displayReceipt() — end boundary not found')
        else:
            src = src[:fn_start] + _AS_NEW_DISPLAY_RECEIPT + src[fn_end:]
            ok('Replaced displayReceipt() with MFReceipt version')

    return src


# ═══════════════════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    print('Microfauna — GCash receipt patch\n')
    patch_file('templates/dashboard.html', patch_dashboard)
    patch_file('templates/view_sales.html', patch_view_sales)
    patch_file('templates/add_sale.html',   patch_add_sale)
    print('\n\nAll done! Next steps:')
    print('  1.  cp static/receipt.js   → your project\'s static/ folder')
    print('  2.  Edit static/receipt.js  → set GCASH_NUMBER to your number')
    print('  3.  Save your GCash QR screenshot as  static/gcash-qr.png')
    print('  4.  Restart Flask and open any receipt to test the toggle')
    print('\n  Backups were created as  <filename>.bak_<timestamp>  — safe to delete later.')
