"""JavaScript snippets that Playwright evaluates inside the browser context.

Each constant is a self-contained JS expression that takes the
caller-supplied arguments and returns a JSON-serialisable result.

Keeping them in one module (instead of inlining in strings throughout
the codebase) makes them diff-friendly and testable in isolation.
"""
from __future__ import annotations


# Extract wishlist / follower / review counts from the live storefront DOM.
POPULARITY_JS: str = """(appId) => {
    const out = { wishlist: null, followers: null, reviews: null };
    const parseInt0 = (s) => {
        const m = (s || '').replace(/[^0-9]/g, '');
        return m ? parseInt(m, 10) : null;
    };
    const wlSelectors = [
        '#wishlist_count',
        'span.wishlist_count',
        '[data-tooltip-text*="ishlist" i]',
        '.game_area_purchase_game .wishlist_count',
    ];
    for (const sel of wlSelectors) {
        const el = document.querySelector(sel);
        if (el) {
            const v = parseInt0(el.innerText || el.textContent);
            if (v != null) { out.wishlist = v; break; }
        }
    }
    const flSelectors = [
        '#followed_by_count',
        '[data-tooltip-text*="ollower" i]',
    ];
    for (const sel of flSelectors) {
        const el = document.querySelector(sel);
        if (el) {
            const v = parseInt0(el.innerText || el.textContent);
            if (v != null) { out.followers = v; break; }
        }
    }
    const revSelectors = [
        '.user_reviews_summary_row .responsive_reviewnumber',
        '.review_summary .responsive_reviewnumber',
        'label[for="review_summary_num"]',
    ];
    for (const sel of revSelectors) {
        const el = document.querySelector(sel);
        if (el) {
            const v = parseInt0(el.innerText || el.textContent);
            if (v != null) { out.reviews = v; break; }
        }
    }
    return out;
}"""


# Call the Steam `ajaxappreviews` endpoint from inside the browser.
# Carries the right cookies / age-check state and bypasses the JSON
# review cache (which lags 24-72h for newly-published apps).
AJAX_REVIEWS_JS: str = """async (url) => {
    try {
        const r = await fetch(url, {
            credentials: 'include',
            headers: { 'Accept': 'application/json, text/plain, */*' }
        });
        const text = await r.text();
        return { status: r.status, ok: r.ok, body: text };
    } catch (e) {
        return { error: String(e) };
    }
}"""


__all__ = ["POPULARITY_JS", "AJAX_REVIEWS_JS"]