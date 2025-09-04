<?php
/**
 * Plugin Name:  PostPress AI
 * Description:  Connect WordPress to your Django PostPress AI service for AI-assisted content (preview, save draft, publish).
 * Version:      1.0.0
 * Author:       Tech With Wayne
 * Text Domain:  postpress-ai
 * Requires PHP: 7.4
 * Requires WP:  6.0
 *
 * CHANGE LOG
 * ----------
 * 2025-08-21
 * - ADD: Required Composer UI file (inc/class-ppa-composer.php).                        # CHANGED:
 * - KEEP: Admin, Settings, Menu, Controller, Client, REST, Preserve modules intact.     # CHANGED:
 *
 * 2025-08-21 (hotfix)
 * - ADD: Always ensure AJAX handlers are registered by initializing PPA_Controller      # CHANGED:
 *        on 'init' when not already hooked. Safe-guarded with has_action() to avoid
 *        double registration. (No changes to your admin boot flow.)                     # CHANGED:
 */

if ( ! defined( 'ABSPATH' ) ) { exit; }

/** ========= CORE CONSTANTS ========= */
define( 'PPA_PLUGIN_FILE', __FILE__ );
define( 'PPA_PLUGIN_BASENAME', plugin_basename( __FILE__ ) );
define( 'PPA_PLUGIN_DIR', plugin_dir_path( __FILE__ ) );
define( 'PPA_PLUGIN_URL', plugin_dir_url( __FILE__ ) );

// Optional override for Composer submenu target
if ( ! defined( 'PPA_COMPOSER_SLUG' ) ) {
    define( 'PPA_COMPOSER_SLUG', 'ppa-composer' ); // CHANGED: points to new Composer class
}

/** ========= i18n ========= */
add_action( 'plugins_loaded', static function () {
    load_plugin_textdomain( 'postpress-ai', false, dirname( PPA_PLUGIN_BASENAME ) . '/languages' );
} );

/** ========= REQUIRE SUBMODULES ========= */
$__ppa_missing = [];

$__admin_file      = PPA_PLUGIN_DIR . 'inc/class-ppa-admin.php';
$__settings_file   = PPA_PLUGIN_DIR . 'inc/class-ppa-settings.php';
$__menu_file       = PPA_PLUGIN_DIR . 'inc/class-ppa-menu.php';
$__controller_file = PPA_PLUGIN_DIR . 'inc/class-ppa-controller.php';
$__client_file     = PPA_PLUGIN_DIR . 'inc/class-ppa-client.php';
$__rest_file       = PPA_PLUGIN_DIR . 'inc/class-ppa-rest.php';
$__preserve_file   = PPA_PLUGIN_DIR . 'inc/class-ppa-preserve-html.php';
$__composer_file   = PPA_PLUGIN_DIR . 'inc/class-ppa-composer.php'; // CHANGED

if ( file_exists( $__admin_file ) )      { require_once $__admin_file; }      else { $__ppa_missing[] = 'inc/class-ppa-admin.php'; }
if ( file_exists( $__settings_file ) )   { require_once $__settings_file; }   else { $__ppa_missing[] = 'inc/class-ppa-settings.php'; }
if ( file_exists( $__menu_file ) )       { require_once $__menu_file; }       else { $__ppa_missing[] = 'inc/class-ppa-menu.php'; }
if ( file_exists( $__client_file ) )     { require_once $__client_file; }     else { $__ppa_missing[] = 'inc/class-ppa-client.php'; }
if ( file_exists( $__controller_file ) ) { require_once $__controller_file; } else { $__ppa_missing[] = 'inc/class-ppa-controller.php'; }
if ( file_exists( $__rest_file ) )       { require_once $__rest_file; }       else { $__ppa_missing[] = 'inc/class-ppa-rest.php'; }
if ( file_exists( $__preserve_file ) )   { require_once $__preserve_file; }   else { $__ppa_missing[] = 'inc/class-ppa-preserve-html.php'; }
if ( file_exists( $__composer_file ) )   { require_once $__composer_file; }   else { $__ppa_missing[] = 'inc/class-ppa-composer.php'; } // CHANGED

/** ========= ENSURE AJAX HANDLERS EXIST (front+admin+ajax) =========
 * We register PPA_Controller hooks on every request. If the controller file already
 * auto-initializes itself, this guard prevents double registration.                    # CHANGED:
 */
add_action( 'init', static function () {                                                // CHANGED:
    if ( class_exists( 'PPA_Controller' )                                              // CHANGED:
         && ! has_action( 'wp_ajax_ppa_preview', array( 'PPA_Controller', 'ajax_preview' ) ) ) { // CHANGED:
        // SECURITY: Nonce + capability checks live inside the controller.             // CHANGED:
        PPA_Controller::init();                                                        // CHANGED:
    }
} );                                                                                   // CHANGED:

/** ========= BOOT (ADMIN ONLY) ========= */
add_action( 'plugins_loaded', static function () use ( $__ppa_missing ) {
    if ( ! is_admin() ) { return; }

    if ( ! empty( $__ppa_missing ) ) {
        add_action( 'admin_notices', static function () use ( $__ppa_missing ) {
            echo '<div class="notice notice-error"><p><strong>PostPress AI:</strong> Missing files — ';
            echo esc_html( implode( ', ', $__ppa_missing ) );
            echo '. Upload these into <code>wp-content/plugins/postpress-ai/</code> and reload.</p></div>';
        } );
    }

    if ( class_exists( 'PPA_Admin' ) )    { PPA_Admin::init(); }
    if ( class_exists( 'PPA_Settings' ) ) { PPA_Settings::init(); }
    if ( class_exists( 'PPA_Menu' ) )     { PPA_Menu::init(); }
});

/** ========= PLUGINS LIST: "Settings" ACTION LINK ========= */
add_filter( 'plugin_action_links_' . PPA_PLUGIN_BASENAME, static function( array $links ) : array {
    $url = admin_url( 'options-general.php?page=postpress-ai-settings' );
    $settings_link = '<a href="' . esc_url( $url ) . '">' . esc_html__( 'Settings', 'postpress-ai' ) . '</a>';
    array_unshift( $links, $settings_link );
    return $links;
});
