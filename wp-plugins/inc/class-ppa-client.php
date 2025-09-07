<?php
# CHANGED: 2025-09-04 - add preview endpoint fallback probe and cache (tries /api/preview/, /preview/, /postpress-ai/preview/)
 /**
  * PPA_Client
  *
  * Utility client used by the PostPress AI WP plugin to resolve upstream endpoints.
  *
  * CHANGE LOG
  * 2025-09-04: Added preview endpoint probe fallback and caching. Tries a set of
  *             common preview endpoints if the configured ppa_server_base does not
  *             already include the preview path. Caches successful path for 1 hour.
  *
  * Notes:
  * - This helper purposely does not make assumptions about auth. Do not log secrets.
  * - If you want to adjust candidate endpoints, edit the $candidates array in probe_preview_path().
  */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

if ( ! class_exists( 'PPA_Client' ) ) :

final class PPA_Client {

    // transient prefix keys
    private const TRANSIENT_PREFIX = 'ppa_resolved_path_';
    // TTL for cached resolved path (seconds)
    private const TRANSIENT_TTL = 60 * 60; // 1 hour

    /**
     * Return the full preview URL for the configured server base.
     *
     * Returns a string like: https://apps.techwithwayne.com/postpress-ai/preview/
     * or false on failure (no resolved endpoint).
     *
     * @return string|false
     */
    public static function get_preview_url() {
        $base = trim( (string) get_option( 'ppa_server_base', '' ) );
        if ( empty( $base ) ) {
            return false;
        }

        // If base already contains a preview-like path, use it directly (no probe).
        $maybe = self::normalize_and_detect_if_base_has_action_path( $base, 'preview' );
        if ( $maybe !== false ) {
            return esc_url_raw( rtrim( $maybe, '/' ) . '/' );
        }

        // Check transient cache first
        $trans_key = self::TRANSIENT_PREFIX . 'preview';
        $cached = get_transient( $trans_key );
        if ( ! empty( $cached ) ) {
            return esc_url_raw( rtrim( $base, '/' ) . $cached );
        }

        // Probe candidate endpoints
        $resolved = self::probe_preview_path( $base );
        if ( $resolved === false ) {
            return false;
        }

        // Cache the path fragment (e.g. '/postpress-ai/preview/')
        set_transient( $trans_key, $resolved, self::TRANSIENT_TTL );
        return esc_url_raw( rtrim( $base, '/' ) . $resolved );
    }

    /**
     * Probe common candidate paths for a working preview endpoint.
     *
     * Returns the path fragment (leading slash, trailing slash) on success, e.g. '/postpress-ai/preview/'
     * or false if none of the candidates resolved.
     *
     * @param string $base
     * @return string|false
     */
    private static function probe_preview_path( string $base ) {
        $candidates = [
            '/api/preview/',
            '/preview/',
            '/api/v1/preview/',
            '/v1/preview/',
            '/postpress-ai/preview/',
            '/postpress-ai/api/preview/',
        ];

        $base = rtrim( $base, '/' );

        // Use a lightweight HEAD request first to detect an existing endpoint.
        $args = [
            'timeout'     => 8,
            'redirection' => 3,
            'blocking'    => true,
            'sslverify'   => true,
        ];

        foreach ( $candidates as $path ) {
            $url = $base . $path;

            // Try HEAD
            $head = wp_remote_head( $url, $args );
            if ( ! is_wp_error( $head ) ) {
                $code = (int) wp_remote_retrieve_response_code( $head );
                // Treat 2xx as success; also treat 401/403 as "endpoint exists but auth required"
                if ( ( $code >= 200 && $code < 300 ) || in_array( $code, [ 401, 403 ], true ) ) {
                    return $path;
                }

                // Some servers don't implement HEAD correctly (405). Try GET in that case.
                if ( in_array( $code, [ 405, 501, 0 ], true ) ) {
                    $get = wp_remote_get( $url, $args );
                    if ( ! is_wp_error( $get ) ) {
                        $gcode = (int) wp_remote_retrieve_response_code( $get );
                        if ( ( $gcode >= 200 && $gcode < 300 ) || in_array( $gcode, [ 401, 403 ], true ) ) {
                            return $path;
                        }
                    }
                }
            }
            // if head was WP_Error, continue to next candidate
        }

        // none matched
        return false;
    }

    /**
     * If the configured base URL already contains the requested action path,
     * return the full URL (base) as-is; otherwise return false.
     *
     * Example: base "https://apps.techwithwayne.com/postpress-ai/preview" returns that URL.
     *
     * @param string $base
     * @param string $action
     * @return string|false
     */
    private static function normalize_and_detect_if_base_has_action_path( string $base, string $action ) {
        $parsed = wp_parse_url( $base );
        if ( ! is_array( $parsed ) || empty( $parsed['path'] ) ) {
            return false;
        }
        $path = strtolower( rtrim( $parsed['path'], '/' ) );
        if ( strpos( $path, strtolower( $action ) ) !== false ) {
            // ensure proper trailing slash
            return rtrim( $base, '/' );
        }
        return false;
    }
}

endif;
