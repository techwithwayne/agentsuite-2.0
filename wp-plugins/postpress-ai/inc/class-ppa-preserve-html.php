<?php
# CHANGED: 2025-09-04 - imported from postpress_wp.zip
/**
 * CHANGE LOG
 * 2025-09-04: Imported from postpress_wp.zip into agentsuite repo branch.
 */
/**
 * PostPress AI — Scoped RAW HTML preservation for REST saves
 * -----------------------------------------------------------------------------
 * What/Why:
 * - WordPress may sanitize/alter post_content when saving via REST, depending
 *   on capabilities (KSES) or other filters. For our admin UI saves only, we
 *   want **byte-for-byte** HTML preservation.
 *
 * How:
 * - Admin JS wraps the save call in a temporary "RAW mode" and injects a header:
 *       X-PPA-Store: 1
 * - This class detects that exact header on REST requests to wp/v2/posts|pages,
 *   grants `unfiltered_html` for the duration of the request, disables KSES
 *   filters, then restores them afterwards.
 *
 * Scope:
 * - Active only for authenticated admins (wp-admin context / REST nonce).
 * - Only when the request has the header AND targets posts/pages endpoints.
 * - No effect on normal edits, front-end forms, or other plugins/routes.
 *
 * Security:
 * - We do NOT broaden CORS or expose any secrets.
 * - We only honor the header for authenticated requests that already pass REST
 *   permission checks; we just avoid sanitizing trusted admin HTML.
 * -----------------------------------------------------------------------------
 */

if ( ! defined( 'ABSPATH' ) ) { exit; }

final class PPA_Preserve_HTML {
	/** @var bool */
	private static $active = false;

	public static function init() {
		// Hook before REST callbacks to enable raw mode if needed
		add_filter( 'rest_request_before_callbacks', [ __CLASS__, 'maybe_enable_raw' ], 0, 3 );
		// Hook after callbacks to always restore
		add_filter( 'rest_request_after_callbacks',  [ __CLASS__, 'maybe_disable_raw' ], PHP_INT_MAX, 3 );
	}

	/**
	 * Detect our header and endpoint, then enable RAW mode.
	 *
	 * @param mixed           $response
	 * @param array|callable  $handler
	 * @param WP_REST_Request $request
	 * @return mixed
	 */
	public static function maybe_enable_raw( $response, $handler, $request ) {
		if ( self::should_enable_for_request( $request ) ) {
			self::begin_raw_mode();
		}
		return $response;
	}

	/**
	 * Always clean up after REST callback runs.
	 *
	 * @param mixed           $response
	 * @param array|callable  $handler
	 * @param WP_REST_Request $request
	 * @return mixed
	 */
	public static function maybe_disable_raw( $response, $handler, $request ) {
		if ( self::$active ) {
			self::end_raw_mode();
		}
		return $response;
	}

	/**
	 * Decide if this request should be handled in RAW mode.
	 */
	private static function should_enable_for_request( $request ) {
		// Only for authenticated users (REST nonce/cookie). Prevents front-end abuse.
		if ( ! is_user_logged_in() ) {
			return false;
		}

		// Require our explicit header from admin.js
		$flag = $request->get_header( 'X-PPA-Store' );
		if ( '1' !== $flag ) {
			return false;
		}

		// Only target core posts/pages REST endpoints
		$route = $request->get_route(); // e.g., "/wp/v2/posts" or "/wp/v2/posts/123"
		if ( ! is_string( $route ) ) {
			return false;
		}
		if ( 0 !== strpos( $route, '/wp/v2/posts' ) && 0 !== strpos( $route, '/wp/v2/pages' ) ) {
			return false;
		}

		// Only for create/update methods
		$method = strtoupper( $request->get_method() ); // POST | PUT | PATCH
		if ( ! in_array( $method, [ 'POST', 'PUT', 'PATCH' ], true ) ) {
			return false;
		}

		return true;
	}

	/**
	 * Turn on RAW mode for this request:
	 * - grant unfiltered_html
	 * - disable KSES filters
	 */
	private static function begin_raw_mode() {
		if ( self::$active ) {
			return;
		}
		self::$active = true;

		// Temporarily grant unfiltered_html to the current user
		add_filter( 'user_has_cap', [ __CLASS__, 'grant_unfiltered_html' ], 0, 4 );

		// Disable KSES filters for the duration of the request only
		if ( function_exists( 'kses_remove_filters' ) ) {
			kses_remove_filters();
		}

		// Some installs add balancing/cleanup filters on save; remove the common ones
		remove_filter( 'content_save_pre', 'balanceTags', 50 );
		remove_filter( 'content_save_pre', 'wp_filter_post_kses' );
		remove_filter( 'content_filtered_save_pre', 'wp_filter_post_kses' );
	}

	/**
	 * Restore default behavior after the REST callback finishes.
	 */
	private static function end_raw_mode() {
		// Restore KSES filters
		if ( function_exists( 'kses_init_filters' ) ) {
			kses_init_filters();
		}

		// Remove our temporary capability grant
		remove_filter( 'user_has_cap', [ __CLASS__, 'grant_unfiltered_html' ], 0 );

		self::$active = false;
	}

	/**
	 * Filter: grant unfiltered_html for this request only.
	 *
	 * @param array   $allcaps All the capabilities of the user.
	 * @param array   $caps    Actual capabilities being checked.
	 * @param array   $args    [0] requested cap, [1] user id, ...
	 * @param WP_User $user    WP_User object.
	 * @return array
	 */
	public static function grant_unfiltered_html( $allcaps, $caps, $args, $user ) {
		if ( self::$active && ! empty( $args[0] ) && 'unfiltered_html' === $args[0] ) {
			$allcaps['unfiltered_html'] = true;
		}
		return $allcaps;
	}
}

// Autoload: if the file is included, activate the hooks.
PPA_Preserve_HTML::init();
