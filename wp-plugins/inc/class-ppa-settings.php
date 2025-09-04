<?php
/**
 * PostPress AI — Settings Page + Connectivity Tester
 * Path: /home/u3007-tenkoaygp3je/www/techwithwayne.com/public_html/wp-content/plugins/postpress-ai/inc/class-ppa-settings.php
 *
 * CHANGE LOG
 * ----------
 * 2025-08-20
 * - NEW: Adds Settings page under Settings → PostPress AI (slug: postpress-ai-settings).        # CHANGED:
 * - NEW: Fields: Django Base URL (https), Shared Secret (masked; never echoed), HTTP Timeout.   # CHANGED:
 * - NEW: "Test Connectivity" button (server-side) calling /version/ and /health/ on Django.     # CHANGED:
 * - UX:  Settings page uses .ppa-admin wrappers so it picks up the same CSS/JS as Composer.     # CHANGED:
 * - SAFETY: Empty Shared Secret input will NOT erase the stored secret (pre_update_option hook). # CHANGED:
 * - SECURITY: Requires manage_options; nonces on POST; no raw secrets printed anywhere.         # CHANGED:
 */

if ( ! defined( 'ABSPATH' ) ) { exit; }

if ( ! class_exists( 'PPA_Settings' ) ):

final class PPA_Settings {

    // Option names kept consistent with controller usage.
    const OPTION_BASE = 'ppa_server_base';   // e.g., https://techwithwayne.pythonanywhere.com
    const OPTION_KEY  = 'ppa_shared_key';    // sent as X-PPA-Key (server-side only)
    const OPTION_TO   = 'ppa_http_timeout';  // integer seconds

    const NONCE_TEST  = 'ppa_settings_test';

    /**
     * Bootstrap: register menu, settings, test handler, and "do not wipe key on blank" guard.
     */
    public static function init() : void {                                                     // CHANGED:
        add_action( 'admin_menu',  [ __CLASS__, 'register_menu' ] );                           // CHANGED:
        add_action( 'admin_init',  [ __CLASS__, 'register_settings' ] );                       // CHANGED:
        add_action( 'admin_post_ppa_test_connectivity', [ __CLASS__, 'handle_test_connectivity' ] ); // CHANGED:
        add_filter( 'pre_update_option_' . self::OPTION_KEY, [ __CLASS__, 'preserve_secret_if_blank' ], 10, 2 ); // CHANGED:
        self::ensure_defaults();                                                               // CHANGED:
    }

    /**
     * Create options with autoload = no (keeps wp_options lightweight).
     */
    private static function ensure_defaults() : void {                                         // CHANGED:
        if ( false === get_option( self::OPTION_BASE, false ) ) {
            add_option( self::OPTION_BASE, '', '', 'no' );                                     // CHANGED:
        }
        if ( false === get_option( self::OPTION_KEY, false ) ) {
            add_option( self::OPTION_KEY, '', '', 'no' );                                      // CHANGED:
        }
        if ( false === get_option( self::OPTION_TO, false ) ) {
            add_option( self::OPTION_TO, 15, '', 'no' );                                       // CHANGED:
        }
    }

    /**
     * Register "Settings → PostPress AI". (Proper URL is options-general.php?page=postpress-ai-settings)
     * Using add_options_page ensures correct permissions UI and avoids "not allowed" with admin.php links.
     */
    public static function register_menu() : void {                                            // CHANGED:
        add_options_page(
            __( 'PostPress AI Settings', 'postpress-ai' ),
            __( 'PostPress AI', 'postpress-ai' ),
            'manage_options',
            'postpress-ai-settings',
            [ __CLASS__, 'render_page' ]
        );
    }

    /**
     * Register settings and sanitizers.
     */
    public static function register_settings() : void {                                        // CHANGED:
        register_setting(
            'postpress_ai',
            self::OPTION_BASE,
            [ 'type' => 'string', 'sanitize_callback' => [ __CLASS__, 'sanitize_base_url' ] ]
        );
        register_setting(
            'postpress_ai',
            self::OPTION_KEY,
            [ 'type' => 'string', 'sanitize_callback' => [ __CLASS__, 'sanitize_secret' ] ]
        );
        register_setting(
            'postpress_ai',
            self::OPTION_TO,
            [ 'type' => 'integer', 'sanitize_callback' => [ __CLASS__, 'sanitize_timeout' ] ]
        );
    }

