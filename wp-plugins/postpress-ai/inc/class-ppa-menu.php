<?php
/**
 * PostPress AI — Admin Menu (top-level + submenus)
 * Path: /home/customer/www/techwithwayne.com/public_html/wp-content/plugins/postpress-ai/inc/class-ppa-menu.php
 *
 * CHANGE LOG
 * ----------
 * 2025-08-21
 * - FIX: Wire Composer submenu directly to PPA_Composer::render_page().              # CHANGED:
 * - KEEP: Settings proxy intact.                                                     # CHANGED:
 */

if ( ! defined( 'ABSPATH' ) ) { exit; }

if ( ! class_exists( 'PPA_Menu' ) ):

final class PPA_Menu {

    /** Unified top-level slug */
    const MENU_SLUG = 'postpress-ai';

    public static function init() : void {
        add_action( 'admin_menu', [ __CLASS__, 'register_menu' ] );
    }

    public static function register_menu() : void {
        // ===== Top-level: Settings proxy
        add_menu_page(
            __( 'PostPress AI', 'postpress-ai' ),
            __( 'PostPress AI', 'postpress-ai' ),
            'manage_options',
            self::MENU_SLUG,
            [ __CLASS__, 'render_settings_proxy' ],
            'dashicons-admin-generic',
            58
        );

        // ===== Submenu: Composer
        add_submenu_page(
            self::MENU_SLUG,
            __( 'Composer', 'postpress-ai' ),
            __( 'Composer', 'postpress-ai' ),
            'manage_options',
            'ppa-composer',                               // CHANGED
            [ 'PPA_Composer', 'render_page' ]             // CHANGED
        );

        // ===== Submenu: Settings
        add_submenu_page(
            self::MENU_SLUG,
            __( 'Settings', 'postpress-ai' ),
            __( 'Settings', 'postpress-ai' ),
            'manage_options',
            'postpress-ai-settings',
            [ __CLASS__, 'render_settings_proxy' ]
        );
    }

    public static function render_settings_proxy() : void {
        if ( ! current_user_can( 'manage_options' ) ) {
            wp_die( esc_html__( 'You do not have permission to access this page.', 'postpress-ai' ) );
        }
        if ( class_exists( 'PPA_Settings' ) && is_callable( [ 'PPA_Settings', 'render_page' ] ) ) {
            PPA_Settings::render_page();
            return;
        }
        echo '<div class="wrap"><h1>PostPress AI</h1><div class="notice notice-error"><p>';
        echo esc_html__( 'Settings module missing. Ensure inc/class-ppa-settings.php is present and required.', 'postpress-ai' );
        echo '</p></div></div>';
    }
}

endif;
