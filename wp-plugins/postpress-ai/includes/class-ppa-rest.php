<?php
/**
 * Legacy compatibility shim for:
 *   includes/class-ppa-rest.php → inc/class-ppa-rest.php
 *
 * CHANGE LOG
 * ----------
 * 2025-08-22
 * - NEW: Forwarder to inc/class-ppa-rest.php.                                      # CHANGED:
 */

if ( ! defined( 'ABSPATH' ) ) { exit; }
if ( ! defined( 'PPA_PLUGIN_DIR' ) ) {
    define( 'PPA_PLUGIN_DIR', trailingslashit( dirname( dirname( __FILE__ ) ) ) );
}
$target = PPA_PLUGIN_DIR . 'inc/class-ppa-rest.php';
if ( file_exists( $target ) ) { require_once $target; }
else {
    if ( is_admin() && function_exists( 'add_action' ) ) {
        add_action( 'admin_notices', static function () use ( $target ) {
            echo '<div class="notice notice-error"><p><strong>PostPress AI:</strong> Missing file ';
            echo esc_html( $target );
            echo '.</p></div>';
        } );
    }
    if ( defined('WP_DEBUG_LOG') && WP_DEBUG_LOG ) { error_log('[PPA][includes-shim] Missing target: ' . $target); }
}
