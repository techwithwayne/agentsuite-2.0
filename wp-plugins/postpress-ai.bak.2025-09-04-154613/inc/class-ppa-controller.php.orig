<?php
/**
 * PostPress AI — AJAX Proxy Controller
 * Path: /wp-content/plugins/postpress-ai/inc/class-ppa-controller.php
 *
 * CHANGE LOG
 * ----------
 * 2025-08-27
 * - CHANGED: Removed hardcoded Django URL.
 * - CHANGED: Uses options ppa_server_base / ppa_project_key.
 * - CHANGED: Injects headers (X-PPA-Key, X-PPA-Client, X-PPA-Origin).
 * - CHANGED: Nonce + capability checks.
 * - CHANGED: Returns clear JSON for missing config.
 */

if ( ! defined( 'ABSPATH' ) ) { exit; }

if ( ! class_exists( 'PPA_Controller' ) ):
final class PPA_Controller {

    public static function init() : void {
        add_action( 'wp_ajax_ppa_preview', [ __CLASS__, 'handle_preview' ] );
        add_action( 'wp_ajax_ppa_store',   [ __CLASS__, 'handle_store' ] );
    }

    public static function handle_preview() : void { self::proxy_request( '/api/preview/' ); }
    public static function handle_store()   : void { self::proxy_request( '/api/store/' ); }

    private static function proxy_request( string $endpoint ) : void {
        check_ajax_referer( 'ppa_nonce', 'nonce' );

        if ( ! current_user_can( 'ppa_use' ) && ! current_user_can( 'edit_posts' ) ) {
            wp_send_json_error( [ 'message' => 'Permission denied' ], 403 );
        }

        $base = rtrim( get_option( 'ppa_server_base', '' ), '/' );
        $key  = get_option( 'ppa_project_key', '' );

        if ( empty( $base ) || empty( $key ) ) {
            wp_send_json_error( [
                'message' => 'PostPress AI is not connected. Set Server Base & Project Key in PostPress AI → Settings.'
            ], 400 );
        }

        $payload = wp_unslash( $_POST );
        unset( $payload['action'], $payload['nonce'] );

        $args = [
            'headers' => [
                'X-PPA-Key'    => $key,
                'X-PPA-Client' => 'postpress-ai/' . ( defined( 'PPA_VERSION' ) ? PPA_VERSION : 'dev' ),
                'X-PPA-Origin' => home_url(),
            ],
            'timeout' => 30,
            'body'    => $payload,
        ];

        $response = wp_remote_post( $base . $endpoint, $args );

        if ( is_wp_error( $response ) ) {
            wp_send_json_error( [ 'message' => $response->get_error_message() ], 500 );
        }

        $code = wp_remote_retrieve_response_code( $response );
        $body = wp_remote_retrieve_body( $response );

        wp_send_json( [ 'status' => $code, 'body' => $body ] );
    }
}
endif;

PPA_Controller::init();
