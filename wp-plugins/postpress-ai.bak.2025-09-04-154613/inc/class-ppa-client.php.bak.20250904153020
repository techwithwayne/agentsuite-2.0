<?php
# CHANGED: 2025-09-04 - imported class-ppa-client.php (one-file import)
/**
 * CHANGE LOG
 * 2025-09-04: Imported client file from plugin ZIP into agentsuite repo branch.
 */
/**
 * CHANGE LOG
 * 2025-08-18 (Step 1 – client bootstrap in correct folder)
 * - NEW FILE in /inc/: Adds PPA_Client, a hardened WP HTTP API wrapper for calling the Django service.
 * - Enforces: HTTPS base, header normalization (Origin, Content-Type, X-PPA-Key), timeout cap (<=15s),
 *   secret-safe logging, JSON parsing, and non-fatal contract hints.
 * - No behavior changes to controllers yet. Next step will wire the controller to use this client.
 *
 * Markers:
 * - Entire file is new. Security-critical lines are annotated with `// CHANGED:`.
 */

if ( ! defined( 'ABSPATH' ) ) { exit; } // CHANGED: block direct access for security.

/**
 * PPA_Client
 *
 * Single-responsibility HTTP wrapper (WP HTTP API) for calls to the Django PostPress AI service.
 * SECURITY:
 * - NEVER leak the shared key. Only log lengths/booleans.
 * - Always send Origin and Content-Type. Keep X-PPA-Key strictly server-side.
 * - Enforce HTTPS base and cap timeouts at 15s.
 */
final class PPA_Client { // CHANGED:

	/** WP site origin expected by Django’s origin checks. */
	private const ORIGIN = 'https://techwithwayne.com'; // CHANGED:

	/** Resolve configured Django base URL (without `/postpress-ai/`) and normalize. */
	private static function get_base_url(): string { // CHANGED:
		$base = get_option( 'ppa_server_base', '' ); // CHANGED:
		$base = is_string( $base ) ? trim( $base ) : ''; // CHANGED:

		// Default to PythonAnywhere direct if unset (avoids CF WAF blocks during setup). // CHANGED:
		if ( $base === '' ) {
			$base = 'https://techwithwayne.pythonanywhere.com'; // CHANGED:
		}

		// Strip trailing slashes and enforce HTTPS only. // CHANGED:
		$base = preg_replace( '#/*$#', '', $base ); // CHANGED:
		if ( ! preg_match( '#^https://#i', $base ) ) { // CHANGED:
			$base = 'https://techwithwayne.pythonanywhere.com'; // CHANGED:
		}
		return $base; // CHANGED:
	}

	/** Build full endpoint URL under `/postpress-ai/`. */
	private static function build_url( string $endpoint ): string { // CHANGED:
		$endpoint = ltrim( $endpoint, '/' ); // CHANGED:
		return self::get_base_url() . '/postpress-ai/' . $endpoint; // CHANGED:
	}

	/** Timeout from option (default 10), capped at 15 seconds. */
	private static function get_timeout(): int { // CHANGED:
		$opt = get_option( 'ppa_timeout_seconds', 10 ); // CHANGED:
		$val = is_numeric( $opt ) ? (int) $opt : 10; // CHANGED:
		if ( $val <= 0 ) { $val = 10; } // CHANGED:
		if ( $val > 15 ) { $val = 15; } // CHANGED:
		return $val; // CHANGED:
	}

	/** Read the server-auth header (NEVER expose or log value). */
	private static function get_auth_key(): string { // CHANGED:
		$key = get_option( 'ppa_shared_key', '' ); // CHANGED:
		return is_string( $key ) ? trim( $key ) : ''; // CHANGED:
	}

	/** Common headers — keep X-PPA-Key server-side only. */
	private static function build_headers(): array { // CHANGED:
		return [
			'Content-Type' => 'application/json; charset=utf-8', // CHANGED:
			'Origin'       => self::ORIGIN, // CHANGED:
			'X-PPA-Key'    => self::get_auth_key(), // CHANGED:
		];
	}

