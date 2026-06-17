/**
 * MICROFAUNA — receipt.js
 * Centralised receipt HTML builder + GCash QR toggle.
 *
 * SETUP:
 *   1. Place your GCash QR screenshot at  static/gcash-qr.png
 *   2. That's it — no phone number config needed.
 *
 * Exposes: window.MFReceipt
 */
(function (global) {
    'use strict';

    var GCASH_BLUE = '#007AE2';

    // GCash toggle state — default ON
    var _on = localStorage.getItem('mf_gcash') !== 'false';

    // ── Preload QR image as base64 (Promise-based so we can await it) ──
    var _qrReady = null;   // resolves to base64 string or null

    function _loadQr() {
        if (_qrReady) return _qrReady;          // already kicked off
        _qrReady = fetch('/static/gcash-qr.png')
            .then(function (r) {
                if (!r.ok) throw new Error('not found');
                return r.blob();
            })
            .then(function (blob) {
                return new Promise(function (resolve) {
                    var rd = new FileReader();
                    rd.onloadend = function () { resolve(rd.result); };
                    rd.readAsDataURL(blob);
                });
            })
            .catch(function () {
                return null;   // file missing — graceful fallback
            });
        return _qrReady;
    }

    // Start loading immediately on script parse
    _loadQr();


    /* ── Utilities ───────────────────────────────────────────────── */
    function esc(s) {
        return String(s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }


    /* ── Build receipt HTML (accepts resolved base64 or null) ─────── */
    function buildHTML(data, qrBase64) {

        /* Item rows */
        var rows = '';
        (data.items || []).forEach(function (item) {
            rows +=
                '<tr>' +
                '<td style="padding:9px 8px;border-bottom:1px dashed #ccc;color:#000;font-size:13px;">' + esc(item.name) + '</td>' +
                '<td style="padding:9px 8px;border-bottom:1px dashed #ccc;text-align:center;color:#000;font-size:13px;">' + item.quantity + '</td>' +
                '<td style="padding:9px 8px;border-bottom:1px dashed #ccc;text-align:right;color:#000;font-size:13px;">&#8369;' + parseFloat(item.price).toFixed(2) + '</td>' +
                '<td style="padding:9px 8px;border-bottom:1px dashed #ccc;text-align:right;color:#000;font-size:13px;font-weight:600;">&#8369;' + parseFloat(item.subtotal).toFixed(2) + '</td>' +
                '</tr>';
        });

        var discountLine = (data.discount > 0)
            ? '<div style="text-align:right;color:#cc0000;font-size:13px;margin-top:6px;">Discount: -&#8369;' +
              parseFloat(data.discount).toFixed(2) + '</div>'
            : '';

        var notesLine = data.notes
            ? '<div style="color:#000;"><b>Notes:</b> ' + esc(data.notes) + '</div>'
            : '';

        /* ── GCash block ─────────────────────────────────────────── */
        var gcashBlock = '';
        if (_on) {
            var qrSection;
            if (qrBase64) {
                qrSection =
                    '<div style="' +
                        'width:168px;height:168px;' +
                        'margin:0 auto 14px;' +
                        'border:3px solid ' + GCASH_BLUE + ';' +
                        'border-radius:8px;overflow:hidden;' +
                        'background:#fff;display:flex;' +
                        'align-items:center;justify-content:center;' +
                    '">' +
                        '<img src="' + qrBase64 + '" ' +
                             'width="162" height="162" ' +
                             'style="display:block;object-fit:contain;" ' +
                             'alt="GCash QR">' +
                    '</div>';
            } else {
                // gcash-qr.png missing — show a placeholder box
                qrSection =
                    '<div style="' +
                        'width:168px;height:168px;' +
                        'margin:0 auto 14px;' +
                        'border:3px dashed ' + GCASH_BLUE + ';' +
                        'border-radius:8px;background:#f0f8ff;' +
                        'display:flex;align-items:center;justify-content:center;' +
                        'font-family:\'Courier New\',monospace;font-size:11px;' +
                        'color:' + GCASH_BLUE + ';text-align:center;padding:10px;' +
                    '">' +
                        'Place gcash&#8209;qr.png<br>in static/' +
                    '</div>';
            }

            gcashBlock =
                '<div style="' +
                    'margin:20px 0 14px;' +
                    'padding:16px 16px 18px;' +
                    'border:2px dashed ' + GCASH_BLUE + ';' +
                    'border-radius:10px;' +
                    'text-align:center;' +
                    'background:#fff;' +
                    'box-sizing:border-box;' +
                '">' +
                    '<div style="color:' + GCASH_BLUE + ';font-weight:700;font-size:10px;' +
                        'letter-spacing:3px;margin-bottom:10px;' +
                        'font-family:\'Courier New\',monospace;">' +
                        '\u2500\u2500 PAYMENT \u2500\u2500' +
                    '</div>' +
                    '<div style="color:' + GCASH_BLUE + ';font-size:13px;font-weight:700;' +
                        'margin-bottom:14px;font-family:\'Courier New\',monospace;' +
                        'letter-spacing:0.5px;">Pay via GCash</div>' +
                    qrSection +
                    '<div style="font-size:12px;color:#555;' +
                        'font-family:\'Courier New\',monospace;letter-spacing:0.5px;">' +
                        'Scan to pay \u00b7 GCash' +
                    '</div>' +
                '</div>';
        }

        return (
            '<!DOCTYPE html><html><head><meta charset="utf-8">' +
            '<style>' +
            'html,body{margin:0;padding:0;background:#fff!important;color:#000!important;}' +
            'body{font-family:"Courier New",Courier,monospace;font-size:13px;line-height:1.6;' +
            'background:#fff!important;color:#000!important;padding:28px 24px;' +
            'box-sizing:border-box;width:480px;}' +
            '*{box-sizing:border-box;}' +
            'table{width:100%;border-collapse:collapse;}' +
            'thead tr{background:#000!important;}' +
            'thead th{color:#fff!important;background:#000!important;}' +
            '@media(prefers-color-scheme:dark){' +
            'html,body{background:#fff!important;color:#000!important;}' +
            'thead tr{background:#000!important;}' +
            'thead th{color:#fff!important;background:#000!important;}}' +
            '</style></head><body>' +

            '<div style="text-align:center;margin-bottom:20px;padding-bottom:16px;border-bottom:2px solid #000;">' +
            '<div style="font-size:22px;font-weight:700;letter-spacing:3px;color:#000;">MICROFAUNA</div>' +
            '<div style="font-size:12px;margin-top:4px;color:#555;letter-spacing:1px;">Sales Receipt</div>' +
            '</div>' +

            '<div style="margin-bottom:16px;font-size:13px;color:#000;line-height:2;">' +
            '<div><b>Receipt #:</b> ' + esc(String(data.receipt_no)) + '</div>' +
            '<div><b>Customer:</b> ' + esc(data.customer_name) + '</div>' +
            '<div><b>Date:</b> ' + esc(data.date) + '</div>' +
            notesLine + '</div>' +

            '<table><thead><tr style="background:#000!important;">' +
            '<th style="padding:9px 8px;text-align:left;color:#fff!important;font-size:11px;letter-spacing:1px;background:#000!important;">ITEM</th>' +
            '<th style="padding:9px 8px;text-align:center;color:#fff!important;font-size:11px;letter-spacing:1px;background:#000!important;">QTY</th>' +
            '<th style="padding:9px 8px;text-align:right;color:#fff!important;font-size:11px;letter-spacing:1px;background:#000!important;">PRICE</th>' +
            '<th style="padding:9px 8px;text-align:right;color:#fff!important;font-size:11px;letter-spacing:1px;background:#000!important;">TOTAL</th>' +
            '</tr></thead><tbody>' + rows + '</tbody></table>' +

            '<div style="margin-top:16px;padding-top:12px;border-top:2px solid #000;">' +
            discountLine +
            '<div style="text-align:right;font-size:18px;font-weight:700;color:#000;margin-top:6px;">' +
            'TOTAL: &#8369;' + parseFloat(data.total).toFixed(2) + '</div>' +
            '</div>' +

            gcashBlock +

            '<div style="margin-top:' + (_on ? '4px' : '22px') + ';padding-top:14px;' +
            'border-top:1px dashed #ccc;text-align:center;font-size:12px;color:#000;line-height:2;">' +
            '<div>Thank you for your purchase!</div><div>Visit us again soon</div>' +
            '</div>' +
            '</body></html>'
        );
    }


    /* ── Render receipt into a scaled iframe inside a modal ──────── */
    function renderInModal(contentEl, data) {
        contentEl.innerHTML = '';

        var wrap = document.createElement('div');
        wrap.style.cssText = 'width:100%;overflow:hidden;background:#fff;';
        contentEl.appendChild(wrap);

        var iframe = document.createElement('iframe');
        iframe.style.cssText =
            'width:480px;border:none;background:#fff;display:block;transform-origin:top left;';
        iframe.scrolling = 'no';
        wrap.appendChild(iframe);

        function doScale(doc) {
            var w = contentEl.offsetWidth || 480;
            var s = Math.min(1, w / 480);
            iframe.style.transform = 'scale(' + s + ')';
            var h = (doc.body && doc.body.scrollHeight) || 500;
            iframe.style.height = h + 'px';
            wrap.style.height   = Math.ceil(h * s) + 'px';
        }

        // Await QR load before rendering so the image is always present
        _loadQr().then(function (qrBase64) {
            var doc = iframe.contentDocument || iframe.contentWindow.document;
            doc.open(); doc.write(buildHTML(data, qrBase64)); doc.close();
            setTimeout(function () { doScale(doc); }, 60);
            setTimeout(function () { doScale(doc); }, 300);
        });
    }


    /* ── Capture receipt as PNG via a hidden off-screen iframe ───── */
    function captureAsPng(action, saleId, customerName, data) {
        var filename = 'receipt_' + saleId + '_' +
                       (customerName || '').replace(/\s+/g, '_') + '.png';
        var isIOS = /iPhone|iPad|iPod/.test(navigator.userAgent);

        // Always await QR so PNG capture gets the image
        _loadQr().then(function (qrBase64) {
            var iframe = document.createElement('iframe');
            iframe.style.cssText =
                'position:fixed;left:-9999px;top:0;width:480px;height:1px;' +
                'border:none;visibility:hidden;';
            document.body.appendChild(iframe);

            var iDoc = iframe.contentDocument || iframe.contentWindow.document;
            iDoc.open(); iDoc.write(buildHTML(data, qrBase64)); iDoc.close();

            setTimeout(async function () {
                iframe.style.height = (iDoc.body.scrollHeight + 56) + 'px';
                var canvas;
                try {
                    canvas = await html2canvas(iDoc.body, {
                        backgroundColor: '#ffffff', scale: 2,
                        useCORS: true, allowTaint: false,
                        logging: false, windowWidth: 480, width: 480
                    });
                } catch (err) {
                    document.body.removeChild(iframe);
                    alert('Could not capture receipt. Please try again.');
                    return;
                }
                document.body.removeChild(iframe);
                var dataUrl = canvas.toDataURL('image/png');

                if (action === 'share' || action === 'copy') {
                    canvas.toBlob(async function (blob) {
                        var file = new File([blob], filename, { type: 'image/png' });
                        if (navigator.canShare && navigator.canShare({ files: [file] })) {
                            try { await navigator.share({ files: [file], title: 'Microfauna Receipt' }); return; }
                            catch (e) { if (e.name === 'AbortError') return; }
                        }
                        if (window.ClipboardItem && navigator.clipboard && navigator.clipboard.write) {
                            try {
                                await navigator.clipboard.write([new ClipboardItem({ 'image/png': blob })]);
                                alert('Receipt image copied! Paste in any chat.');
                                return;
                            } catch (e) { /* fall through */ }
                        }
                        _previewOverlay(dataUrl, filename, blob);
                    }, 'image/png');
                } else {
                    if (!isIOS) {
                        var a = document.createElement('a');
                        a.download = filename; a.href = dataUrl;
                        document.body.appendChild(a); a.click(); document.body.removeChild(a);
                    } else {
                        canvas.toBlob(async function (blob) {
                            var file = new File([blob], filename, { type: 'image/png' });
                            if (navigator.canShare && navigator.canShare({ files: [file] })) {
                                try { await navigator.share({ files: [file], title: 'Microfauna Receipt' }); return; }
                                catch (e) { if (e.name === 'AbortError') return; }
                            }
                            _previewOverlay(dataUrl, filename, blob);
                        }, 'image/png');
                    }
                }
            }, 150);
        });
    }


    /* ── Fallback: full-screen image overlay (long-press hint) ───── */
    function _previewOverlay(dataUrl, filename, blob) {
        var old = document.getElementById('mf-img-preview');
        if (old) old.remove();

        var o = document.createElement('div');
        o.id = 'mf-img-preview';
        o.style.cssText =
            'position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,.92);display:flex;' +
            'flex-direction:column;align-items:center;justify-content:center;' +
            'padding:20px;gap:14px;backdrop-filter:blur(6px);-webkit-backdrop-filter:blur(6px);';

        var img = document.createElement('img');
        img.src = dataUrl; img.alt = 'Receipt';
        img.style.cssText =
            'max-width:100%;max-height:calc(100vh - 160px);border-radius:10px;' +
            'box-shadow:0 8px 32px rgba(0,0,0,.6);object-fit:contain;';

        var hint = document.createElement('p');
        hint.textContent = 'Long-press image to Copy or Save to Photos';
        hint.style.cssText =
            'color:rgba(255,255,255,.6);font-size:12px;font-family:-apple-system,sans-serif;' +
            'margin:0;text-align:center;';

        var row = document.createElement('div');
        row.style.cssText = 'display:flex;gap:10px;justify-content:center;width:100%;max-width:320px;';

        var shareBtn = document.createElement('button');
        shareBtn.textContent = 'Share';
        shareBtn.style.cssText =
            'flex:1;padding:13px;background:#00cc77;color:#fff;border:none;' +
            'border-radius:10px;font-weight:700;font-size:.95rem;cursor:pointer;touch-action:manipulation;';
        shareBtn.onclick = async function () {
            var file = blob ? new File([blob], filename, { type: 'image/png' }) : null;
            if (file && navigator.canShare && navigator.canShare({ files: [file] })) {
                try { await navigator.share({ files: [file], title: 'Microfauna Receipt' }); return; }
                catch (e) { if (e.name === 'AbortError') return; }
            }
            if (window.ClipboardItem && navigator.clipboard && navigator.clipboard.write && blob) {
                try {
                    await navigator.clipboard.write([new ClipboardItem({ 'image/png': blob })]);
                    alert('Copied to clipboard!');
                } catch (e) { alert('Share not available on this browser.'); }
            }
        };

        var closeBtn = document.createElement('button');
        closeBtn.textContent = 'Close';
        closeBtn.style.cssText =
            'flex:1;padding:13px;background:rgba(255,255,255,.1);color:#fff;' +
            'border:1px solid rgba(255,255,255,.2);border-radius:10px;' +
            'font-weight:600;font-size:.95rem;cursor:pointer;touch-action:manipulation;';
        closeBtn.onclick = function () { o.remove(); };
        o.addEventListener('click', function (e) { if (e.target === o) o.remove(); });

        row.appendChild(shareBtn);
        row.appendChild(closeBtn);
        o.appendChild(img); o.appendChild(hint); o.appendChild(row);
        document.body.appendChild(o);
    }


    /* ── Public API ──────────────────────────────────────────────── */
    global.MFReceipt = {
        isGcashOn:    function ()  { return _on; },
        toggleGcash:  function ()  {
            _on = !_on;
            localStorage.setItem('mf_gcash', _on ? 'true' : 'false');
            return _on;
        },
        buildHTML:     buildHTML,
        renderInModal: renderInModal,
        captureAsPng:  captureAsPng,
    };

})(window);