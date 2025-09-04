<?php
# CHANGED: 2025-09-04 - robustly forward request payload and return raw HTML for preview endpoint
/**
 * PPA_Controller - AJAX proxy for PostPress AI
 *
 * CHANGE LOG
 * 2025-09-04: Imported and patched to:
 *   - Forward raw request body when present (php://input) to preserve Content-Type.
 *   - Forward form-encoded POST data when appropriate.
 *   - Add required proxy headers (X-PPA-Key, X-PPA-Client, X-PPA-Origin).
 *   - Return upstream preview responses as raw HTML (preserve Content-Type).
 *   - Unwrap JSON-wrapped upstream payloads that use {status, body}.
 *
 * Note: This file intentionally avoids logging secrets. Do not add code that writes the
 * X-PPA-Key to logs or disk.
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

if ( ! class_exists( 'PPA_Controller' ) ) :

final class PPA_Controller {

    public static function init() : void {
        add_action( 'wp_ajax_ppa_preview', [ __CLASS__, 'handle_preview' ] );
        add_action( 'wp_ajax_ppa_store',   [ __CLASS__, 'handle_store' ] );
    }

    public static function handle_preview() : void { self::proxy_request( '/api/preview/' ); }
    public static function handle_store()   : void { self::proxy_request( '/api/store/' ); }

    /**
     * Proxy a request to the configured upstream preview/store endpoint.
     *
     * @param string $endpoint  Upstream endpoint path (e.g. /api/preview/)
     */
    private static function proxy_request( string $endpoint ) : void {
        // Nonce verification (must match wp_create_nonce used in admin JS)
        check_ajax_referer( 'ppa_admin', 'nonce' );

        // Capability check
        if ( ! current_user_can( 'edit_posts' ) ) {
            wp_send_json_error( [ 'message' => 'Insufficient capability' ], 403 );
        }

        // Get configured upstream server base URL from options
        $server_base = trim( (string) get_option( 'ppa_server_base', '' ) );
        if ( empty( $server_base ) ) {
            wp_send_json_error( [ 'message' => 'PPA server base not configured' ], 500 );
        }

        // Shared key (do not log). Prefer option, fall back to env if needed.
        $shared_key = trim( (string) get_option( 'ppa_shared_key', '' ) );
        if ( empty( $shared_key ) && defined( 'PPA_SHARED_KEY' ) ) {
            $shared_key = PPA_SHARED_KEY;
        }

        // Build upstream URL
        $server_base = rtrim( $server_base, '/' );
        $remote_url  = $server_base . $endpoint;

        // Prepare headers for upstream request
        $headers = [
            // include the shared key so upstream can authenticate the proxy call
            'X-PPA-Key'    => $shared_key,
            'X-PPA-Client' => 'wordpress-plugin',
            'X-PPA-Origin' => home_url(),
        ];

        // Preserve incoming Content-Type if present
        if ( ! empty( $_SERVER['CONTENT_TYPE'] ) ) {
            $headers['Content-Type'] = wp_unslash( (string) $_SERVER['CONTENT_TYPE'] );
        }

        // Prepare body: prefer raw php://input when present (this preserves JSON or other content-types),
        // otherwise forward sanitized $_POST array (form-encoded).
        $raw_input = file_get_contents( 'php://input' );
        $args = [
            'headers'     => $headers,
            'timeout'     => 20,
            'redirection' => 5,
            'blocking'    => true,
        ];

        if ( ! empty( $raw_input ) && strlen( trim( $raw_input ) ) > 0 ) {
            // Forward raw body and ensure Content-Type is set (already in $headers when available)
            $args['body'] = $raw_input;
        } else {
            // Forward POST data as an array (wp_remote_post will encode as form-data / urlencoded)
            // Strip known internal fields so we don't forward admin nonce & action to upstream
            $forward = $_POST;
            unset( $forward['action'], $forward['nonce'] );
            // Use wp_unslash to avoid double-escaping
            $sanitized = [];
            foreach ( $forward as $k => $v ) {
                $sanitized[ $k ] = is_array( $v ) ? array_map( 'wp_unslash', $v ) : wp_unslash( (string) $v );
            }
            $args['body'] = $sanitized;
        }

        // Make the remote request
        $response = wp_remote_post( $remote_url, $args );

        if ( is_wp_error( $response ) ) {
            // Respect your rule to not leak secrets. Return generic error to client.
            wp_send_json_error( [ 'message' => $response->get_error_message() ], 500 );
        }

        $code = (int) wp_remote_retrieve_response_code( $response );
        $body = wp_remote_retrieve_body( $response );

        // If preview endpoint, return the upstream body directly (raw HTML ideally)
        if ( stripos( $endpoint, '/api/preview' ) !== false ) {
            // If the upstream returned JSON with {status,body}, unwrap that structure.
            $decoded = null;
            if ( ! empty( $body ) ) {
                $maybe_json = json_decode( $body, true );
                if ( is_array( $maybe_json ) && array_key_exists( 'body', $maybe_json ) ) {
                    // prefer nested body if present
                    $html = (string) $maybe_json['body'];
                } else {
                    $html = (string) $body;
                }
            } else {
                $html = '';
            }

            // If we still have no HTML to return, provide a harmless HTML comment with diagnostic info
            if ( trim( $html ) === '' ) {
                $diag = sprintf(
                    '<!-- PPA Preview: upstream returned empty body (HTTP %d). Check upstream logs. -->',
                    $code
                );

                // If WP_DEBUG is enabled, include a little more context (non-secret)
                if ( defined( 'WP_DEBUG' ) && WP_DEBUG ) {
                    $diag .= sprintf(
                        "\n<!-- PPA DEBUG: forwarded to %s; forwarded-body-size=%d; content-type=%s -->",
                        esc_html( $remote_url ),
                        strlen( (string) $args['body'] ),
                        isset( $headers['Content-Type'] ) ? esc_html( $headers['Content-Type'] ) : 'unknown'
                    );
                }
                $html = $diag;
            }

            // Set Content-Type header to what upstream returned if possible, otherwise text/html
            $remote_headers = wp_remote_retrieve_headers( $response );
            $up_ct = '';
            if ( is_array( $remote_headers ) && ! empty( $remote_headers['content-type'] ) ) {
                $up_ct = (string) $remote_headers['content-type'];
            } elseif ( method_exists( $remote_headers, 'get' ) && $remote_headers->get( 'content-type' ) ) {
                $up_ct = (string) $remote_headers->get( 'content-type' );
            }

            if ( ! empty( $up_ct ) ) {
                // Make sure we only return a safe content type (avoid returning application/json when admin expects HTML).
                header( 'Content-Type: ' . $up_ct );
            } else {
                header( 'Content-Type: text/html; charset=utf-8' );
            }

            // Return raw HTML (or diagnostic comment) directly — admin JS will insert it.
            echo $html;
            wp_die();
        }

        // Non-preview endpoints: keep JSON wrapper for structured responses
        wp_send_json( [ 'status' => $code, 'body' => $body ], $code );
    }
}

endif;

PPA_Controller::init();
