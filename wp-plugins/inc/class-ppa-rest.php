<?php
/**
 * PostPress AI — REST API
 * Path: wp-content/plugins/postpress-ai/inc/class-ppa-rest.php
 *
 * Responsibilities:
 * - Register a minimal REST endpoint for local (site-level) token analytics.
 * - Route: POST /wp-json/ppa/v1/tokens  (Editors+ only)
 * - Also: GET  /wp-json/ppa/v1/tokens?limit=10 to read recent entries (Editors+).
 * - Store compact entries in site option "ppa_token_ledger" (capped length).
 *
 * Security:
 * - Requires capability "edit_posts" (Editors, Admins).
 * - Uses WP REST nonce via wp.apiFetch in the admin (no CORS changes).
 *
 * Source of truth:
 * - This is informational UX for the WP site. Django remains authoritative for freemium enforcement.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

if ( ! class_exists( 'PPA_REST' ) ) :

final class PPA_REST {

	const NS            = 'ppa/v1';
	const ROUTE_TOKENS  = '/tokens';
	const LEDGER_OPTION = 'ppa_token_ledger';
	const LEDGER_MAX    = 500; // keep the newest N entries only

	/**
	 * Bootstrap.
	 */
	public static function init() : void {
		add_action( 'rest_api_init', [ __CLASS__, 'register_routes' ] );
	}

	/**
	 * Register REST routes.
	 */
	public static function register_routes() : void {
		register_rest_route(
			self::NS,
			self::ROUTE_TOKENS,
			[
				// POST /ppa/v1/tokens — append one token log entry
				[
					'methods'             => WP_REST_Server::CREATABLE,
					'callback'            => [ __CLASS__, 'tokens_create' ],
					'permission_callback' => [ __CLASS__, 'can_edit_posts' ],
					'args'                => self::token_args_schema(),
				],
				// GET /ppa/v1/tokens?limit=10 — list recent entries
				[
					'methods'             => WP_REST_Server::READABLE,
					'callback'            => [ __CLASS__, 'tokens_list' ],
					'permission_callback' => [ __CLASS__, 'can_edit_posts' ],
					'args'                => [
						'limit' => [
							'type'              => 'integer',
							'required'          => false,
							'sanitize_callback' => 'absint',
							'validate_callback' => function( $value ) {
								return ( $value >= 1 && $value <= self::LEDGER_MAX );
							},
						],
					],
				],
			]
		);
	}

	/**
	 * Capability gate: Editors and above only.
	 */
	public static function can_edit_posts( WP_REST_Request $req ) : bool {
		return current_user_can( 'edit_posts' );
	}

	/**
	 * Schema for POST body fields — accept only what we use.
	 */
	private static function token_args_schema() : array {
		return [
			'input' => [
				'type'              => 'integer',
				'required'          => true,
				'sanitize_callback' => 'absint',
			],
			'output' => [
				'type'              => 'integer',
				'required'          => true,
				'sanitize_callback' => 'absint',
			],
			'total' => [
				'type'              => 'integer',
				'required'          => true,
				'sanitize_callback' => 'absint',
			],
			'subject' => [
				'type'              => 'string',
				'required'          => false,
				'sanitize_callback' => 'sanitize_text_field',
			],
			'genre' => [
				'type'              => 'string',
				'required'          => false,
				'sanitize_callback' => 'sanitize_text_field',
			],
			'tone' => [
				'type'              => 'string',
				'required'          => false,
				'sanitize_callback' => 'sanitize_text_field',
			],
			'ts' => [
				'type'              => 'string',
				'required'          => false,
				'sanitize_callback' => [ __CLASS__, 'sanitize_iso8601' ],
			],
		];
	}

	/**
	 * POST /tokens — append a ledger entry.
	 */
	public static function tokens_create( WP_REST_Request $req ) : WP_REST_Response {
		$user_id = get_current_user_id();

		// Stable per-install UUID used elsewhere (created by admin loader).
		$plugin_uuid = get_option( 'ppa_install_uuid', '' );
		if ( empty( $plugin_uuid ) ) {
			$plugin_uuid = wp_generate_uuid4();
			update_option( 'ppa_install_uuid', $plugin_uuid, true );
		}

		$entry = [
			'ts'          => $req->get_param( 'ts' ) ?: gmdate( 'c' ),
			'user_id'     => (int) $user_id,
			'subject'     => (string) ( $req->get_param( 'subject' ) ?: '' ),
			'genre'       => (string) ( $req->get_param( 'genre' ) ?: '' ),
			'tone'        => (string) ( $req->get_param( 'tone' ) ?: '' ),
			'input'       => (int) $req->get_param( 'input' ),
			'output'      => (int) $req->get_param( 'output' ),
			'total'       => (int) $req->get_param( 'total' ),
			'plugin_uuid' => (string) $plugin_uuid,
		];

		$ledger = get_option( self::LEDGER_OPTION, [] );
		if ( ! is_array( $ledger ) ) {
			$ledger = [];
		}

		$ledger[] = $entry;

		$len = count( $ledger );
		if ( $len > self::LEDGER_MAX ) {
			// Keep newest N entries
			$ledger = array_slice( $ledger, $len - self::LEDGER_MAX );
		}

		update_option( self::LEDGER_OPTION, $ledger, false );

		// Optional debug log in WP_DEBUG mode.
		if ( defined( 'WP_DEBUG' ) && WP_DEBUG ) {
			error_log( '[PPA] token_log: ' . wp_json_encode( $entry ) ); // phpcs:ignore
		}

		return new WP_REST_Response(
			[
				'ok'          => true,
				'stored'      => true,
				'count'       => count( $ledger ),
				'plugin_uuid' => $plugin_uuid,
				'last'        => $entry,
			],
			200
		);
	}

	/**
	 * GET /tokens — list recent entries.
	 */
	public static function tokens_list( WP_REST_Request $req ) : WP_REST_Response {
		$limit = (int) ( $req->get_param( 'limit' ) ?: 20 );
		$limit = max( 1, min( $limit, self::LEDGER_MAX ) );

		$ledger = get_option( self::LEDGER_OPTION, [] );
		if ( ! is_array( $ledger ) ) {
			$ledger = [];
		}

		$slice = array_slice( $ledger, -$limit );

		return new WP_REST_Response( array_values( $slice ), 200 );
	}

	/**
	 * Basic ISO8601 sanitizer. Falls back to current UTC time.
	 */
	public static function sanitize_iso8601( $value ) : string {
		$value = is_string( $value ) ? trim( $value ) : '';
		if ( preg_match( '/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?([+-]\d{2}:\d{2}|Z)$/', $value ) ) {
			return $value;
		}
		return gmdate( 'c' );
	}
}

PPA_REST::init();

endif;
