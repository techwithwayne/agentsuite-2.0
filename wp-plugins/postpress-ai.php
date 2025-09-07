<?php
/**
 * Plugin Name:  PostPress AI
 * Description:  Admin composer + preview bridge for PostPress AI.
 * Version:      0.0.0-hotfix2
 * Author:       Tech With Wayne
 * Text Domain:  postpress-ai
 */
if (!defined('ABSPATH')) { exit; }

if (!defined('PPA_PLUGIN_FILE'))     define('PPA_PLUGIN_FILE', __FILE__);
if (!defined('PPA_PLUGIN_BASENAME')) define('PPA_PLUGIN_BASENAME', plugin_basename(__FILE__));
if (!defined('PPA_PLUGIN_DIR'))      define('PPA_PLUGIN_DIR', plugin_dir_path(__FILE__));
if (!defined('PPA_PLUGIN_URL'))      define('PPA_PLUGIN_URL', plugin_dir_url(__FILE__));
if (!defined('PPA_VERSION'))         define('PPA_VERSION', '0.0.0-hotfix2');
if (!defined('PPA_COMPOSER_SLUG'))   define('PPA_COMPOSER_SLUG', 'ppa-composer');

/** Require submodules if present (no fatals if missing) */
$need = [
  'inc/class-ppa-admin.php',
  'inc/class-ppa-settings.php',
  'inc/class-ppa-menu.php',
  'inc/class-ppa-composer.php',
  'inc/class-ppa-client.php',
  'inc/class-ppa-preserve-html.php',
  'inc/class-ppa-rest.php',
  // Controller introduced under /includes in current builds:
  'inc/class-ppa-controller.php',
];
foreach ($need as $rel) {
  $path = PPA_PLUGIN_DIR . $rel;
  if (file_exists($path)) { require_once $path; }
}

/** i18n */
add_action('plugins_loaded', static function () {
  load_plugin_textdomain('postpress-ai', false, dirname(PPA_PLUGIN_BASENAME).'/languages');
});

/** Ensure AJAX handlers are registered */
add_action('init', static function () {
  if (class_exists('PPA_Controller') && method_exists('PPA_Controller','init')) {
    PPA_Controller::init();
  } else {
    if (class_exists('PPA_Controller') && is_callable(['PPA_Controller','ajax_preview'])) {
      add_action('wp_ajax_ppa_preview',        ['PPA_Controller','ajax_preview']);
      add_action('wp_ajax_nopriv_ppa_preview', ['PPA_Controller','ajax_preview']);
    }
    if (class_exists('PPA_Controller') && is_callable(['PPA_Controller','ajax_store'])) {
      add_action('wp_ajax_ppa_store', ['PPA_Controller','ajax_store']);
    }
  }
});

/** Boot admin (menu, assets, settings) */
add_action('plugins_loaded', static function () {
  if (!is_admin()) return;
  if (class_exists('PPA_Admin')    && method_exists('PPA_Admin','init'))    PPA_Admin::init();
  if (class_exists('PPA_Settings') && method_exists('PPA_Settings','init')) PPA_Settings::init();
  if (class_exists('PPA_Menu')     && method_exists('PPA_Menu','init'))     PPA_Menu::init();
});

/** Plugins list: Settings link */
add_filter('plugin_action_links_' . PPA_PLUGIN_BASENAME, static function(array $links): array {
  $url = admin_url('options-general.php?page=postpress-ai-settings');
  array_unshift($links, '<a href="'.esc_url($url).'">'.esc_html__('Settings','postpress-ai').'</a>');
  return $links;
});
