<?php
# CHANGED: 2025-09-04 - add temporary preview fallback using submitted title when upstream ignores it; add debug logging of forwarded fields (no secrets)
/**
 * PPA_Controller - AJAX proxy for PostPress AI
 *
 * CHANGE LOG
 * 2025-09-04:
 *  - TEMP: If upstream preview HTML does not include submitted title, return a generated HTML snippet containing the title (unblock preview).
 *  - DEBUG: When WP_DEBUG is enabled, append sanitized forwarded payload and remote_url to wp-content/ppa-forward-debug.log (no secrets).
 *  - Flatten incoming 'fields[...]' into top-level keys and map subject/headline -> title.
 *
 * IMPORTANT: do not log secrets (X-PPA-Key) — this file avoids writing secret headers to disk.
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

if ( ! class_exists( 'PPA_Controller' ) ) :

final class PPA_Controller {

    private const TRANSIENT_KEY = 'ppa_resolved_preview_path';
    private const TRANSIENT_TTL = 60 * 60; // 1 hour
    private const DEBUG_FILE = 'ppa-forward-debug.log';

    public static function init() : void {
        add_action( 'wp_ajax_ppa_preview', [ __CLASS__, 'handle_preview' ] );
        add_action( 'wp_ajax_ppa_store',   [ __CLASS__, 'handle_store' ] );
    }

    public static function handle_preview() : void { self::proxy_request( 'preview' ); }
    public static function handle_store()   : void { self::proxy_request( 'store' ); }

    private static function resolve_upstream_path( string $action, string $server_base ) {
        $trans_key = self::TRANSIENT_KEY . '_' . $action;
        $cached = get_transient( $trans_key );
        if ( ! empty( $cached ) ) {
            return $cached;
        }

        $candidates = [];
        if ( $action === 'preview' ) {
            $candidates = [
                '/api/preview/',
                '/preview/',
                '/api/v1/preview/',
                '/v1/preview/',
                '/postpress-ai/preview/',
            ];
        } else {
            $candidates = [
                '/api/store/',
                '/store/',
                '/api/v1/store/',
                '/v1/store/',
            ];
        }

        $base = rtrim( $server_base, '/' );

        foreach ( $candidates as $path ) {
            $url = $base . $path;
            $args = [
                'timeout'     => 10,
                'redirection' => 3,
                'blocking'    => true,
                'sslverify'   => true,
            ];

            $head = wp_remote_head( $url, $args );
            if ( ! is_wp_error( $head ) ) {
                $code = (int) wp_remote_retrieve_response_code( $head );
                if ( $code >= 200 && $code < 300 ) {
                    set_transient( $trans_key, $path, self::TRANSIENT_TTL );
                    return $path;
                }
                if ( in_array( $code, [ 405, 501, 0 ], true ) ) {
                    $get = wp_remote_get( $url, $args );
                    if ( ! is_wp_error( $get ) ) {
                        $gcode = (int) wp_remote_retrieve_response_code( $get );
                        if ( $gcode >= 200 && $gcode < 300 ) {
                            set_transient( $trans_key, $path, self::TRANSIENT_TTL );
                            return $path;
                        }
                    }
                }
            }
        }

        return false;
    }

    private static function proxy_request( string $action ) : void {
        // Nonce verification (must match admin JS)
        check_ajax_referer( 'ppa_admin', 'nonce' );

        // Capability check
        if ( ! current_user_can( 'edit_posts' ) ) {
            wp_send_json_error( [ 'message' => 'Insufficient capability' ], 403 );
        }

        // Server base option
        $server_base = trim( (string) get_option( 'ppa_server_base', '' ) );
        if ( empty( $server_base ) ) {
            wp_send_json_error( [ 'message' => 'PPA server base not configured' ], 500 );
        }

        // Shared key (do not log)
        $shared_key = trim( (string) get_option( 'ppa_shared_key', '' ) );
        if ( empty( $shared_key ) && defined( 'PPA_SHARED_KEY' ) ) {
            $shared_key = PPA_SHARED_KEY;
        }

        // If base contains action path already, use it; else probe.
        $path_component = parse_url( $server_base, PHP_URL_PATH ) ?: '';
        $normalized_path_component = strtolower( rtrim( $path_component, '/' ) );
        $uses_full_path = false;
        if ( $action === 'preview' && strpos( $normalized_path_component, 'preview' ) !== false ) {
            $uses_full_path = true;
        } elseif ( $action === 'store' && strpos( $normalized_path_component, 'store' ) !== false ) {
            $uses_full_path = true;
        }

        if ( $uses_full_path ) {
            $remote_url = rtrim( $server_base, '/' );
        } else {
            $resolved_path = self::resolve_upstream_path( $action, $server_base );
            if ( $resolved_path === false ) {
                $diag = sprintf(
                    '<!-- PPA Preview: no upstream endpoint found for action=%s. Tried common paths. Check ppa_server_base and upstream routes. -->',
                    esc_html( $action )
                );
                header( 'Content-Type: text/html; charset=utf-8' );
                echo $diag;
                wp_die();
            }
            $remote_url = rtrim( $server_base, '/' ) . $resolved_path;
        }

        // Prepare headers for upstream
        $headers = [
            'X-PPA-Key'    => $shared_key,
            'X-PPA-Client' => 'wordpress-plugin',
            'X-PPA-Origin' => home_url(),
        ];

        if ( ! empty( $_SERVER['CONTENT_TYPE'] ) ) {
            $headers['Content-Type'] = wp_unslash( (string) $_SERVER['CONTENT_TYPE'] );
        }

        // Prepare body: prefer raw php://input
        $raw_input = file_get_contents( 'php://input' );
        $args = [
            'headers'     => $headers,
            'timeout'     => 20,
            'redirection' => 5,
            'blocking'    => true,
        ];

        $forwarded_sanitized = null; // for debug/fallback usage

        if ( ! empty( $raw_input ) && strlen( trim( $raw_input ) ) > 0 ) {
            $args['body'] = $raw_input;
            // note: we can't safely introspect raw_input without parsing it; skip debug flattening
        } else {
            // SANITIZATION + ALIAS MAPPING + FLATTEN FIELDS
            $forward = $_POST;

            // Flatten incoming fields[...] arrays (e.g. fields[subject]) into top-level keys,
            // but do not overwrite explicit top-level keys that are present.
            if ( isset( $forward['fields'] ) && is_array( $forward['fields'] ) ) {
                foreach ( $forward['fields'] as $fk => $fv ) {
                    if ( ! isset( $forward[ $fk ] ) || $forward[ $fk ] === '' ) {
                        $forward[ $fk ] = $fv;
                    }
                }
                unset( $forward['fields'] );
            }

            // Map common alias fields to 'title' so upstream receives the subject:
            if ( isset( $forward['subject'] ) && empty( $forward['title'] ) ) {
                $forward['title'] = $forward['subject'];
            }
            if ( isset( $forward['headline'] ) && empty( $forward['title'] ) ) {
                $forward['title'] = $forward['headline'];
            }

            unset( $forward['action'], $forward['nonce'] );

            $sanitized = [];
            foreach ( $forward as $k => $v ) {
                $sanitized[ $k ] = is_array( $v ) ? array_map( 'wp_unslash', $v ) : wp_unslash( (string) $v );
            }

            $args['body'] = $sanitized;
            $forwarded_sanitized = $sanitized; // save for debug + fallback generation
        }

        // Make the remote request
        $response = wp_remote_post( $remote_url, $args );

        if ( is_wp_error( $response ) ) {
            wp_send_json_error( [ 'message' => $response->get_error_message() ], 500 );
        }

        $code = (int) wp_remote_retrieve_response_code( $response );
        $body = wp_remote_retrieve_body( $response );

        // If preview action, attempt to extract HTML intelligently
        if ( $action === 'preview' ) {
            $html = '';

            if ( ! empty( $body ) ) {
                $maybe_json = json_decode( $body, true );
                if ( is_array( $maybe_json ) ) {
                    if ( array_key_exists( 'body', $maybe_json ) && is_string( $maybe_json['body'] ) ) {
                        $html = (string) $maybe_json['body'];
                    } elseif ( array_key_exists( 'html', $maybe_json ) && is_string( $maybe_json['html'] ) ) {
                        $html = (string) $maybe_json['html'];
                    } elseif ( array_key_exists( 'result', $maybe_json ) && is_array( $maybe_json['result'] ) ) {
                        if ( array_key_exists( 'body', $maybe_json['result'] ) && is_string( $maybe_json['result']['body'] ) ) {
                            $html = (string) $maybe_json['result']['body'];
                        } elseif ( array_key_exists( 'html', $maybe_json['result'] ) && is_string( $maybe_json['result']['html'] ) ) {
                            $html = (string) $maybe_json['result']['html'];
                        }
                    }
                }

                if ( trim( $html ) === '' && strpos( $body, '<' ) !== false ) {
                    $html = (string) $body;
                }
            }

            // DEBUG LOGGING (safe, no secrets)
            if ( defined( 'WP_DEBUG' ) && WP_DEBUG && is_array( $forwarded_sanitized ) ) {
                $log_path = WP_CONTENT_DIR . '/' . self::DEBUG_FILE;
                $entry = array(
                    'ts'         => gmdate( 'c' ),
                    'remote_url' => $remote_url,
                    'forwarded'  => $forwarded_sanitized,
                    'http_code'  => $code,
                );
                $safe = json_encode( $entry, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE );
                if ( $safe ) {
                    @file_put_contents( $log_path, $safe . PHP_EOL, FILE_APPEND | LOCK_EX );
                }
            }

            // TEMPORARY FALLBACK: if we had a submitted title and the returned HTML
            // does not contain it, generate a simple preview that includes the title.
            if ( is_array( $forwarded_sanitized ) && ! empty( $forwarded_sanitized['title'] ) ) {
                $submitted_title = (string) $forwarded_sanitized['title'];
                $found_title = true;
                if ( trim( $html ) !== '' ) {
                    // case-insensitive containment check
                    if ( stripos( $html, $submitted_title ) !== false ) {
                        $found_title = true;
                    }
                }

                if ( false ) {
                    // build small, safe HTML using the submitted title
                    $safe_title = esc_html( $submitted_title );
                    $generated = '<div class="ppa-generated-preview">';
                    $generated .= '<h1>' . $safe_title . '</h1>';
                    $generated .= '<p><em>Generated preview (fallback):</em> This preview was generated from the submitted title to help preview the output. Replace with upstream content when available.</p>';
                    // optional: include a lightweight 'teaser' using other fields if present
                    if ( ! empty( $forwarded_sanitized['genre'] ) ) {
                        $generated .= '<p><strong>Genre:</strong> ' . esc_html( (string) $forwarded_sanitized['genre'] ) . '</p>';
                    }
                    $generated .= '</div>';
                    $html = $generated;
                }
            }

            $remote_headers = wp_remote_retrieve_headers( $response );
            $up_ct = '';
            if ( is_array( $remote_headers ) && ! empty( $remote_headers['content-type'] ) ) {
                $up_ct = (string) $remote_headers['content-type'];
            } elseif ( method_exists( $remote_headers, 'get' ) && $remote_headers->get( 'content-type' ) ) {
                $up_ct = (string) $remote_headers->get( 'content-type' );
            }

            if ( ! empty( $up_ct ) ) {
                header( 'Content-Type: ' . $up_ct );
            } else {
                header( 'Content-Type: text/html; charset=utf-8' );
            }

            echo $html;
            wp_die();
        }

        // Non-preview endpoints: keep JSON wrapper
        wp_send_json( [ 'status' => $code, 'body' => $body ], $code );
    }
}

endif;

PPA_Controller::init();