    /**
     * If the admin leaves the Shared Secret field blank, DO NOT wipe the stored key.
     * This prevents accidental loss of credentials when saving other settings.
     */
    public static function preserve_secret_if_blank( $new_value, $old_value ) {                // CHANGED:
        // Only preserve when explicitly blank; admins can erase by typing a single dash "-" if needed.
        if ( is_string( $new_value ) && trim( $new_value ) === '' ) {                          // CHANGED:
            return $old_value;                                                                 // CHANGED:
        }
        // Allow explicit wipe using a sentinel; sanitize later will trim it away to blank if needed.
        if ( $new_value === '-' ) { return ''; }                                               // CHANGED:
        return $new_value;                                                                     // CHANGED:
    }

    /** Sanitize: enforce https, strip trailing slash. */
    public static function sanitize_base_url( $raw ) : string {                                // CHANGED:
        $u = trim( (string) $raw );
        if ( $u === '' ) { return ''; }
        $u = esc_url_raw( $u );
        if ( stripos( $u, 'https://' ) !== 0 ) {
            add_settings_error( self::OPTION_BASE, 'ppa_base_https', __( 'Base URL must start with https://', 'postpress-ai' ), 'error' );
            return '';
        }
        return rtrim( $u, '/' );
    }

    /** Sanitize: keep as-is; trimming whitespace only. */
    public static function sanitize_secret( $raw ) : string {                                  // CHANGED:
        return trim( (string) $raw );
    }

    /** Sanitize: clamp timeout to [5..60] seconds. */
    public static function sanitize_timeout( $raw ) : int {                                    // CHANGED:
        $n = intval( $raw );
        if ( $n < 5 )  { $n = 5;  }
        if ( $n > 60 ) { $n = 60; }
        return $n;
    }

    /** Utility: mask a secret for display (show last 4). Never echo the real value. */
    private static function mask_secret( string $s ) : string {                                 // CHANGED:
        if ( $s === '' ) { return ''; }
        $len = strlen( $s );
        if ( $len <= 4 ) { return str_repeat( '•', max(0,$len-1) ) . substr( $s, -1 ); }
        return str_repeat( '•', $len - 4 ) . substr( $s, -4 );
    }

    /**
     * Render the Settings page.
     * NOTE: The outer wrappers (.ppa-admin, .ppa-card) let this page inherit the same
     * styles/scripts your composer screen uses. Your enqueuer should target screen ids
     * containing "postpress-ai" so both pages share CSS/JS.
     */
    public static function render_page() : void {                                              // CHANGED:
        if ( ! current_user_can( 'manage_options' ) ) {
            wp_die( esc_html__( 'You do not have permission to access this page.', 'postpress-ai' ) );
        }

        $base = get_option( self::OPTION_BASE, '' );
        $key  = get_option( self::OPTION_KEY,  '' );
        $to   = intval( get_option( self::OPTION_TO, 15 ) );

        settings_errors();
        ?>
        <div id="ppa-settings" class="wrap ppa-admin"><!-- share composer styles -->           <!-- CHANGED -->
            <h1><?php echo esc_html__( 'PostPress AI Settings', 'postpress-ai' ); ?></h1>

            <form method="post" action="options.php" class="ppa-card" style="max-width: 900px;">
                <?php
                    settings_fields( 'postpress_ai' );   // nonce + group
                    do_settings_sections( 'postpress_ai' );
                ?>

                <table class="form-table" role="presentation">
                    <tbody>
                        <tr>
                            <th scope="row"><label for="ppa_server_base"><?php esc_html_e( 'Django Base URL', 'postpress-ai' ); ?></label></th>
                            <td>
                                <input name="<?php echo esc_attr( self::OPTION_BASE ); ?>" id="ppa_server_base" type="url"
                                       class="regular-text code"
                                       placeholder="https://techwithwayne.pythonanywhere.com"
                                       value="<?php echo esc_attr( $base ); ?>" />
                                <p class="description">
                                    <?php esc_html_e( 'Example: https://techwithwayne.pythonanywhere.com (no trailing slash).', 'postpress-ai' ); ?>
                                </p>
                            </td>
                        </tr>

                        <tr>
                            <th scope="row"><label for="ppa_shared_key"><?php esc_html_e( 'Shared Secret', 'postpress-ai' ); ?></label></th>
                            <td>
                                <input name="<?php echo esc_attr( self::OPTION_KEY ); ?>" id="ppa_shared_key" type="password"
                                       class="regular-text"
                                       autocomplete="new-password"
                                       placeholder="<?php echo esc_attr( $key ? self::mask_secret( $key ) : '••••••••' ); ?>" />
                                <p class="description">
                                    <?php esc_html_e( 'Sent as X-PPA-Key in server-to-server requests. Leave blank to keep existing secret. Enter "-" to clear.', 'postpress-ai' ); ?>
                                </p>
                            </td>
                        </tr>

                        <tr>
                            <th scope="row"><label for="ppa_http_timeout"><?php esc_html_e( 'HTTP Timeout (seconds)', 'postpress-ai' ); ?></label></th>
                            <td>
                                <input name="<?php echo esc_attr( self::OPTION_TO ); ?>" id="ppa_http_timeout" type="number" min="5" max="60"
                                       value="<?php echo esc_attr( $to ); ?>" />
                                <p class="description">
                                    <?php esc_html_e( 'How long WordPress waits for Django before failing the request.', 'postpress-ai' ); ?>
                                </p>
                            </td>
                        </tr>
                    </tbody>
                </table>

                <?php submit_button( __( 'Save Settings', 'postpress-ai' ) ); ?>
            </form>

            <div class="ppa-card" style="max-width: 900px; margin-top: 16px;">
                <h2><?php esc_html_e( 'Connectivity', 'postpress-ai' ); ?></h2>
                <p><?php esc_html_e( 'Run a server-side check to confirm Django is reachable from WordPress.', 'postpress-ai' ); ?></p>
                <form method="post" action="<?php echo esc_url( admin_url( 'admin-post.php' ) ); ?>">
                    <input type="hidden" name="action" value="ppa_test_connectivity" />
                    <?php wp_nonce_field( self::NONCE_TEST ); ?>
                    <?php submit_button( __( 'Test Connectivity', 'postpress-ai' ), 'secondary', 'submit', false ); ?>
                </form>
            </div>
        </div>
        <?php
    }

