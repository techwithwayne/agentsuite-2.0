/**
 * Entry point — bundles into assets/js/admin.js
 */
import { boot } from './boot.js';

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', boot, { once: true });
} else {
  boot();
}
