/*
 * SurgiCentral static demo — shared site JS.
 * Loaded on every page after the Bootstrap bundle. Provides:
 *   - Nav partial injection (computes relative prefix from folder depth)
 *   - demoStore: localStorage-backed fake persistence for "fake-live" flows
 *   - toast(): small bootstrap toast helper
 *   - Auto-wiring for [data-demo-inert] elements (nav items with no static
 *     equivalent — shows a toast instead of doing nothing silently)
 */
(function () {
  "use strict";

  // ── Path prefix ──────────────────────────────────────────────────────────
  // Every content page lives exactly one folder below the site root
  // (e.g. /procurement/index.html) except the root index.html itself.
  // This lets the same nav.html work from any depth without hardcoding
  // a deployment path.
  function computePrefix() {
    var segments = window.location.pathname.split('/').filter(Boolean);
    // Drop the filename itself
    if (segments.length && segments[segments.length - 1].indexOf('.html') !== -1) {
      segments.pop();
    }
    return segments.length >= 1 ? '../'.repeat(1) : '';
  }
  window.SITE_PREFIX = computePrefix();

  // ── Toasts ───────────────────────────────────────────────────────────────
  function ensureToastContainer() {
    var c = document.querySelector('.demo-toast-container');
    if (!c) {
      c = document.createElement('div');
      c.className = 'demo-toast-container';
      document.body.appendChild(c);
    }
    return c;
  }

  window.toast = function (message, variant) {
    variant = variant || 'primary';
    var container = ensureToastContainer();
    var el = document.createElement('div');
    el.className = 'toast align-items-center text-bg-' + variant + ' border-0';
    el.setAttribute('role', 'alert');
    el.innerHTML =
      '<div class="d-flex">' +
      '<div class="toast-body">' + message + '</div>' +
      '<button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>' +
      '</div>';
    container.appendChild(el);
    var t = new bootstrap.Toast(el, { delay: 3500 });
    t.show();
    el.addEventListener('hidden.bs.toast', function () { el.remove(); });
  };

  // ── demoStore: fake-live persistence for signature write flows ─────────
  // Namespaced localStorage wrapper. Data entered during a demo session
  // persists across page views in the same browser tab/profile, but never
  // touches a server — refreshing after clearing storage resets to the
  // baked-in snapshot. This is intentionally NOT real persistence.
  window.demoStore = {
    _key: function (ns) { return 'surgicentral_demo::' + ns; },

    get: function (ns, fallback) {
      try {
        var raw = localStorage.getItem(this._key(ns));
        return raw ? JSON.parse(raw) : (fallback !== undefined ? fallback : null);
      } catch (e) { return fallback !== undefined ? fallback : null; }
    },

    set: function (ns, value) {
      localStorage.setItem(this._key(ns), JSON.stringify(value));
    },

    append: function (ns, row) {
      var list = this.get(ns, []);
      list.push(row);
      this.set(ns, list);
      return list;
    },

    reset: function (ns) {
      localStorage.removeItem(this._key(ns));
    },

    resetAll: function () {
      Object.keys(localStorage)
        .filter(function (k) { return k.indexOf('surgicentral_demo::') === 0; })
        .forEach(function (k) { localStorage.removeItem(k); });
    }
  };

  // ── Nav injection ────────────────────────────────────────────────────────
  document.addEventListener('DOMContentLoaded', function () {
    var placeholder = document.getElementById('nav-placeholder');
    if (placeholder) {
      fetch(window.SITE_PREFIX + 'assets/partials/nav.html')
        .then(function (r) { return r.text(); })
        .then(function (html) {
          html = html.split('{{PREFIX}}').join(window.SITE_PREFIX);
          placeholder.innerHTML = html;
          wireInertLinks();
        })
        .catch(function () {
          placeholder.innerHTML = '<div class="alert alert-warning m-3">Nav failed to load — open this page from a web server, not file://</div>';
        });
    } else {
      wireInertLinks();
    }
  });

  function wireInertLinks() {
    document.querySelectorAll('[data-demo-inert]').forEach(function (el) {
      el.addEventListener('click', function (e) {
        e.preventDefault();
        toast('"' + el.getAttribute('data-demo-inert') + '" needs the live SurgiCentral backend — not wired up in this static portfolio demo.', 'secondary');
      });
    });
  }

  // Expose for pages that wire inert buttons added after their own JSON render
  window.wireInertLinks = wireInertLinks;
})();
