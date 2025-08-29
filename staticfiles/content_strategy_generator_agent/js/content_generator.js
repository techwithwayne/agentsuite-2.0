// content-genrator.js - Height Management and Loading Animation for Content Strategy Generator

// Immediately-invoked function expression to isolate scope and avoid polluting globals
(function () {
  class IframeHeightManager {
    constructor() {
      this.lastHeight = 0;
      this.resizeObserver = null;
      this.debounceTimeout = null;
      this.init();
    }

    init() {
      console.log('📏 Initializing iframe height manager for Content Generator');
      this.startHeightMonitoring();
      setTimeout(() => {
        this.sendHeightToParent();
        try {
          window.parent.postMessage({
            type: 'widget-ready',
            timestamp: Date.now(),
            source: 'content-generator'
          }, '*');
          console.log('🎉 Sent widget-ready to parent');
        } catch (error) {
          console.warn('Failed to send widget-ready to parent:', error);
        }
      }, 1000);
    }

    startHeightMonitoring() {
      if (window.ResizeObserver) {
        this.resizeObserver = new ResizeObserver(() => {
          this.debounceHeightUpdate();
        });
        this.resizeObserver.observe(document.body);
      }
      const observer = new MutationObserver((mutations) => {
        let shouldUpdate = false;
        mutations.forEach((mutation) => {
          if (
            mutation.type === 'childList' ||
            mutation.type === 'attributes' ||
            mutation.type === 'subtree'
          ) {
            shouldUpdate = true;
          }
        });
        if (shouldUpdate) {
          this.debounceHeightUpdate();
        }
      });
      observer.observe(document.body, {
        childList: true,
        subtree: true,
        attributes: true,
        attributeFilter: ['style', 'class']
      });
      setInterval(() => {
        this.sendHeightToParent();
      }, 3000);
    }

    debounceHeightUpdate() {
      if (this.debounceTimeout) {
        clearTimeout(this.debounceTimeout);
      }
      this.debounceTimeout = setTimeout(() => {
        this.sendHeightToParent();
      }, 150);
    }

    getOptimalHeight() {
      const bodyScrollHeight = document.body.scrollHeight;
      const documentHeight = document.documentElement.scrollHeight;
      const windowHeight = window.innerHeight;
      const maxHeight = Math.max(bodyScrollHeight, documentHeight, windowHeight);
      const finalHeight = Math.max(400, maxHeight + 50);
      return Math.min(finalHeight, 900);
    }

    sendHeightToParent() {
      const newHeight = this.getOptimalHeight();
      if (Math.abs(newHeight - this.lastHeight) > 15) {
        this.lastHeight = newHeight;
        try {
          const heightMessage = {
            type: 'resize',
            height: newHeight,
            timestamp: Date.now(),
            source: 'content-generator'
          };
          window.parent.postMessage(heightMessage, '*');
          window.parent.postMessage({
            type: 'iframeResize',
            height: newHeight,
            timestamp: Date.now(),
            source: 'content-generator'
          }, '*');
          console.log(`📤 Sent height to parent: ${newHeight}px`);
        } catch (error) {
          console.warn('Failed to send height to parent:', error);
        }
      }
    }

    triggerHeightUpdate() {
      setTimeout(() => {
        this.sendHeightToParent();
      }, 100);
    }

    forceHeightUpdate() {
      this.lastHeight = 0;
      this.sendHeightToParent();
    }
  }

  window.addEventListener('load', () => {
    const heightManager = new IframeHeightManager();
    window.contentGeneratorHeightManager = heightManager;

    const loadingStyle = document.createElement('style');
    loadingStyle.textContent = `
      #loading-animation {
        display: none;
        text-align: center;
        margin-top: 20px;
        font-size: 14px;
        color: #121212;
        align-items: center;
        justify-content: center;
      }
      #loading-animation .spinner {
        display: inline-block;
        width: 20px;
        height: 20px;
        border: 3px solid rgba(18, 18, 18, 0.2);
        border-top-color: #ff6c00;
        border-radius: 50%;
        animation: spin 0.8s linear infinite;
        margin-right: 8px;
      }
      @keyframes spin {
        to { transform: rotate(360deg); }
      }
    `;
    document.head.appendChild(loadingStyle);

    let generateButton = document.querySelector('#generate-button');
    if (!generateButton) {
      const allButtons = Array.from(document.getElementsByTagName('button'));
      generateButton = allButtons.find(btn => btn.textContent.trim().toLowerCase() === 'generate strategy');
    }

    const loaderElement = document.createElement('div');
    loaderElement.id = 'loading-animation';
    loaderElement.innerHTML = '<div class="spinner"></div><span class="loading-text">Hold tight, your plan is being generated…</span>';

    (function insertLoader() {
      if (generateButton) {
        const formElem = generateButton.closest('form');
        if (formElem) {
          formElem.insertAdjacentElement('afterend', loaderElement);
          return;
        }
        const parentNode = generateButton.parentNode;
        if (parentNode) {
          parentNode.insertAdjacentElement('afterend', loaderElement);
          return;
        }
      }
      document.body.appendChild(loaderElement);
    })();

    function showLoading() {
      loaderElement.style.display = 'flex';
      if (window.contentGeneratorHeightManager) {
        window.contentGeneratorHeightManager.triggerHeightUpdate();
      }
    }

    function hideLoading() {
      loaderElement.style.display = 'none';
      if (window.contentGeneratorHeightManager) {
        window.contentGeneratorHeightManager.triggerHeightUpdate();
      }
    }

    if (generateButton) {
      generateButton.addEventListener('click', (event) => {
        event.preventDefault();
        showLoading();

        const formElem = generateButton.closest('form');
        const formData = new FormData(formElem);
        const payload = Object.fromEntries(formData.entries());

        const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');

        fetch('/content-strategy/', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken
          },
          body: JSON.stringify(payload)
        })
          .then((response) => {
            const contentType = response.headers.get("content-type");
            if (!response.ok) {
              throw new Error(`HTTP error ${response.status}`);
            }
            if (contentType && contentType.includes("application/json")) {
              return response.json();
            } else {
              throw new Error("Expected JSON but got HTML");
            }
          })
          .then((data) => {
            if (!document.getElementById('result-container')) {
              const resultDiv = document.createElement('div');
              resultDiv.id = 'result-container';
              loaderElement.insertAdjacentElement('afterend', resultDiv);
            }
            document.getElementById('result-container').innerHTML = data.result || '<p>No result received.</p>';
          })
          .catch((error) => {
            console.error('Error generating plan:', error);
          })
          .finally(() => {
            hideLoading();
          });
      });
    }

    window.addEventListener('resize', () => {
      heightManager.triggerHeightUpdate();
    });
    document.addEventListener('visibilitychange', () => {
      if (!document.hidden) {
        heightManager.forceHeightUpdate();
      }
    });
    window.addEventListener('pageshow', (event) => {
      if (event.persisted) {
        setTimeout(() => {
          heightManager.forceHeightUpdate();
        }, 300);
      }
    });
  });
})();
