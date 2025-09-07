<?php
# CHANGED: 2025-09-04 - enqueue preview-fix.js to ensure preview POSTs include subject/title/headline when needed
/**
 * PostPress AI - Admin Asset Loader
 * Path: /home/customer/www/techwithwayne.com/public_html/wp-content/plugins/postpress-ai/inc/class-ppa-admin.php
 *
 * Loads admin CSS/JS for composer and settings pages.
 * Injects configuration variables into JS, including secure nonce.
 *
 * @package PostPressAI
 */

/**
 * CHANGE LOG
 * ----------
 * 2025-08-24
 * - ADDED: Conditional enqueue of admin.js vs admin.min.js based on SCRIPT_DEBUG.    # CHANGED:
 *
 * 2025-08-21 (evening pass)
 * - ADDED: Cache-busting versions for CSS/JS using filemtime() to prevent stale admin.js loads.
 * - ADDED: Explicit `window.PPA = window.PPA || PPA;` alias to guarantee global access in JS.
 * - VERIFIED: Nonce uses wp_create_nonce('ppa_admin') to match controller verification.
 *
 * 2025-08-21 (earlier pass)
 * - FIXED: Injected correct nonce into JS via wp_localize_script.
 * - Confirmed we still localize ajaxUrl, page, and key_present.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit; // Prevent direct access
}

class PPA_Admin {

	/**
	 * Boot hooks.
	 */
	public static function init() {
		add_action( 'admin_enqueue_scripts', array( __CLASS__, 'enqueue_admin_assets' ) );
	}

	/**
	 * Enqueue admin scripts and styles.
	 *
	 * Loads dark mode CSS and admin.js, then injects variables
	 * (ajaxUrl, nonce, page slug, key presence).
	 *
	 * @param string $hook Current admin page hook.
	 */
	public static function enqueue_admin_assets( $hook ) {
		// Only load on plugin-specific pages (composer + settings).
		if ( strpos( $hook, 'ppa' ) === false && strpos( $hook, 'postpress-ai' ) === false ) {
			return;
		}

		// --- Cache-busting versions based on filemtime() ------------------------
		$css_file = plugin_dir_path( __FILE__ ) . '../assets/css/admin.css';
		$js_base  = plugin_dir_path( __FILE__ ) . '../assets/js/admin';
		$css_ver  = file_exists( $css_file ) ? (string) filemtime( $css_file ) : '1';

		// Decide which JS file to use (.js or .min.js)
		$suffix  = ( defined( 'SCRIPT_DEBUG' ) && SCRIPT_DEBUG ) ? '.js' : '.min.js';
		$js_file = $js_base . $suffix;
		$js_ver  = file_exists( $js_file ) ? (string) filemtime( $js_file ) : '1';

		// Register + enqueue admin CSS.
		wp_register_style(
			'ppa-admin',
			plugins_url( '../assets/css/admin.css', __FILE__ ),
			array(),
			$css_ver
		);
		wp_enqueue_style( 'ppa-admin' );

		// Register + enqueue admin JS (conditional .js/.min.js).
		wp_register_script(
			'ppa-admin',
			plugins_url( '../assets/js/admin' . $suffix, __FILE__ ),
			array( 'jquery' ),
			$js_ver,
			true
		);
		wp_enqueue_script( 'ppa-admin' );

		// Localize script with configuration object.
		wp_localize_script(
			'ppa-admin',
			'PPA',
			array(
				'ajaxUrl'     => admin_url( 'admin-ajax.php' ),
				'nonce'       => wp_create_nonce( 'ppa_admin' ),
				'page'        => isset( $_GET['page'] ) ? sanitize_text_field( $_GET['page'] ) : '',
				'key_present' => (bool) get_option( 'ppa_shared_key' ),
			)
		);

		// Ensure the localized object is also reachable as window.PPA.
		wp_add_inline_script(
			'ppa-admin',
			'window.PPA = window.PPA || (typeof PPA !== "undefined" ? PPA : {});',
			'before'
		);

		// --- ENQUEUE PREVIEW-FIX (defensive client-side patch) ----------------
		// This lightweight script ensures preview POSTs include subject/title/headline
		// when the admin UI does not supply them. It is dependent on 'ppa-admin'.
		// Ensure the file wp-plugins/postpress-ai/assets/js/preview-fix.js exists.
		$preview_fix_path = plugins_url( '../assets/js/preview-fix.js', __FILE__ );
		wp_register_script(
			'ppa-preview-fix',
			$preview_fix_path,
			array( 'ppa-admin' ),
			$js_ver,
			true
		);
		wp_enqueue_script( 'ppa-preview-fix' );
		// ---------------------------------------------------------------------

		// Inline fallback styles for dark mode (ensures visibility).
		$inline_css = '
			.ppa-dark {
				background-color: #121212;
				color: #f5f5f5;
			}
			.ppa-dark a {
				color: #4da3ff;
			}
			.ppa-column h1,
			.ppa-column h2,
			.ppa-column h3,
			.ppa-column h4,
			.ppa-column h5,
			.ppa-column h6,
			.ppa-column p,
			.ppa-column span {
				color: #ffffff;
			}
		';
		wp_add_inline_style( 'ppa-admin', $inline_css );
	}
}

PPA_Admin::init();