	/**
	 * Central request routine.
	 *
	 * @param string      $method   'GET' or 'POST'
	 * @param string      $endpoint e.g. 'preview/', 'store/', 'version/', 'health/', 'preview/debug-model/'
	 * @param array|null  $payload  JSON-serializable array for POST
	 * @param array       $require_fields Optional keys to sanity-check returned JSON (non-fatal)
	 *
	 * @return array {
	 *   ok: bool,
	 *   status_code: int,
	 *   json: array|null,
	 *   ver: string|null,
	 *   contract_ok: bool|null,
	 *   missing: array|null,
	 *   error: string|null, // 'transport_error' | 'http_error' | 'non_json_response' | server 'error'
	 * }
	 */
	public static function request( string $method, string $endpoint, ?array $payload = null, array $require_fields = [] ): array { // CHANGED:
		$method = strtoupper( $method ); // CHANGED:
		$url    = self::build_url( $endpoint ); // CHANGED:

		$args = [ // CHANGED:
			'method'    => $method, // CHANGED:
			'timeout'   => self::get_timeout(), // CHANGED:
			'headers'   => self::build_headers(), // CHANGED:
			'sslverify' => true, // CHANGED:
		];

		if ( $method === 'POST' ) { // CHANGED:
			$args['body'] = wp_json_encode( is_array( $payload ) ? $payload : [] ); // CHANGED:
		}

		$resp = wp_remote_request( $url, $args ); // CHANGED:

		if ( is_wp_error( $resp ) ) { // CHANGED:
			self::log_transport( $url, $args, null, null, $resp ); // CHANGED:
			return [
				'ok'          => false, // CHANGED:
				'status_code' => 0, // CHANGED:
				'json'        => null, // CHANGED:
				'ver'         => null, // CHANGED:
				'contract_ok' => null, // CHANGED:
				'missing'     => null, // CHANGED:
				'error'       => 'transport_error', // CHANGED:
			];
		}

		$code = (int) wp_remote_retrieve_response_code( $resp ); // CHANGED:
		$body = wp_remote_retrieve_body( $resp ); // CHANGED:

		$decoded = null; // CHANGED:
		if ( is_string( $body ) && $body !== '' ) { // CHANGED:
			$decoded = json_decode( $body, true ); // CHANGED:
			if ( ! is_array( $decoded ) ) { $decoded = null; } // CHANGED:
		}

		self::log_transport( $url, $args, $code, $body, null ); // CHANGED:

		$contract_ok = null; // CHANGED:
		$missing     = null; // CHANGED:
		if ( is_array( $decoded ) && $require_fields ) { // CHANGED:
			$missing = []; // CHANGED:
			foreach ( $require_fields as $k ) { // CHANGED:
				if ( ! array_key_exists( $k, $decoded ) ) { $missing[] = $k; } // CHANGED:
			}
			$contract_ok = empty( $missing ); // CHANGED:
		}

		$ok = ( $code >= 200 && $code < 300 && is_array( $decoded ) ); // CHANGED:

		return [
			'ok'          => $ok, // CHANGED:
			'status_code' => $code, // CHANGED:
			'json'        => $decoded, // CHANGED:
			'ver'         => is_array( $decoded ) && isset( $decoded['ver'] ) ? (string) $decoded['ver'] : null, // CHANGED:
			'contract_ok' => $contract_ok, // CHANGED:
			'missing'     => $missing, // CHANGED:
			'error'       => $ok ? null : ( is_array( $decoded ) && isset( $decoded['error'] ) ? (string) $decoded['error'] : ( $code >= 200 && $code < 300 ? 'non_json_response' : 'http_error' ) ), // CHANGED:
		];
	}

	/** Convenience: POST /preview/ */
	public static function post_preview( array $payload ): array { // CHANGED:
		// Server: { ok:true, result:{ title, html, summary }, token_usage?, quota?, ver } // CHANGED:
		return self::request( 'POST', 'preview/', $payload, [ 'ok' ] ); // CHANGED:
	}

	/** Convenience: POST /store/ */
	public static function post_store( array $payload ): array { // CHANGED:
		// Server: HTTP 200 always, normalized envelope { ok, stored, id|null, mode, target_used, wp_status, ... } // CHANGED:
		return self::request( 'POST', 'store/', $payload, [ 'ok' ] ); // CHANGED:
	}

	/** Convenience: GET /version/ */
	public static function get_version(): array { // CHANGED:
		return self::request( 'GET', 'version/', null, [ 'ok', 'ver' ] ); // CHANGED:
	}

	/** Convenience: GET /health/ */
	public static function get_health(): array { // CHANGED:
		return self::request( 'GET', 'health/', null, [ 'ok' ] ); // CHANGED:
	}

	/** Convenience: GET /preview/debug-model/ (auth) */
	public static function get_preview_debug_model(): array { // CHANGED:
		return self::request( 'GET', 'preview/debug-model/', null, [ 'ok' ] ); // CHANGED:
	}

	/**
	 * Secret-safe breadcrumb logging (only when WP_DEBUG_LOG is enabled):
	 * - Logs: method, host, path, timeout, body_len, status, is_json, key_provided_len, key_present flag.
	 * - NEVER logs secrets or bodies.
	 */
	private static function log_transport( string $url, array $args, ?int $code, ?string $body, $wp_error ): void { // CHANGED:
		if ( ! defined( 'WP_DEBUG_LOG' ) || ! WP_DEBUG_LOG ) { return; } // CHANGED:

		$method   = strtoupper( $args['method'] ?? 'GET' ); // CHANGED:
		$timeout  = (int) ( $args['timeout'] ?? 0 ); // CHANGED:
		$headers  = (array) ( $args['headers'] ?? [] ); // CHANGED:
		$key      = (string) ( $headers['X-PPA-Key'] ?? '' ); // CHANGED:
		$key_len  = strlen( $key ); // CHANGED:
		$key_set  = $key_len > 0; // CHANGED:
		$body_len = isset( $args['body'] ) ? strlen( (string) $args['body'] ) : 0; // CHANGED:
		$is_json  = is_string( $body ) ? ( json_decode( $body, true ) !== null ) : false; // CHANGED:

		$parts = wp_parse_url( $url ); // CHANGED:
		$host  = $parts['host'] ?? ''; // CHANGED:
		$path  = $parts['path'] ?? ''; // CHANGED:

		$prefix = '[PPA][wp][client]'; // CHANGED:

		if ( is_wp_error( $wp_error ) ) { // CHANGED:
			error_log( sprintf(
				"%s transport_error method=%s host=%s path=%s timeout=%ds key_provided_len=%d key_present=%s body_len=%d error=%s",
				$prefix, $method, $host, $path, $timeout, $key_len, $key_set ? 'true' : 'false', $body_len, $wp_error->get_error_code()
			) ); // CHANGED:
			return; // CHANGED:
		}

		error_log( sprintf(
			"%s response method=%s host=%s path=%s timeout=%ds key_provided_len=%d key_present=%s body_len=%d status=%s is_json=%s",
			$prefix, $method, $host, $path, $timeout, $key_len, $key_set ? 'true' : 'false', $body_len,
			$code === null ? 'null' : (string) $code,
			$is_json ? 'true' : 'false'
		) ); // CHANGED:
	}
}