    /**
     * Handle "Test Connectivity": GET /version/ then /health/ on Django.
     * Never prints secrets; adds admin notices with a short summary.
     */
    public static function handle_test_connectivity() : void {                                 // CHANGED:
        if ( ! current_user_can( 'manage_options' ) ) {
            wp_die( esc_html__( 'Insufficient permissions.', 'postpress-ai' ) );
        }
        check_admin_referer( self::NONCE_TEST );

        $base = rtrim( (string) get_option( self::OPTION_BASE, '' ), '/' );
        $key  = (string) get_option( self::OPTION_KEY,  '' );
        $to   = intval( get_option( self::OPTION_TO, 15 ) );

        if ( $base === '' ) {
            add_settings_error( 'ppa_connect', 'ppa_base_missing', __( 'Set the Django Base URL first.', 'postpress-ai' ), 'error' );
            wp_safe_redirect( admin_url( 'options-general.php?page=postpress-ai-settings' ) );
            exit;
        }

        $headers = [
            'Accept'       => 'application/json',
            'Content-Type' => 'application/json',
        ];
        if ( $key !== '' ) {
            $headers['X-PPA-Key'] = $key; // sent server-side only
        }

        $endpoints = [
            'version' => $base . '/postpress-ai/version/',
            'health'  => $base . '/postpress-ai/health/',
        ];

        $results = [];
        foreach ( $endpoints as $name => $url ) {
            $resp = wp_remote_get( $url, [
                'headers'   => $headers,
                'timeout'   => $to,
                'sslverify' => true,
            ] );
            if ( is_wp_error( $resp ) ) {
                $results[ $name ] = [ 'ok' => false, 'error' => $resp->get_error_message() ];
            } else {
                $code = wp_remote_retrieve_response_code( $resp );
                $body = wp_remote_retrieve_body( $resp );
                $json = json_decode( $body, true );
                $results[ $name ] = [ 'ok' => ( $code >= 200 && $code < 300 ), 'status' => $code, 'body' => is_array( $json ) ? $json : null ];
            }
        }

        $ok_version = ! empty( $results['version']['ok'] );
        $ok_health  = ! empty( $results['health']['ok'] );

        if ( $ok_version && $ok_health ) {
            add_settings_error(
                'ppa_connect', 'ppa_connect_ok',
                __( 'Connectivity OK: version and health endpoints responded.', 'postpress-ai' ),
                'updated'
            );
        } else {
            $msg = sprintf(
                'Connectivity issues. version=%s status=%s; health=%s status=%s',
                $ok_version ? 'ok' : 'fail',
                isset( $results['version']['status'] ) ? intval( $results['version']['status'] ) : '-',
                $ok_health ? 'ok' : 'fail',
                isset( $results['health']['status'] ) ? intval( $results['health']['status'] ) : '-'
            );
            add_settings_error( 'ppa_connect', 'ppa_connect_fail', esc_html( $msg ), 'error' );
        }

        wp_safe_redirect( admin_url( 'options-general.php?page=postpress-ai-settings' ) );
        exit;
    }
}

endif;
