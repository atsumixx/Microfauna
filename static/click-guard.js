/**
 * MICROFAUNA - Global Click Guard
 * Prevents spam-clicking and provides instant visual feedback
 * Apply to ALL buttons, links, and interactive elements
 */

(function() {
    'use strict';

    // Track active operations globally
    const activeOperations = new Set();

    /**
     * Guard a button/link against spam clicks
     * Usage: guardClick(element, asyncFunction)
     */
    window.guardClick = function(element, asyncFn) {
        const key = element.id || element.getAttribute('data-guard-key') || Math.random().toString(36);
        
        // Already running? Ignore
        if (activeOperations.has(key)) {
            return Promise.resolve();
        }

        // Mark as active
        activeOperations.add(key);
        
        // Disable immediately
        const wasDisabled = element.disabled;
        element.disabled = true;
        element.classList.add('is-loading');
        
        // Store original state
        const originalText = element.textContent;
        const originalCursor = element.style.cursor;
        element.style.cursor = 'wait';

        return Promise.resolve()
            .then(() => asyncFn())
            .finally(() => {
                // Re-enable after operation completes
                setTimeout(() => {
                    element.disabled = wasDisabled;
                    element.classList.remove('is-loading');
                    element.style.cursor = originalCursor;
                    element.textContent = originalText;
                    activeOperations.delete(key);
                }, 150); // Small delay prevents double-click on slow networks
            });
    };

    /**
     * Protect navigation links (prevent multiple page loads)
     */
    function protectNavigation() {
        document.addEventListener('click', function(e) {
            const link = e.target.closest('a[href]');
            if (!link) return;

            // Skip external links and # anchors
            const href = link.getAttribute('href');
            if (!href || href.startsWith('#') || href.startsWith('http') || href.startsWith('mailto')) {
                return;
            }

            // Skip if already navigating
            if (link.classList.contains('is-navigating')) {
                e.preventDefault();
                return;
            }

            // Mark as navigating
            link.classList.add('is-navigating');
            link.style.opacity = '0.6';
            link.style.pointerEvents = 'none';

            // Timeout fallback (if navigation fails)
            setTimeout(() => {
                link.classList.remove('is-navigating');
                link.style.opacity = '';
                link.style.pointerEvents = '';
            }, 3000);
        }, true);
    }

    /**
     * Protect form submissions
     */
    function protectForms() {
        document.addEventListener('submit', function(e) {
            const form = e.target;
            const submitBtn = form.querySelector('button[type="submit"], input[type="submit"]');
            
            if (submitBtn && submitBtn.disabled) {
                e.preventDefault();
                return;
            }

            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.classList.add('is-loading');
                
                // For native form submits (not fetch), we let the browser handle it
                // The page will navigate away, so no need to re-enable
            }
        }, true);
    }

    /**
     * Protect action buttons (delete, edit, etc.)
     */
    function protectActionButtons() {
        document.addEventListener('click', function(e) {
            const btn = e.target.closest('button:not([type="submit"])');
            if (!btn || btn.disabled) {
                if (btn && btn.disabled) {
                    e.preventDefault();
                    e.stopPropagation();
                }
                return;
            }

            // For onclick handlers, add a small guard
            if (btn.onclick) {
                const key = btn.id || `btn-${Date.now()}`;
                if (activeOperations.has(key)) {
                    e.preventDefault();
                    e.stopPropagation();
                    return;
                }
                activeOperations.add(key);
                setTimeout(() => activeOperations.delete(key), 500);
            }
        }, true);
    }

    /**
     * Add visual feedback on any click
     */
    function addInstantFeedback() {
        document.addEventListener('mousedown', function(e) {
            const target = e.target.closest('button, a, input[type="submit"]');
            if (target && !target.disabled) {
                target.classList.add('is-pressed');
            }
        }, true);

        document.addEventListener('mouseup', function(e) {
            const target = e.target.closest('button, a, input[type="submit"]');
            if (target) {
                setTimeout(() => target.classList.remove('is-pressed'), 100);
            }
        }, true);
    }

    /**
     * Initialize on DOM ready
     */
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    function init() {
        protectNavigation();
        protectForms();
        protectActionButtons();
        addInstantFeedback();
    }

    // Expose utilities globally
    window.ClickGuard = {
        protect: guardClick,
        isActive: (key) => activeOperations.has(key),
        clear: () => activeOperations.clear()
    };
})();
