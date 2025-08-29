// content-genrator.js - Height Management + Centered Spinner + Fade-in Results

(function () {
  class IframeHeightManager {
    constructor() {
      this.lastHeight = 0;
      this.resizeObserver = null;
      this.debounceTimeout = null;
      this.init();
    }

    init() {
      this.startHeightMonitoring();
      setTimeout(() => {
        this.sendHeightToParent();
        try {
          window.parent.postMessage({ type: 'widget-ready', timestamp: Date.now(), source: 'content-generator' }, '*');
        } catch (error) {
          console.warn('Failed to send widget-ready to parent:', error);
        }
      }, 1000);
    }

    startHeightMonitoring() {
      if (window.ResizeObserver) {
        this.resizeObserver = new ResizeObserver(() => this.debounceHeightUpdate());
        this.resizeObserver.observe(document.body);
      }

      const observer = new MutationObserver(() => this.debounceHeightUpdate());
      observer.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['style', 'class'] });

      setInterval(() => this.sendHeightToParent(), 3000);
    }

    debounceHeightUpdate() {
      if (this.debounceTimeout) clearTimeout(this.debounceTimeout);
      this.debounceTimeout = setTimeout(() => this.sendHeightToParent(), 150);
    }

    getOptimalHeight() {
      const maxHeight = Math.max(document.body.scrollHeight, document.documentElement.scrollHeight, window.innerHeight);
      return Math.min(Math.max(400, maxHeight + 50), 900);
    }

    sendHeightToParent() {
      const newHeight = this.getOptimalHeight();
      if (Math.abs(newHeight - this.lastHeight) > 15) {
        this.lastHeight = newHeight;
        try {
          const heightMessage = { type: 'resize', height: newHeight, timestamp: Date.now(), source: 'content-generator' };
          window.parent.postMessage(heightMessage, '*');
          window.parent.postMessage({ ...heightMessage, type: 'iframeResize' }, '*');
        } catch (error) {
          console.warn('Failed to send height to parent:', error);
        }
      }
    }

    triggerHeightUpdate() {
      setTimeout(() => this.sendHeightToParent(), 100);
    }

    forceHeightUpdate() {
      this.lastHeight = 0;
      this.sendHeightToParent();
    }
  }

  window.addEventListener('load', () => {
    const heightManager = new IframeHeightManager();
    window.contentGeneratorHeightManager = heightManager;

    // Inject styles for spinner and fade-in animation
    const style = document.createElement('style');
    style.textContent = `
      #loading-animation {
        display: none;
        justify-content: center;
        align-items: center;
        flex-direction: row;
        margin: 30px auto 0 auto;
        font-size: 14px;
        color: #ffffff;
        width: 100%;
        text-align: center;
      }
      #loading-animation .spinner {
        width: 22px;
        height: 22px;
        border: 3px solid rgba(255,255,255,0.3);
        border-top-color: #ffffff;
        border-radius: 50%;
        animation: spin 0.8s linear infinite;
        margin-right: 8px;
      }
      @keyframes spin {
        to { transform: rotate(360deg); }
      }
      #result {
        opacity: 0;
        transition: opacity 0.8s ease-in-out;
        margin-top: 30px;
      }
      #result.fade-in {
        opacity: 1;
      }
    `;
    document.head.appendChild(style);

    // Create loading spinner element
    const loaderElement = document.createElement('div');
    loaderElement.id = 'loading-animation';
    loaderElement.classList.add('loading-container');
    loaderElement.innerHTML = `
      <div class="spinner"></div>
      <span>Hold tight, your plan is being generated…</span>
    `;

    const generateButton = document.querySelector('#generate-button') ||
      Array.from(document.getElementsByTagName('button')).find(btn => btn.textContent.trim().toLowerCase() === 'generate strategy');

    if (generateButton) {
      const formElem = generateButton.closest('form');
      if (formElem) {
        formElem.insertAdjacentElement('afterend', loaderElement);
      } else {
        generateButton.parentNode?.insertAdjacentElement('afterend', loaderElement);
      }
    }

    function showLoading() {
      loaderElement.style.display = 'flex';
      heightManager.triggerHeightUpdate();
    }

    function hideLoading() {
      loaderElement.style.display = 'none';
      heightManager.triggerHeightUpdate();
    }

    function getCSRFToken() {
      return document.querySelector('input[name="csrfmiddlewaretoken"]')?.value;
    }

    if (generateButton) {
      generateButton.addEventListener('click', (event) => {
        event.preventDefault();
        const formElem = generateButton.closest('form');
        if (!formElem) return;

        const formData = new FormData(formElem);
        const jsonData = {};
        formData.forEach((value, key) => { jsonData[key] = value; });

        const csrfToken = getCSRFToken();
        showLoading();

        fetch('/content-strategy/json/', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken
          },
          body: JSON.stringify(jsonData)
        })
        .then(response => {
          if (!response.ok) throw new Error(`HTTP error ${response.status}`);
          return response.json();
        })
        .then(data => {
          const resultContainer = document.querySelector('#result');
          if (data.result && resultContainer) {
            resultContainer.innerHTML = data.result;
            resultContainer.classList.remove('fade-in'); // reset animation
            void resultContainer.offsetWidth; // force reflow
            resultContainer.classList.add('fade-in');
            heightManager.triggerHeightUpdate();
          }
        })
        .catch(error => {
          console.error('Error generating plan:', error);
          const resultContainer = document.querySelector('#result');
          if (resultContainer) {
            resultContainer.innerHTML = `<p style="color:red;">An error occurred. Please try again later.</p>`;
            heightManager.triggerHeightUpdate();
          }
        })
        .finally(() => {
          hideLoading();
        });
      });
    }

    // Height watchers
    window.addEventListener('resize', () => heightManager.triggerHeightUpdate());
    document.addEventListener('visibilitychange', () => { if (!document.hidden) heightManager.forceHeightUpdate(); });
    window.addEventListener('pageshow', (e) => { if (e.persisted) setTimeout(() => heightManager.forceHeightUpdate(), 300); });
  });
})();
