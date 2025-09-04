<?php
/**
 * PostPress AI — Composer Admin Page
 * Path: /home/customer/www/techwithwayne.com/public_html/wp-content/plugins/postpress-ai/inc/class-ppa-composer.php
 *
 * CHANGE LOG
 * ----------
 * 2025-08-24: Expanded Content Types in form (added Case Study, Product Description, Newsletter, Whitepaper, Landing Page, FAQ, Press Release). # CHANGED:
 * 2025-08-24: Removed inline <style> and moved all Composer CSS into assets/css/admin.css. # CHANGED:
 *             Scoped styling under body.postpress-ai_page_ppa-composer.                   # CHANGED:
 */

if ( ! defined( 'ABSPATH' ) ) { exit; }

if ( ! class_exists( 'PPA_Composer' ) ) :

final class PPA_Composer {

	/**
	 * Render the admin page with tabs (Compose / History).
	 */
	public static function render_page() : void {
		if ( ! current_user_can( 'edit_posts' ) ) {
			wp_die( esc_html__( 'You do not have permission to access this page.', 'postpress-ai' ) );
		}

		$active = isset( $_GET['tab'] ) ? sanitize_key( wp_unslash( $_GET['tab'] ) ) : 'compose';
		if ( ! in_array( $active, [ 'compose', 'history' ], true ) ) {
			$active = 'compose';
		}

		$compose_url = esc_url( add_query_arg( [ 'page' => 'ppa-composer', 'tab' => 'compose' ], admin_url( 'admin.php' ) ) );
		$history_url = esc_url( add_query_arg( [ 'page' => 'ppa-composer', 'tab' => 'history' ], admin_url( 'admin.php' ) ) );

		echo '<div class="wrap ppa-admin ppa-wrap">';
		echo '<h1 class="ppa-title">' . esc_html__( 'PostPress AI — Composer', 'postpress-ai' ) . '</h1>';

		// Tabs
		echo '<h2 class="nav-tab-wrapper">';
		echo '<a class="nav-tab ' . ( $active === 'compose' ? 'nav-tab-active' : '' ) . '" href="' . $compose_url . '">' . esc_html__( 'Compose', 'postpress-ai' ) . '</a>';
		echo '<a class="nav-tab ' . ( $active === 'history' ? 'nav-tab-active' : '' ) . '" href="' . $history_url . '">' . esc_html__( 'History', 'postpress-ai' ) . '</a>';
		echo '</h2>';

		// Content
		if ( $active === 'history' ) {
			self::render_history_tab();
		} else {
			self::render_compose_tab();
		}

		echo '</div>'; // .wrap
	}

