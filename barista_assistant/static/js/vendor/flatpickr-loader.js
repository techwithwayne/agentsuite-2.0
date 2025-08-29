// vendor/flatpickr-loader.js
(function () {
  function loadJS(src) {
    return new Promise((res, rej) => {
      const s = document.createElement("script");
      s.src = src;
      s.onload = res;
      s.onerror = rej;
      document.head.appendChild(s);
    });
  }
  function loadCSS(href) {
    return new Promise((res, rej) => {
      const l = document.createElement("link");
      l.rel = "stylesheet";
      l.href = href;
      l.onload = res;
      l.onerror = rej;
      document.head.appendChild(l);
    });
  }
  let loading = null;
  window.ensureFlatpickr = function ensureFlatpickr() {
    if (window.flatpickr) return Promise.resolve(window.flatpickr);
    if (!loading) {
      // Pin a specific version
      const css = "https://cdn.jsdelivr.net/npm/flatpickr@4.6.13/dist/flatpickr.min.css";
      const js  = "https://cdn.jsdelivr.net/npm/flatpickr@4.6.13/dist/flatpickr.min.js";
      loading = Promise.all([loadCSS(css), loadJS(js)]).then(() => window.flatpickr);
    }
    return loading;
  };
})();
