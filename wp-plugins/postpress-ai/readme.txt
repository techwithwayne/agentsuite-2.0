=== PostPress AI ===
Contributors: techwithwayne
Tags: ai, content, openai, assistant, editor
Requires at least: 6.1
Tested up to: 6.6
Requires PHP: 7.4
Stable tag: 0.1.0
License: GPLv2 or later
License URI: https://www.gnu.org/licenses/gpl-2.0.html

Generate AI-powered drafts from the WordPress admin, with exact-HTML preservation and a secure Django backend.

== Description ==
PostPress AI lets editors compose a subject, choose a genre and tone, and instantly preview rich HTML in the admin. 
When you save or publish, the plugin preserves the exact HTML (bypassing KSES *only* for that request) and logs token usage locally for your site admins.

**Highlights**
- Fast preview: calls your Django backend with a shared key over HTTPS.
- Exact HTML preservation on save/publish (no surprise sanitization).
- Local token-usage ledger (Editors+): POST/GET `/wp-json/ppa/v1/tokens`.
- Clean, modern admin UI with keyboard shortcuts.

**Security**
- Requires Editor+ capabilities for token logs.
- No broad CORS changes in WordPress; Django enforces `X-PPA-Key`.

== Installation ==
1. Upload the `postpress-ai` folder to `/wp-content/plugins/`.
2. Activate the plugin in **Plugins → Installed Plugins**.
3. Go to **Settings → PostPress AI** and open the **PostPress AI** page.
4. Ensure your Django app exposes `/postpress-ai/preview/` and `/postpress-ai/store/` 
   and that `PPA_SHARED_KEY` matches on both sides.

== Frequently Asked Questions ==

= Does this require external accounts? =
You’ll need an AI backend (Django app) with an OpenAI-compatible client configured server-side.

= Where are token logs stored? =
A compact rolling ledger is stored in the `ppa_token_ledger` site option (Editors+ only).

= Will this modify KSES for all requests? =
No. It temporarily relaxes sanitization only when a request is marked with the plugin’s header during Save/Publish.

== Screenshots ==
1. Compose and Preview split view.
2. Token chip with input/output/total.
3. Quota banner (optional).

== Changelog ==
= 0.1.0 =
- Initial release: Preview, Save Draft, Publish, exact-HTML preservation, local token logs, and UI polish.

== Upgrade Notice ==
= 0.1.0 =
First release; verify your Django base URL and shared key.