	/**
	 * Compose tab (form left, preview right).
	 */
	private static function render_compose_tab() : void {
		$nonce = wp_create_nonce( 'ppa_admin' );

		echo '<div class="ppa-grid">';

		// Left: form
		echo '<div class="ppa-col"><div class="ppa-card">';
		echo '<h2>' . esc_html__( 'Compose', 'postpress-ai' ) . '</h2>';
		echo '<form id="ppa-composer-form" class="ppa-form" method="post" data-ppa-autopreview="0">';
		printf( '<input type="hidden" id="ppa-nonce" name="nonce" value="%s" />', esc_attr( $nonce ) );

		// Subject
		echo '<p class="ppa-field">';
		echo '<label for="ppa-subject"><strong>' . esc_html__( 'Subject', 'postpress-ai' ) . '</strong></label>';
		echo '<input type="text" id="ppa-subject" name="subject" class="regular-text" placeholder="' . esc_attr__( 'e.g., 10 quick tips for speeding up your site', 'postpress-ai' ) . '"/>';
		echo '</p>';

		// Content type
		echo '<p class="ppa-field">';
		echo '<label for="ppa-genre"><strong>' . esc_html__( 'Content Type', 'postpress-ai' ) . '</strong></label>';
		echo '<select id="ppa-genre" name="genre" class="regular-text">';
		echo '<option value="blog">' . esc_html__( 'Blog Post', 'postpress-ai' ) . '</option>';
		echo '<option value="email">' . esc_html__( 'Email', 'postpress-ai' ) . '</option>';
		echo '<option value="social">' . esc_html__( 'Social Post', 'postpress-ai' ) . '</option>';
		echo '<option value="case-study">' . esc_html__( 'Case Study', 'postpress-ai' ) . '</option>';           # CHANGED:
		echo '<option value="product-description">' . esc_html__( 'Product Description', 'postpress-ai' ) . '</option>'; # CHANGED:
		echo '<option value="newsletter">' . esc_html__( 'Newsletter', 'postpress-ai' ) . '</option>';           # CHANGED:
		echo '<option value="whitepaper">' . esc_html__( 'Whitepaper', 'postpress-ai' ) . '</option>';           # CHANGED:
		echo '<option value="landing-page">' . esc_html__( 'Landing Page', 'postpress-ai' ) . '</option>';       # CHANGED:
		echo '<option value="faq">' . esc_html__( 'FAQ', 'postpress-ai' ) . '</option>';                         # CHANGED:
		echo '<option value="press-release">' . esc_html__( 'Press Release', 'postpress-ai' ) . '</option>';     # CHANGED:
		echo '</select>';
		echo '</p>';

		// Tone
		echo '<p class="ppa-field">';
		echo '<label for="ppa-tone"><strong>' . esc_html__( 'Tone', 'postpress-ai' ) . '</strong></label>';
		echo '<input type="text" id="ppa-tone" name="tone" class="regular-text" placeholder="' . esc_attr__( 'e.g., casual, friendly', 'postpress-ai' ) . '"/>';
		echo '</p>';

		// Audience
		echo '<p class="ppa-field">';
		echo '<label for="ppa-audience"><strong>' . esc_html__( 'Target Audience', 'postpress-ai' ) . '</strong></label>';
		echo '<input type="text" id="ppa-audience" name="audience" class="regular-text" placeholder="' . esc_attr__( 'e.g., small business owners in Iowa', 'postpress-ai' ) . '"/>';
		echo '</p>';

		// Keywords
		echo '<p class="ppa-field">';
		echo '<label for="ppa-keywords"><strong>' . esc_html__( 'Keywords', 'postpress-ai' ) . '</strong></label>';
		echo '<input type="text" id="ppa-keywords" name="keywords" class="regular-text" placeholder="' . esc_attr__( 'comma,separated,terms', 'postpress-ai' ) . '"/>';
		echo '</p>';

		// Word count
		echo '<p class="ppa-field">';
		echo '<label for="ppa-length"><strong>' . esc_html__( 'Word Count', 'postpress-ai' ) . '</strong></label>';
		echo '<input type="number" id="ppa-length" name="length" class="small-text" min="100" step="50" placeholder="1200" />';
		echo '</p>';

		// CTA (optional)
		echo '<p class="ppa-field">';
		echo '<label for="ppa-cta"><strong>' . esc_html__( 'Call to Action (optional)', 'postpress-ai' ) . '</strong></label>';
		echo '<input type="text" id="ppa-cta" name="cta" class="regular-text" placeholder="' . esc_attr__( 'e.g., Grab a free consultation today', 'postpress-ai' ) . '"/>';
		echo '</p>';

		// Actions
		echo '<div class="ppa-actions">';
		echo '<button type="button" id="ppa-preview-btn" class="button button-secondary">' . esc_html__( 'Preview', 'postpress-ai' ) . '</button>';
		echo '<button type="button" id="ppa-save-btn" class="button button-secondary">' . esc_html__( 'Save as Draft', 'postpress-ai' ) . '</button>';
		echo '<button type="button" id="ppa-publish-btn" class="button button-primary">' . esc_html__( 'Publish', 'postpress-ai' ) . '</button>';
		echo '</div>';

		echo '</form>';
		echo '</div></div>';

		// Right: preview
		echo '<div class="ppa-col"><div class="ppa-card">';
		echo '<h2>' . esc_html__( 'Preview', 'postpress-ai' ) . '</h2>';

		echo '<div id="ppa-preview-window" aria-busy="false">';
		// Preloader overlay
		echo '<div class="ppa-preloader" aria-hidden="true">';
		echo '  <div class="ppa-lds-spinner">';
		for ( $i = 0; $i < 12; $i++ ) {
			echo '<div></div>';
		}
		echo '  </div>';
		echo '  <div class="ppa-preloader-label">' . esc_html__( 'Generating preview…', 'postpress-ai' ) . '</div>';
		echo '</div>'; // .ppa-preloader
		echo '</div>'; // #ppa-preview-window

		echo '</div></div>'; // .ppa-card / .ppa-col

		echo '</div>'; // .ppa-grid
	}

	/**
	 * History tab — shows recent AI content with Tokens & Cost columns.
	 */
	private static function render_history_tab() : void {
		echo '<div class="ppa-card">';
		echo '<h2>' . esc_html__( 'Recent AI Content', 'postpress-ai' ) . '</h2>';

		$args = [
			'numberposts' => 20,
			'post_type'   => 'post',
			'orderby'     => 'date',
			'order'       => 'DESC',
		];

		$posts = get_posts( $args );

		if ( empty( $posts ) ) {
			echo '<p>' . esc_html__( 'No recent items found.', 'postpress-ai' ) . '</p>';
			echo '</div>';
			return;
		}

		echo '<table class="widefat striped fixed">';
		echo '<thead><tr>';
		echo '<th style="width:120px">' . esc_html__( 'Date', 'postpress-ai' ) . '</th>';
		echo '<th>' . esc_html__( 'Title', 'postpress-ai' ) . '</th>';
		echo '<th style="width:100px">' . esc_html__( 'Status', 'postpress-ai' ) . '</th>';
		echo '<th style="width:100px;text-align:right">' . esc_html__( 'Tokens', 'postpress-ai' ) . '</th>';
		echo '<th style="width:120px;text-align:right">' . esc_html__( 'Cost (USD)', 'postpress-ai' ) . '</th>';
		echo '<th style="width:80px">' . esc_html__( 'Edit', 'postpress-ai' ) . '</th>';
		echo '</tr></thead>';

		echo '<tbody>';
		foreach ( $posts as $p ) :
			$post_id = intval( $p->ID );
			$edit_url = esc_url( admin_url( 'post.php?post=' . $post_id . '&action=edit' ) );
			$status = get_post_status( $post_id );
			$date = esc_html( get_the_date( 'Y-m-d', $post_id ) );
			$title = esc_html( get_the_title( $post_id ) );

			$tokens = get_post_meta( $post_id, '_ppa_tokens', true );
			$cost   = get_post_meta( $post_id, '_ppa_cost', true );

			$tokens_disp = is_numeric( $tokens ) ? number_format( (int) $tokens ) : '&mdash;';
			if ( is_numeric( $cost ) ) {
				$cost_val = floatval( $cost );
				$cost_disp = number_format( $cost_val, 4, '.', '' );
			} else {
				$cost_disp = '&mdash;';
			}

			echo '<tr>';
			echo '<td>' . $date . '</td>';
			echo '<td>' . $title . '</td>';
			echo '<td>' . esc_html( $status ? $status : '' ) . '</td>';
			echo '<td style="text-align:right">' . $tokens_disp . '</td>';
			echo '<td style="text-align:right">$' . $cost_disp . '</td>';
			echo '<td><a class="button button-small" href="' . $edit_url . '">' . esc_html__( 'Open', 'postpress-ai' ) . '</a></td>';
			echo '</tr>';
		endforeach;
		echo '</tbody>';
		echo '</table>';

		echo '</div>'; // .ppa-card
	}
}

endif;
