"""HTML templates for DentaCare.

These three constants (HTML_TEMPLATE, MOBILE_PORTAL_TEMPLATE, LOGIN_TEMPLATE)
were extracted verbatim from dental_clinic.py to shrink that module. They are
rendered there via flask.render_template_string; content is byte-for-byte
identical to the originals."""

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ CLINIC_NAME }} — {{ SYSTEM_NAME }}</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;600;700;800&family=Space+Grotesk:wght@600;700&display=swap');

        :root {
            --bg-1: #f1f7f8;
            --bg-2: #e7f0ff;
            --panel: #ffffff;
            --line: #dbe4ef;
            --text: #11243a;
            --muted: #627386;
            --brand: #0f6d7b;
            --brand-2: #1d7fb7;
            --accent: #13b5a7;
            --danger: #d9434e;
            --warning: #d89e1f;
            --ok: #1f9a5f;
            --shadow: 0 14px 36px rgba(19, 39, 66, 0.12);
        }

        * { margin: 0; padding: 0; box-sizing: border-box; }

        body {
            font-family: 'Manrope', 'Inter', 'Segoe UI', Tahoma, sans-serif;
            color: var(--text);
            background:
                radial-gradient(1200px 500px at 100% -30%, #cfe7ff 0%, transparent 60%),
                radial-gradient(1000px 500px at -10% 0%, #cff3ec 0%, transparent 58%),
                linear-gradient(160deg, var(--bg-1), var(--bg-2));
            min-height: 100vh;
            padding: 0;
        }

        body[data-theme="dark"] {
            --bg-1: #0b1220;
            --bg-2: #111a2d;
            --panel: #0f1728;
            --line: #263449;
            --text: #e7eef8;
            --muted: #9bb0c8;
            --shadow: 0 18px 40px rgba(0, 0, 0, 0.35);
            background:
                radial-gradient(1200px 500px at 100% -30%, rgba(29, 127, 183, 0.18) 0%, transparent 60%),
                radial-gradient(1000px 500px at -10% 0%, rgba(19, 181, 167, 0.12) 0%, transparent 58%),
                linear-gradient(160deg, var(--bg-1), var(--bg-2));
        }

        /* Full-window shell: the app fills the browser window edge-to-edge
           (top bar flush to the top), instead of floating as a centered
           card. Content stays in a comfortable column — see .tab-content. */
        .container {
            min-height: 100vh;
            margin: 0;
            display: flex;
            flex-direction: column;
            background: rgba(255, 255, 255, 0.88);
            border: none;
            backdrop-filter: blur(8px);
            border-radius: 0;
            overflow: hidden;
        }

        body[data-theme="dark"] .container {
            background: rgba(12, 19, 33, 0.92);
        }

        /* ── Header ── */
        .header {
            padding: 20px 28px 18px;
            color: #fff;
            background: linear-gradient(135deg, var(--brand) 0%, var(--brand-2) 55%, #3565b8 100%);
            position: relative;
            overflow: hidden;
        }

        .header::before {
            content: '';
            position: absolute;
            inset: 0;
            background:
                radial-gradient(ellipse 65% 90% at 8% -15%, rgba(255,255,255,0.16) 0%, transparent 65%),
                linear-gradient(180deg, rgba(255,255,255,0.07) 0%, transparent 50%);
            pointer-events: none;
            z-index: 0;
        }

        .header::after {
            content: '';
            position: absolute;
            width: 300px; height: 300px;
            right: -70px; top: -120px;
            border-radius: 50%;
            background: rgba(255,255,255,0.06);
            border: 1px solid rgba(255,255,255,0.1);
        }

        .header-accent-line {
            position: absolute;
            bottom: 0; left: 0; right: 0;
            height: 2px;
            background: linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.4) 35%, rgba(255,255,255,0.6) 50%, rgba(255,255,255,0.4) 65%, transparent 100%);
        }

        body[data-theme="dark"] .header {
            background: linear-gradient(135deg, #0e2b4d 0%, #124c71 55%, #1d5f87 100%);
        }

        .header-top {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 12px;
            width: 100%;
            position: relative;
            z-index: 1;
        }

        .header-brand {
            display: flex;
            align-items: center;
            gap: 14px;
            position: relative;
            z-index: 1;
        }

        .header-logo-mark {
            width: 58px; height: 58px; min-width: 58px;
            border-radius: 0;
            background: transparent;
            border: none;
            display: flex;
            align-items: center;
            justify-content: center;
            backdrop-filter: none;
            box-shadow: none;
            flex-shrink: 0;
            overflow: visible;
            padding: 0;
        }

        .header-logo-img {
            width: 100%;
            height: 100%;
            object-fit: contain;
            display: block;
            filter: drop-shadow(0 1px 3px rgba(0,0,0,0.25));
        }

        .header-text { display: flex; flex-direction: column; gap: 3px; }

        .header-system-name {
            font-family: 'Space Grotesk', 'Manrope', sans-serif;
            font-size: clamp(1.1rem, 2.8vw, 1.65rem);
            font-weight: 800;
            letter-spacing: -0.025em;
            color: #fff;
            line-height: 1.15;
            text-shadow: 0 1px 8px rgba(0,0,0,0.2);
        }

        .header-clinic-name {
            font-size: 0.72rem;
            font-weight: 700;
            color: rgba(255,255,255,0.65);
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }

        /* ── Header right controls ── */
        .header-meta {
            display: flex;
            align-items: center;
            gap: 6px;
            flex-wrap: wrap;
            justify-content: flex-end;
        }

        .header-meta-divider {
            width: 1px;
            height: 22px;
            background: rgba(255,255,255,0.25);
            margin: 0 4px;
        }

        .doctor-badge {
            position: relative;
            display: inline-flex;
            align-items: center;
            gap: 0;
            padding: 8px 13px;
            border-radius: 13px;
            font-weight: 700;
            color: #fff;
            border: 1px solid rgba(255,255,255,0.28);
            background: rgba(255,255,255,0.14);
            backdrop-filter: blur(8px);
            cursor: pointer;
            white-space: nowrap;
            user-select: none;
            transition: background 0.18s, border-color 0.18s, transform 0.12s;
        }

        .doctor-badge:hover {
            background: rgba(255,255,255,0.22);
            border-color: rgba(255,255,255,0.44);
            transform: translateY(-1px);
        }

        .doctor-badge:active { transform: translateY(0); }

        .doctor-badge-name { font-size: 1rem; font-weight: 700; letter-spacing: -0.01em; }

        .doctor-edit-icon {
            position: absolute;
            top: -22px;
            left: 50%;
            transform: translateX(-50%);
            font-size: 0.78rem;
            background: rgba(0,0,0,0.55);
            color: #fff;
            padding: 2px 7px;
            border-radius: 6px;
            white-space: nowrap;
            opacity: 0;
            pointer-events: none;
            transition: opacity 0.18s;
        }
        .doctor-badge:hover .doctor-edit-icon { opacity: 1; }

        /* Doctor name edit popover */
        .doctor-edit-popover {
            display: none;
            position: fixed;
            min-width: 270px;
            background: var(--panel);
            border: 1px solid var(--line);
            border-radius: 16px;
            padding: 18px;
            box-shadow: 0 20px 48px rgba(0,0,0,0.22), 0 2px 8px rgba(0,0,0,0.1);
            z-index: 9999;
        }
        .doctor-edit-popover.open { display: block; animation: popoverIn 0.16s ease; }

        @keyframes popoverIn {
            from { opacity: 0; transform: translateY(-6px) scale(0.97); }
            to   { opacity: 1; transform: translateY(0) scale(1); }
        }

        .doctor-edit-popover-title {
            font-size: 0.75rem;
            font-weight: 800;
            color: var(--muted);
            text-transform: uppercase;
            letter-spacing: 0.07em;
            margin-bottom: 14px;
        }

        .doctor-edit-field { margin-bottom: 10px; }
        .doctor-edit-field label {
            display: block;
            font-size: 0.78rem;
            font-weight: 600;
            color: var(--muted);
            margin-bottom: 5px;
        }
        .doctor-edit-field input {
            width: 100%;
            padding: 8px 11px;
            border: 1.5px solid var(--line);
            border-radius: 9px;
            font-size: 0.9rem;
            color: var(--text);
            background: var(--bg-1);
            outline: none;
            transition: border-color 0.15s;
            font-family: inherit;
        }
        .doctor-edit-field input:focus { border-color: var(--brand); }

        .doctor-edit-actions {
            display: flex;
            gap: 8px;
            margin-top: 14px;
        }
        .doctor-edit-save {
            flex: 1;
            padding: 9px;
            background: var(--brand);
            color: #fff;
            border: none;
            border-radius: 9px;
            font-weight: 700;
            font-size: 0.875rem;
            cursor: pointer;
            transition: opacity 0.15s;
            font-family: inherit;
        }
        .doctor-edit-save:hover { opacity: 0.88; }
        .doctor-edit-cancel {
            padding: 9px 13px;
            background: transparent;
            color: var(--muted);
            border: 1.5px solid var(--line);
            border-radius: 9px;
            font-weight: 600;
            font-size: 0.875rem;
            cursor: pointer;
            font-family: inherit;
        }
        .doctor-edit-cancel:hover { background: var(--bg-1); }

        /* Theme / language toggles */
        .theme-toggle, .language-toggle {
            margin: 0;
            border-radius: 8px;
            background: transparent;
            border: none;
            color: #fff;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            backdrop-filter: none;
            transition: opacity 0.18s, transform 0.12s;
            font-family: inherit;
        }
        .theme-toggle:hover, .language-toggle:hover {
            opacity: 0.72;
            transform: translateY(-1px);
        }
        .theme-toggle:active, .language-toggle:active { transform: translateY(0); }
        .theme-toggle {
            width: 38px; height: 38px; min-width: 38px;
            padding: 0;
            font-size: 1.3rem;
            line-height: 1;
        }
        .language-toggle {
            padding: 0 4px;
            height: 38px;
            font-size: 1rem;
            font-weight: 700;
            white-space: nowrap;
            letter-spacing: 0.02em;
        }

        .sub-tabs {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(118px, max-content));
            justify-content: flex-start;
            gap: 10px;
            margin-bottom: 16px;
        }

        .sub-tab {
            border: 1px solid #c9d8e8;
            border-radius: 10px;
            background: #f7fbff;
            color: #2d4c67;
            padding: 9px 13px;
            font-weight: 700;
            cursor: pointer;
            box-shadow: 0 2px 6px rgba(15, 40, 66, 0.04);
            transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
        }

        .sub-tab:hover {
            background: #edf6ff;
            transform: translateY(-2px);
            box-shadow: 0 5px 12px rgba(30, 136, 229, 0.15);
        }

        .sub-tab.active {
            background: linear-gradient(135deg, rgba(62, 168, 255, 0.1) 0%, rgba(30, 136, 229, 0.15) 100%);
            border-color: rgba(30, 136, 229, 0.4);
            color: #1e88e5;
            box-shadow: 0 0 15px rgba(30, 136, 229, 0.15), inset 0 0 0 1px rgba(255, 255, 255, 0.8);
            text-shadow: 0 0 8px rgba(30, 136, 229, 0.2);
        }

        .sub-tab-content {
            display: none;
            margin-bottom: 14px;
        }

        .sub-tab-content.active {
            display: block;
            border: 1px solid rgba(163, 192, 219, 0.38);
            border-radius: 12px;
            background: rgba(248, 252, 255, 0.72);
            padding: 14px 14px 10px;
        }

        .collapsible-box {
            border: 1px solid var(--line);
            border-radius: 12px;
            background: #fff;
            padding: 10px 12px;
        }

        .collapsible-box > summary {
            cursor: pointer;
            font-weight: 800;
            color: #214a68;
            list-style: none;
        }

        .collapsible-box > summary::-webkit-details-marker {
            display: none;
        }

        .collapsible-box > summary::before {
            content: '▸';
            margin-right: 6px;
        }

        .collapsible-box[open] > summary::before {
            content: '▾';
        }

        body[data-theme="dark"] .sub-tab {
            background: #111c30;
            border-color: #31425c;
            color: #bdd0e6;
        }

        body[data-theme="dark"] .sub-tab.active {
            background: linear-gradient(135deg, rgba(19, 181, 167, 0.18) 0%, rgba(29, 127, 183, 0.2) 100%);
            border-color: rgba(96, 135, 179, 0.5);
            color: #f3f8ff;
        }

        body[data-theme="dark"] .sub-tab-content.active {
            background: rgba(13, 25, 43, 0.62);
            border-color: rgba(87, 117, 151, 0.45);
        }

        body[data-theme="dark"] .collapsible-box {
            background: #10192a;
            border-color: #253347;
        }

        body[data-theme="dark"] .collapsible-box > summary {
            color: #dce8f6;
        }

        /* ── Header → body transition strip ── */
        .header-bridge {
            height: 3px;
            background: linear-gradient(90deg,
                var(--brand) 0%,
                var(--brand-2) 50%,
                #3565b8 100%);
            opacity: 0.18;
            flex-shrink: 0;
        }

        body[data-theme="dark"] .header-bridge {
            opacity: 0.35;
        }

        .app-body {
            display: flex;
            flex-direction: row;
            flex: 1;
            min-height: 0;
        }

        .nav-tabs {
            display: flex;
            flex-direction: column;
            gap: 4px;
            padding: 16px 10px;
            background: #f3f7fb;
            border-right: 1px solid var(--line);
            overflow-y: auto;
            width: 196px;
            min-width: 196px;
            flex-shrink: 0;
        }

        .nav-tabs-label {
            font-size: 0.7rem;
            font-weight: 800;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            color: var(--muted);
            padding: 4px 6px 10px;
        }

        body[data-theme="dark"] .nav-tabs {
            background: #10192a;
            border-right-color: #1e2e42;
        }

        .nav-tab {
            flex: none;
            width: 100%;
            text-align: left;
            border: 1px solid transparent;
            background: transparent;
            border-radius: 10px;
            color: #35516d;
            padding: 11px 13px;
            font-weight: 700;
            font-size: 0.92rem;
            cursor: pointer;
            transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
            display: flex;
            align-items: center;
            gap: 9px;
        }

        .nav-tab:focus-visible,
        .nav-subtab:focus-visible {
            outline: 2px solid #7bb6e2;
            outline-offset: 2px;
        }

        .nav-tab:hover { background: #e8f1fa; transform: translateX(4px); box-shadow: 0 4px 12px rgba(30, 136, 229, 0.1); }

        body[data-theme="dark"] .nav-tab {
            color: #bfd0e4;
        }

        body[data-theme="dark"] .nav-tab:hover {
            background: rgba(255, 255, 255, 0.05);
        }

        .nav-tab.active {
            background: linear-gradient(135deg, rgba(62, 168, 255, 0.1) 0%, rgba(30, 136, 229, 0.15) 100%);
            border-color: rgba(30, 136, 229, 0.4);
            color: #1e88e5;
            box-shadow: 0 0 15px rgba(30, 136, 229, 0.15), inset 0 0 0 1px rgba(255, 255, 255, 0.8);
            text-shadow: 0 0 8px rgba(30, 136, 229, 0.2);
            transform: translateX(4px);
        }

        .nav-group-label {
            margin-top: 8px;
            padding: 10px 6px 6px;
            font-size: 0.68rem;
            font-weight: 900;
            letter-spacing: 0.1em;
            text-transform: uppercase;
            color: var(--muted);
        }

        .nav-subtabs {
            display: flex;
            flex-direction: column;
            gap: 4px;
            padding-left: 12px;
            margin-bottom: 6px;
        }

        .nav-subtab {
            width: 100%;
            border: 1px solid transparent;
            border-radius: 10px;
            padding: 9px 12px 9px 16px;
            background: transparent;
            color: #4a6480;
            font-weight: 700;
            font-size: 0.88rem;
            text-align: left;
            cursor: pointer;
            transition: 0.2s ease;
            position: relative;
        }

        .nav-subtab::before {
            content: '';
            position: absolute;
            left: 7px;
            top: 50%;
            width: 5px;
            height: 5px;
            border-radius: 999px;
            transform: translateY(-50%);
            background: rgba(77, 108, 143, 0.55);
        }

        .nav-subtab:hover {
            background: #edf6ff;
        }

        .nav-subtab.active {
            background: rgba(123, 182, 226, 0.16);
            border-color: rgba(123, 182, 226, 0.4);
            color: #113f64;
        }

        body[data-theme="dark"] .nav-group-label {
            color: #91a8c2;
        }

        body[data-theme="dark"] .nav-subtab {
            color: #b9cae0;
        }

        body[data-theme="dark"] .nav-subtab::before {
            background: rgba(185, 202, 224, 0.45);
        }

        body[data-theme="dark"] .nav-subtab:hover {
            background: rgba(255, 255, 255, 0.04);
        }

        body[data-theme="dark"] .nav-subtab.active {
            background: rgba(19, 181, 167, 0.14);
            border-color: rgba(96, 135, 179, 0.38);
            color: #f3f8ff;
        }

        body[data-theme="dark"] .nav-tab.active {
            background: linear-gradient(135deg, rgba(19, 181, 167, 0.18) 0%, rgba(29, 127, 183, 0.2) 100%);
            border-color: rgba(96, 135, 179, 0.5);
            color: #f3f8ff;
        }

        /* Collapsible sidebar quick-win: compact width and icon-only mode */
        body.sidebar-collapsed .nav-tabs {
            width: 72px;
            min-width: 72px;
            padding: 10px 6px;
        }
        body.sidebar-collapsed .nav-tab {
            justify-content: center;
            padding: 8px 6px;
            gap: 0;
        }
        body.sidebar-collapsed .nav-group-label,
        body.sidebar-collapsed .nav-subtabs {
            display: none;
        }
        body.sidebar-collapsed .nav-tab span:not(.tab-icon) { display: none; }
        body.sidebar-collapsed .nav-tabs-label { display: none; }

        @media (max-width: 980px) {
            .nav-tabs { width: 72px; min-width: 72px; }
            .nav-tabs-label { display: none; }
            .content { padding: 18px; }
            .nav-group-label { padding-left: 2px; }
            .nav-subtabs { padding-left: 8px; }
        }

        .content { flex: 1; min-width: 0; padding: 28px; }
        /* Chrome (header + sidebar) goes full-width; the working area stays
           in a centered, readable column so a wide monitor looks premium,
           not just stretched. */
        .tab-content { display: none; max-width: 1500px; margin: 0 auto; }
        .tab-content.active { display: block; animation: fadeIn 0.25s ease; }

        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(8px); }
            to { opacity: 1; transform: translateY(0); }
        }

        h2 {
            font-family: 'Space Grotesk', 'Manrope', sans-serif;
            margin-bottom: 14px;
            letter-spacing: -0.02em;
        }

        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 14px;
            margin-bottom: 22px;
        }

        .stat-card {
            padding: 18px;
            border-radius: 16px;
            color: #fff;
            background: linear-gradient(135deg, #1a8ca2 0%, #2672c5 100%);
            box-shadow: 0 12px 24px rgba(23, 76, 129, 0.2);
        }

        body[data-theme="dark"] .stat-card {
            background: linear-gradient(135deg, #164457 0%, #224f8a 100%);
            box-shadow: 0 12px 24px rgba(0, 0, 0, 0.24);
        }

        .stat-card h3 {
            font-size: clamp(1.3rem, 2.2vw, 1.9rem);
            margin-bottom: 6px;
            line-height: 1.15;
            white-space: nowrap;
        }

        .stat-card p { opacity: 0.92; font-size: 0.9rem; }

        .form-group { margin-bottom: 16px; }
        .form-group label {
            display: block;
            margin-bottom: 7px;
            color: #2c425c;
            font-weight: 700;
            font-size: 0.92rem;
        }

        .form-group input,
        .form-group select,
        .form-group textarea {
            width: 100%;
            border: 1px solid #cdd9e6;
            border-radius: 12px;
            padding: 11px 12px;
            background: #fff;
            color: var(--text);
            transition: 0.2s ease;
        }

        body[data-theme="dark"] .form-group input,
        body[data-theme="dark"] .form-group select,
        body[data-theme="dark"] .form-group textarea {
            background: #0e1727;
            border-color: #2a3951;
            color: var(--text);
        }

        /* Design tokens (quick-win) */
        :root {
            --space-1: 6px;
            --space-2: 10px;
            --space-3: 14px;
            --space-4: 18px;
            --space-5: 24px;
            --space-6: 32px;
            --gap: var(--space-3);
            --input-padding: 12px 14px;
        }

        .form-group textarea { resize: vertical; min-height: 96px; }

        .form-group input:focus,
        .form-group select:focus,
        .form-group textarea:focus {
            outline: none;
            border-color: #7bb6e2;
            box-shadow: 0 0 0 4px rgba(61, 149, 211, 0.14);
        }

        /* Searchable patient combobox: one field that filters as you type and
           slides a list of matches down. The native <select> stays in the DOM
           (visually hidden) as the value holder for forms and scripts. */
        .patient-combo { position: relative; }
        .patient-combo-native {
            position: absolute !important;
            width: 1px !important;
            height: 1px !important;
            padding: 0 !important;
            margin: -1px !important;
            border: 0 !important;
            overflow: hidden;
            clip: rect(0, 0, 0, 0);
            clip-path: inset(50%);
            white-space: nowrap;
            pointer-events: none;
        }
        .patient-combo-input { width: 100%; }
        .patient-combo-menu {
            position: absolute;
            top: calc(100% + 4px);
            left: 0; right: 0;
            z-index: 60;
            max-height: 260px;
            overflow-y: auto;
            background: var(--panel);
            border: 1px solid var(--line);
            border-radius: 12px;
            box-shadow: var(--shadow);
            padding: 4px;
        }
        .patient-combo-option {
            padding: 9px 11px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 0.92rem;
            color: var(--text);
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .patient-combo-option:hover,
        .patient-combo-option.is-active { background: var(--bg-1); }
        .patient-combo-empty {
            padding: 10px 11px;
            color: var(--muted);
            font-size: 0.9rem;
        }

        .form-row { display: grid; grid-template-columns: 1fr 1fr; gap: var(--gap); }

        .btn {
            border: none;
            border-radius: 12px;
            padding: 10px 16px;
            cursor: pointer;
            font-weight: 800;
            font-size: 0.9rem;
            transition: 0.18s ease;
            letter-spacing: 0.01em;
        }

        .btn:hover { transform: translateY(-1px); }
        .btn-primary { background: linear-gradient(135deg, var(--brand) 0%, var(--brand-2) 100%); color: #fff; }
        .btn-success { background: linear-gradient(135deg, #2c9e62 0%, #22b7a1 100%); color: #fff; }
        .btn-danger { background: linear-gradient(135deg, #da4c58 0%, #be3955 100%); color: #fff; }
        .btn-warning { background: linear-gradient(135deg, #f2ca53 0%, #e8a733 100%); color: #342300; }

        /* Small / icon buttons */
        .btn-sm { padding: 6px 10px; font-size: 0.85rem; border-radius: 10px; }
        .btn-icon { padding: 6px 8px; font-size: 0.88rem; border-radius: 10px; }

        .table-container {
            margin-top: 16px;
            overflow-x: auto;
            border: 1px solid var(--line);
            border-radius: 16px;
            background: #fff;
        }

        body[data-theme="dark"] .table-container {
            background: #0f1728;
            border-color: #253347;
        }

        table { width: 100%; border-collapse: collapse; }
        table th {
            padding: 14px 16px;
            text-align: left;
            font-size: 0.95rem;
            letter-spacing: 0.02em;
            color: #49617b;
            background: #f5f9fd;
            border-bottom: 1px solid var(--line);
        }

        body[data-theme="dark"] table th {
            background: #121d31;
            color: #b9cbe0;
            border-bottom-color: #27364a;
        }

        table td {
            padding: 14px 16px;
            border-bottom: 1px solid #edf2f7;
            vertical-align: top;
            font-size: 0.95rem;
        }

        body[data-theme="dark"] table td {
            border-bottom-color: #223043;
        }

        body[data-theme="dark"] table tr:hover {
            background: rgba(255, 255, 255, 0.03);
        }

        table tr:hover { background: #f7fbff; }

        .badge {
            display: inline-flex;
            align-items: center;
            border-radius: 999px;
            padding: 4px 10px;
            font-size: 0.76rem;
            font-weight: 800;
            text-transform: uppercase;
            letter-spacing: 0.04em;
        }

        .badge-success { background: #e0f4e8; color: #166942; }
        .badge-warning { background: #fff1d4; color: #8b5e00; }
        .badge-danger { background: #ffe2e5; color: #8d1f33; }
        .badge-info { background: #e3f1ff; color: #1f5d9e; }

        .expense-status-select { padding: 4px 6px; font-size: 0.85rem; border-radius: 6px; border: 1px solid #cdd9e6; }
        .expense-status-select[data-status="paid"] { background: #e0f4e8; color: #166942; }
        .expense-status-select[data-status="postponed"] { background: #fff1d4; color: #8b5e00; }
        body[data-theme="dark"] .expense-status-select[data-status="paid"] { background: #1a3a22; color: #6ee699; border-color: #2a5a32; }
        body[data-theme="dark"] .expense-status-select[data-status="postponed"] { background: #2a2210; color: #d4a843; border-color: #4a3a10; }

        .action-buttons { display: flex; gap: 8px; flex-wrap: wrap; }
        .action-buttons button { padding: 7px 12px; font-size: 0.8rem; }

        .toolbar-row {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
            margin-top: 12px;
            align-items: center;
        }

        .toolbar-row .btn { padding: 10px 14px; }

        .search-status { margin-top: 8px; color: var(--muted); font-size: 0.9rem; }

        .calendar-controls {
            margin-top: 12px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 12px;
            flex-wrap: wrap;
            padding: 12px;
            border: 1px solid var(--line);
            border-radius: 14px;
            background: linear-gradient(135deg, #f8fcff 0%, #f2fbf8 100%);
        }

        .calendar-month-title {
            font-family: 'Space Grotesk', 'Manrope', sans-serif;
            font-size: 1.12rem;
            font-weight: 700;
            color: #214766;
        }

        .appointments-calendar { margin-top: 14px; display: grid; grid-template-columns: repeat(7, 1fr); gap: 8px; }
        .calendar-day-header {
            font-weight: 700;
            padding: 8px;
            background: #f2f7fc;
            border: 1px solid var(--line);
            border-radius: 10px;
            text-align: center;
            color: #345670;
            font-size: 0.85rem;
        }

        .calendar-day-cell {
            min-height: 116px;
            border: 1px solid var(--line);
            border-radius: 12px;
            padding: 8px;
            background: #fff;
            transition: all 0.2s ease;
        }

        .calendar-day-cell.cursor-pointer {
            cursor: pointer;
        }

        .calendar-day-cell.cursor-pointer:hover {
            background: #f0f8ff;
            border-color: #7bb6e2;
            box-shadow: 0 2px 8px rgba(61, 149, 211, 0.15);
            transform: translateY(-1px);
        }

        .calendar-day-cell.cursor-not-allowed {
            cursor: not-allowed;
            opacity: 0.7;
        }

        .calendar-day-number { font-weight: 800; color: #27415b; }
        .calendar-empty { font-size: 11px; color: #8ba0b5; margin-top: 6px; }
        /* Date picker modal */
        .date-picker-modal { display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.4); z-index: 10000; align-items: center; justify-content: center; }
        .date-picker-modal.active { display: flex; }
        .date-picker-modal-content { background: #fff; border-radius: 16px; padding: 20px; box-shadow: 0 8px 32px rgba(0,0,0,0.15); max-width: 320px; width: 90%; }
        body[data-theme="dark"] .date-picker-modal-content { background: #0e1727; color: #f1f5f9; }
        .date-picker-modal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
        .date-picker-modal-header button { background: none; border: none; font-size: 24px; cursor: pointer; color: #627386; }
        .date-picker-modal-month { font-weight: 700; font-size: 1.1rem; text-align: center; }
        .date-picker-grid { display: grid; grid-template-columns: repeat(7, 1fr); gap: 8px; margin-top: 14px; }
        .date-picker-day { text-align: center; padding: 6px; border-radius: 8px; cursor: pointer; font-size: 0.9rem; border: 1px solid transparent; }
        .date-picker-day:hover { background: #e8f1fa; }
        .date-picker-day-name { font-weight: 700; font-size: 0.75rem; color: #627386; padding: 8px 0; }
        body[data-theme="dark"] .date-picker-day:hover { background: rgba(255,255,255,0.08); }
        .date-picker-day.empty { cursor: default; }
        .date-picker-day.today { background: #e6f7f5; border-color: #13b5a7; color: #0f6d7b; font-weight: 700; }


        .calendar-event {
            font-size: 11px;
            padding: 5px 7px;
            margin-top: 5px;
            background: linear-gradient(135deg, #e5f2ff 0%, #def5ef 100%);
            border: 1px solid #cee1f5;
            border-radius: 8px;
            line-height: 1.35;
        }

        .alert { padding: 12px; border-radius: 10px; margin-bottom: 14px; }
        .alert-success { background: #e2f6ea; color: #0f643f; border: 1px solid #bee7ce; }
        .alert-error { background: #ffe6e8; color: #892336; border: 1px solid #fac8ce; }

        body[data-theme="dark"] .alert-success {
            background: rgba(31, 154, 95, 0.14);
            color: #7be0b0;
            border-color: rgba(31, 154, 95, 0.28);
        }

        body[data-theme="dark"] .alert-error {
            background: rgba(217, 67, 78, 0.14);
            color: #ff9da8;
            border-color: rgba(217, 67, 78, 0.28);
        }

        .modal {
            display: none;
            position: fixed;
            inset: 0;
            background: rgba(10, 23, 38, 0.58);
            z-index: 1000;
            justify-content: center;
            align-items: center;
            padding: 16px;
        }

        .modal.active { display: flex; }

        .modal-content {
            background: #fff;
            padding: 22px;
            border-radius: 16px;
            max-width: 640px;
            width: 100%;
            max-height: 90vh;
            overflow-y: auto;
            border: 1px solid var(--line);
            box-shadow: var(--shadow);
        }

        body[data-theme="dark"] .modal-content {
            background: #111a2b;
            border-color: #253347;
        }

        .modal-header { margin-bottom: 16px; }
        .modal-header h2 {
            font-family: 'Space Grotesk', 'Manrope', sans-serif;
            color: #19344f;
            letter-spacing: -0.01em;
        }

        body[data-theme="dark"] .modal-header h2,
        body[data-theme="dark"] .billing-equation-box h4 {
            color: #e6effb;
        }

        .close-modal {
            float: right;
            font-size: 1.3rem;
            line-height: 1;
            cursor: pointer;
            color: #59758f;
        }

        body[data-theme="dark"] .close-modal {
            color: #b0c3da;
        }

        .billing-equation-box {
            border: 1px solid #cfe1f0;
            border-radius: 12px;
            background: linear-gradient(135deg, #f5fbff 0%, #f3fff8 100%);
            padding: 12px;
            margin-bottom: 16px;
        }

        body[data-theme="dark"] .billing-equation-box {
            background: linear-gradient(135deg, rgba(17, 28, 46, 0.98) 0%, rgba(16, 42, 52, 0.98) 100%);
            border-color: #27364a;
        }

        /* Appointment form helpers */
        .form-section { margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px dashed var(--line); }
        .form-section h3 { font-size: 0.95rem; margin-bottom: 8px; color: var(--brand); }
        .field-error { color: var(--danger); font-size: 0.85rem; margin-top: 6px; min-height: 18px; }
        .form-actions { display: flex; gap: 8px; justify-content: flex-end; align-items: center; margin-top: 12px; }
        .btn-large { padding: 10px 18px; font-size: 1rem; }
        .hint { color: var(--muted); font-size: 0.85rem; margin-top: 6px; }
        .required { color: var(--danger); }
        .toast { padding: 8px 12px; border-radius: 8px; margin-top: 8px; display: inline-block; }
        .toast.success { background: #e6f7ef; color: #0f643f; border: 1px solid #bfe6ce; }
        .toast.error { background: #fff1f2; color: #b23a44; border: 1px solid #f6c7c9; }

        .billing-equation-box h4 {
            margin-bottom: 8px;
            color: #214a68;
            font-size: 0.92rem;
        }

        .billing-equation-box p {
            font-size: 0.87rem;
            color: #4d6379;
            margin-bottom: 3px;
        }

        body[data-theme="dark"] .billing-equation-box p,
        body[data-theme="dark"] .search-status {
            color: #a9bed7;
        }

        body[data-theme="dark"] .calendar-controls {
            background: linear-gradient(135deg, #10192a 0%, #0f1f20 100%);
            border-color: #253347;
        }

        body[data-theme="dark"] .calendar-month-title,
        body[data-theme="dark"] .calendar-day-number {
            color: #eaf2ff;
        }

        body[data-theme="dark"] .calendar-day-header,
        body[data-theme="dark"] .calendar-day-cell {
            background: #10192a;
            border-color: #253347;
            color: #dce7f4;
        }

        body[data-theme="dark"] .calendar-day-cell.cursor-pointer:hover {
            background: #132238;
        }

        body[data-theme="dark"] .calendar-event {
            background: linear-gradient(135deg, rgba(29, 127, 183, 0.2) 0%, rgba(19, 181, 167, 0.16) 100%);
            border-color: rgba(124, 156, 196, 0.24);
            color: #eff6ff;
        }

        @media (max-width: 1024px) {
            .nav-tabs { width: 168px; min-width: 168px; padding: 12px 8px; }
            .content { padding: 20px; }
            .appointments-calendar { grid-template-columns: repeat(4, 1fr); }
        }

        /* ── Mobile hamburger trigger ── */
        .nav-hamburger {
            display: none;
            position: fixed;
            bottom: 20px;
            right: 20px;
            z-index: 900;
            width: 52px;
            height: 52px;
            border-radius: 999px;
            background: linear-gradient(135deg, var(--brand) 0%, var(--brand-2) 100%);
            color: #fff;
            font-size: 1.3rem;
            border: none;
            cursor: pointer;
            box-shadow: 0 8px 24px rgba(15, 109, 123, 0.4);
            align-items: center;
            justify-content: center;
            transition: 0.2s ease;
        }
        .nav-hamburger:hover { transform: scale(1.06); }
        html[dir="rtl"] .nav-hamburger { right: auto; left: 20px; }

        /* ── Mobile overlay nav ── */
        .nav-overlay {
            display: none;
            position: fixed;
            inset: 0;
            background: rgba(10, 23, 38, 0.52);
            z-index: 800;
        }
        .nav-overlay.active { display: block; }

        @media (max-width: 760px) {
            body { padding: 8px; }

            .header { padding: 16px 18px; }
            .header-logo-mark { width: 44px; height: 44px; min-width: 44px; }
            .header-system-name { font-size: 1.1rem; }
            .header-clinic-name { font-size: 0.74rem; }
            .doctor-badge { padding: 6px 10px; font-size: 0.8rem; gap: 5px; }
            .theme-toggle { width: 34px; height: 34px; min-width: 34px; min-height: 34px; }
            .language-toggle { min-height: 34px; font-size: 0.84rem; padding: 0 9px; }

            .app-body { flex-direction: column; }

            /* On mobile, nav slides in from side */
            .nav-tabs {
                position: fixed;
                left: -220px;
                top: 0;
                bottom: 0;
                width: 210px;
                min-width: 0;
                z-index: 850;
                border-right: 1px solid var(--line);
                border-bottom: none;
                flex-direction: column;
                padding: 16px 10px;
                overflow-y: auto;
                overflow-x: hidden;
                gap: 4px;
                transition: left 0.3s cubic-bezier(0.4, 0, 0.2, 1);
                background: var(--panel);
                box-shadow: 8px 0 32px rgba(0,0,0,0.12);
            }
            body[data-theme="dark"] .nav-tabs { background: #0f1728; }
            .nav-tabs.mobile-open { left: 0; }
            html[dir="rtl"] .nav-tabs {
                left: auto; right: -220px; border-left: 1px solid var(--line); border-right: none;
                transition: right 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            }
            html[dir="rtl"] .nav-tabs.mobile-open { right: 0; }

            .nav-hamburger { display: flex; }
            .nav-tabs-label { display: block; }
            .nav-group-label { display: block; }

            .content { padding: 12px; }
            .form-row { grid-template-columns: 1fr; gap: 10px; }
            .stats-grid { grid-template-columns: 1fr 1fr; }
            .appointments-calendar { grid-template-columns: repeat(2, 1fr); }
            .action-buttons { flex-direction: column; }
            .action-buttons .btn { width: 100%; }
            .sub-tabs { grid-template-columns: 1fr 1fr; gap: 8px; }
            .sub-tab { text-align: center; }
            .sub-tab-content.active { padding: 12px 10px 8px; }

            /* Tables scroll on small screens */
            .responsive-table-wrap { -webkit-overflow-scrolling: touch; }
            .modal-content { padding: 16px; border-radius: 14px; max-height: 95vh; }
        }

        @media (max-width: 480px) {
            .stats-grid { grid-template-columns: 1fr; }
            .header-meta { gap: 7px; }
        }

        /* RTL Support */
        html[dir="rtl"] body {
            direction: rtl;
            text-align: right;
            font-family: 'Cairo', 'Tajawal', 'Noto Sans Arabic', 'Segoe UI', Tahoma, sans-serif;
        }
        html[dir="rtl"] .header { text-align: right; }
        html[dir="rtl"] .header-top { flex-direction: row-reverse; }
        html[dir="rtl"] .header-meta { justify-content: flex-start; }
        html[dir="rtl"] .nav-tabs { border-right: none; border-left: 1px solid var(--line); order: 1; }
        html[dir="rtl"] .nav-tab { text-align: right; }
        html[dir="rtl"] .form-row { direction: rtl; }
        html[dir="rtl"] .toolbar-row { flex-direction: row-reverse; }
        html[dir="rtl"] .action-buttons { flex-direction: row-reverse; }
        html[dir="rtl"] table { text-align: right; }
        html[dir="rtl"] table th,
        html[dir="rtl"] table td { text-align: right; }
        html[dir="rtl"] .form-group label { text-align: right; display: block; }
        html[dir="rtl"] .modal-content { direction: rtl; text-align: right; }
        html[dir="rtl"] .close-modal { float: left; }

        /* ── UI Polish ── */
        .page-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            flex-wrap: wrap;
            margin-bottom: 20px;
            padding-bottom: 16px;
            border-bottom: 2px solid var(--line);
        }
        .page-header h2 { margin-bottom: 0; }
        .page-header .header-actions { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
        .section-divider {
            display: flex;
            align-items: center;
            gap: 10px;
            margin: 24px 0 14px;
        }
        .section-divider span {
            font-family: 'Space Grotesk', 'Manrope', sans-serif;
            font-weight: 700;
            font-size: 0.9rem;
            color: var(--text);
            white-space: nowrap;
        }
        .section-divider::after { content: ''; flex: 1; height: 1px; background: var(--line); }
        .stat-card { position: relative; overflow: hidden; }
        .stat-card .stat-icon {
            position: absolute;
            right: 14px;
            top: 50%;
            transform: translateY(-50%);
            font-size: 2.4rem;
            opacity: 0.18;
            pointer-events: none;
        }
        html[dir="rtl"] .stat-card .stat-icon { right: auto; left: 14px; }
        .stat-card h3, .stat-card p { position: relative; z-index: 1; }
        .stat-card-teal { background: linear-gradient(135deg, #0f6d7b 0%, #13b5a7 100%) !important; }
        .stat-card-blue { background: linear-gradient(135deg, #1d7fb7 0%, #3565b8 100%) !important; }
        .stat-card-green { background: linear-gradient(135deg, #1f9a5f 0%, #22b7a1 100%) !important; }
        .stat-card-amber { background: linear-gradient(135deg, #c47f10 0%, #d89e1f 100%) !important; color: #fff !important; }
        body[data-theme="dark"] .stat-card-teal { background: linear-gradient(135deg, #0a4a53 0%, #0d7870 100%) !important; }
        body[data-theme="dark"] .stat-card-blue { background: linear-gradient(135deg, #133a60 0%, #1d4a82 100%) !important; }
        body[data-theme="dark"] .stat-card-green { background: linear-gradient(135deg, #0c4d30 0%, #0f6050 100%) !important; }
        body[data-theme="dark"] .stat-card-amber { background: linear-gradient(135deg, #5a3a00 0%, #704800 100%) !important; }
        .nav-tab .tab-icon { font-size: 1.05rem; flex-shrink: 0; }
        table td { padding: 13px 12px; }
        .holiday-panel { margin-top: 22px; border-radius: 12px; border: 1px solid var(--line); overflow: hidden; }
        .holiday-panel > summary {
            cursor: pointer;
            padding: 13px 16px;
            background: var(--bg-1);
            font-weight: 700;
            color: var(--text);
            list-style: none;
            user-select: none;
            display: flex;
            align-items: center;
            gap: 8px;
            transition: background 0.15s ease;
        }
        .holiday-panel > summary:hover { background: var(--bg-2); }
        .holiday-panel > summary::-webkit-details-marker { display: none; }
        .holiday-panel > summary::before { content: '▸'; color: var(--muted); font-size: 0.78rem; }
        .holiday-panel[open] > summary::before { content: '▾'; }
        body[data-theme="dark"] .holiday-panel > summary { background: #111c30; }
        body[data-theme="dark"] .holiday-panel[open] > summary { background: #0f1728; }
        .holiday-panel-body { padding: 16px; border-top: 1px solid var(--line); background: var(--panel); }
        .dashboard-toolbar { display: flex; justify-content: flex-end; margin-bottom: 20px; }

        /* ── Profile Tabs ── */
        .profile-tabs {
            display: flex;
            gap: 6px;
            padding: 12px 0 0;
            border-bottom: 2px solid var(--line);
            margin-bottom: 18px;
            flex-wrap: wrap;
        }
        .profile-tab {
            border: none;
            background: transparent;
            padding: 9px 18px;
            font-weight: 700;
            font-size: 0.9rem;
            color: var(--muted);
            cursor: pointer;
            border-bottom: 3px solid transparent;
            margin-bottom: -2px;
            border-radius: 0;
            transition: 0.18s ease;
        }
        .profile-tab:hover { color: var(--brand); }
        .profile-tab.active { color: var(--brand); border-bottom-color: var(--brand); }
        body[data-theme="dark"] .profile-tab.active { color: var(--accent); border-bottom-color: var(--accent); }
        .profile-tab-content { display: none; }
        .profile-tab-content.active { display: block; animation: fadeIn 0.2s ease; }

        /* ── Profile stat compact ── */
        .profile-stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
            gap: 12px;
            margin-bottom: 16px;
        }

        /* ── Collapsible form panel ── */
        .form-panel {
            border: 1px solid var(--line);
            border-radius: 14px;
            margin-bottom: 16px;
            overflow: hidden;
        }
        .form-panel > summary {
            cursor: pointer;
            list-style: none;
            padding: 13px 16px;
            background: var(--bg-1);
            font-weight: 800;
            color: var(--text);
            display: flex;
            align-items: center;
            gap: 8px;
            user-select: none;
            transition: background 0.15s;
        }
        .form-panel > summary:hover { background: var(--bg-2); }
        .form-panel > summary::-webkit-details-marker { display: none; }
        .form-panel > summary::before { content: '▸'; color: var(--muted); font-size: 0.8rem; transition: transform 0.2s; }
        .form-panel[open] > summary::before { content: '▾'; }
        .form-panel-body { padding: 16px; border-top: 1px solid var(--line); background: var(--panel); }
        body[data-theme="dark"] .form-panel > summary { background: #111c30; }
        body[data-theme="dark"] .form-panel-body { background: #0f1728; }

        /* ── 3-col form row ── */
        .form-row-3 {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
            gap: var(--gap);
        }
        @media (max-width: 980px) { .form-row-3 { grid-template-columns: 1fr 1fr; } }
        @media (max-width: 560px) { .form-row-3 { grid-template-columns: 1fr; } }

        /* ── Section card ── */
        .section-card {
            border: 1px solid var(--line);
            border-radius: 14px;
            padding: 18px;
            background: var(--panel);
            margin-bottom: 18px;
        }
        .section-card + .section-card { margin-top: 16px; }
        .section-card-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 12px;
            margin-bottom: 14px;
            flex-wrap: wrap;
        }
        .section-card-header h2,
        .section-card-header h3 { margin: 0; }
        .section-card-header p {
            margin-top: 6px;
            color: var(--muted);
            font-size: 0.92rem;
        }
        .section-card-actions {
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
            align-items: center;
        }

        /* ── Bluetooth-sync toggle row ── */
        .bt-toggle-row {
            display: flex;
            align-items: center;
            gap: 12px;
            flex-wrap: wrap;
            margin: 14px 0;
        }
        .bt-toggle-row label {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            cursor: pointer;
            font-weight: 600;
        }
        .screen-shell {
            display: grid;
            gap: 16px;
        }
        .screen-shell > .section-card { margin-bottom: 0; }
        .responsive-table-wrap {
            overflow-x: auto;
            -webkit-overflow-scrolling: touch;
        }
        .responsive-table-wrap table { min-width: 760px; }
        /* The patients list carries 9 columns (incl. two currency columns and a
           3-button actions cell); give it room so nothing is cramped — it
           scrolls horizontally on narrow windows and sits comfortably when the
           window is wide. */
        #patients-table { min-width: 960px; }
        .table-meta {
            display: flex;
            justify-content: space-between;
            gap: 12px;
            align-items: center;
            flex-wrap: wrap;
            margin-bottom: 10px;
        }
        .table-meta .table-meta-text { color: var(--muted); font-size: 0.88rem; }
        .table-toolbar { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
        .table-container tbody tr:last-child td { border-bottom: none; }
        /* Cell utilities apply in any table wrapper (.table-container and
           .responsive-table-wrap), so currency never wraps the ₪ onto its
           own line and numbers stay right-aligned. */
        .numeric-cell, th.numeric-cell { text-align: right; white-space: nowrap; }
        .center-cell, th.center-cell { text-align: center; }
        .actions-cell { white-space: nowrap; }
        .loading-state,
        .empty-state,
        .error-state {
            display: grid;
            place-items: center;
            text-align: center;
            padding: 26px 18px;
            border: 1px dashed var(--line);
            border-radius: 14px;
            background: rgba(255, 255, 255, 0.55);
            color: var(--muted);
        }
        body[data-theme="dark"] .loading-state,
        body[data-theme="dark"] .empty-state,
        body[data-theme="dark"] .error-state {
            background: rgba(10, 17, 29, 0.65);
        }
        .state-icon {
            font-size: 1.55rem;
            margin-bottom: 8px;
            line-height: 1;
        }
        .state-title {
            font-weight: 800;
            color: var(--text);
            margin-bottom: 6px;
        }
        .state-text {
            max-width: 460px;
            line-height: 1.55;
            font-size: 0.92rem;
        }
        .state-actions { margin-top: 14px; display: flex; gap: 8px; justify-content: center; flex-wrap: wrap; }
        .badge-neutral { background: #eef4fb; color: #33536d; }
        .badge-active { background: #e0f4e8; color: #166942; }
        .badge-pending { background: #fff1d4; color: #8b5e00; }
        .badge-muted { background: #e9eef5; color: #596a7c; }
        .badge-secondary { background: #e3f1ff; color: #1f5d9e; }
        .badge-blocked { background: #ffe2e5; color: #8d1f33; }
        .section-card-title {
            font-family: 'Space Grotesk', 'Manrope', sans-serif;
            font-size: 0.9rem;
            font-weight: 800;
            letter-spacing: 0.04em;
            text-transform: uppercase;
            color: var(--muted);
            margin-bottom: 14px;
        }
        body[data-theme="dark"] .section-card { background: #0f1728; border-color: #253347; }

        /* ── Readonly info grid ── */
        .info-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
            gap: 10px 16px;
        }
        .info-field label {
            font-size: 0.76rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            color: var(--muted);
            display: block;
            margin-bottom: 3px;
        }
        .info-field span {
            font-size: 0.95rem;
            font-weight: 600;
            color: var(--text);
        }

        /* ── Calc-expression inputs ── */
        .calc-input {
            font-family: 'Manrope', monospace, sans-serif;
            background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='%23627386' stroke-width='2'%3E%3Crect x='4' y='2' width='16' height='20' rx='2'/%3E%3Cline x1='8' y1='6' x2='16' y2='6'/%3E%3Cline x1='8' y1='10' x2='10' y2='10'/%3E%3Cline x1='14' y1='10' x2='16' y2='10'/%3E%3Cline x1='8' y1='14' x2='10' y2='14'/%3E%3Cline x1='14' y1='14' x2='16' y2='14'/%3E%3Cline x1='8' y1='18' x2='10' y2='18'/%3E%3Cline x1='14' y1='18' x2='16' y2='18'/%3E%3C/svg%3E");
            background-repeat: no-repeat;
            background-position: calc(100% - 10px) center;
            background-size: 14px 14px;
            padding-right: 32px !important;
        }
        .calc-input.calc-error {
            border-color: var(--danger) !important;
            box-shadow: 0 0 0 3px rgba(217, 67, 78, 0.15) !important;
        }
        .calc-input.calc-ok {
            border-color: var(--ok) !important;
            box-shadow: 0 0 0 3px rgba(31, 154, 95, 0.12) !important;
        }
        body[data-theme="dark"] .calc-input {
            background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='%239bb0c8' stroke-width='2'%3E%3Crect x='4' y='2' width='16' height='20' rx='2'/%3E%3Cline x1='8' y1='6' x2='16' y2='6'/%3E%3Cline x1='8' y1='10' x2='10' y2='10'/%3E%3Cline x1='14' y1='10' x2='16' y2='10'/%3E%3Cline x1='8' y1='14' x2='10' y2='14'/%3E%3Cline x1='14' y1='14' x2='16' y2='14'/%3E%3Cline x1='8' y1='18' x2='10' y2='18'/%3E%3Cline x1='14' y1='18' x2='16' y2='18'/%3E%3C/svg%3E");
        }

        /* ── Date-picker input wrapper ── */
        .date-input-wrap {
            display: flex;
            gap: 6px;
            align-items: stretch;
        }
        .date-input-wrap input {
            flex: 1;
            min-width: 0;
        }
        .date-picker-btn {
            flex-shrink: 0;
            padding: 0 12px;
            font-size: 1rem;
            line-height: 1;
            border-radius: 10px;
            border: 1px solid #cdd9e6;
            background: linear-gradient(135deg, #f5fbff 0%, #edf6ff 100%);
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: 0.18s ease;
            color: var(--brand);
        }
        .date-picker-btn:hover { background: #e0f0ff; transform: translateY(-1px); }
        body[data-theme="dark"] .date-picker-btn {
            background: #111c30;
            border-color: #2a3951;
            color: var(--accent);
        }

        /* ── Administration sub-tabs ── */
        .admin-sub-tabs {
            display: flex;
            gap: 6px;
            border-bottom: 2px solid var(--line);
            margin-bottom: 18px;
            flex-wrap: wrap;
        }
        .admin-sub-tab {
            border: none;
            background: transparent;
            padding: 10px 20px;
            font-weight: 700;
            font-size: 0.92rem;
            color: var(--muted);
            cursor: pointer;
            border-bottom: 3px solid transparent;
            margin-bottom: -2px;
            border-radius: 0;
            transition: 0.18s ease;
            display: flex;
            align-items: center;
            gap: 7px;
        }
        .admin-sub-tab:hover { color: var(--brand); transform: translateY(-2px); text-shadow: 0 0 8px rgba(30, 136, 229, 0.2); }
        .admin-sub-tab.active { color: var(--brand); border-bottom-color: var(--brand); text-shadow: 0 0 8px rgba(30, 136, 229, 0.3); background: linear-gradient(0deg, rgba(62, 168, 255, 0.08) 0%, transparent 100%); }
        body[data-theme="dark"] .admin-sub-tab.active { color: var(--accent); border-bottom-color: var(--accent); text-shadow: 0 0 12px rgba(62, 168, 255, 0.5); background: linear-gradient(0deg, rgba(62, 168, 255, 0.15) 0%, transparent 100%); }
        .admin-sub-tab-content { display: none; }
        .admin-sub-tab-content.active { display: block; animation: fadeIn 0.2s ease; }
        .admin-overview-cards {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 14px;
            margin-bottom: 22px;
        }
        /* ── Odontogram ──────────────────────────────────────── */
        .odontogram-card { padding: 16px; }
        .arch { margin: 4px 0; overflow: visible; }
        .tooth { cursor: pointer; transition: filter 150ms ease; }
        .tooth:hover, .tooth:focus-visible { filter: brightness(0.88) drop-shadow(0 2px 4px rgba(0,0,0,.3)); outline: none; }
        .tooth:focus-visible { filter: brightness(0.88) drop-shadow(0 0 0 3px var(--brand, #2563eb)); }
        .tooth-num { font-size: 9px; fill: var(--muted, #64748b); font-weight: 700; font-family: inherit; }
        .tooth-legend { display: flex; flex-wrap: wrap; gap: 8px 14px; margin-top: 10px; }
        .tooth-legend span { display: inline-flex; align-items: center; gap: 5px; font-size: 12px; color: var(--text, #1e293b); }
        .tooth-legend i { width: 12px; height: 12px; border-radius: 3px; display: inline-block; border: 1px solid #334155; flex-shrink: 0; }
        [data-theme="dark"] .tooth-num { fill: #94a3b8; }
        [data-theme="dark"] path[stroke="#94a3b8"] { stroke: #475569; }
        [dir="rtl"] .tooth-row { transform: scaleX(-1); }
        [dir="rtl"] .tooth-num { transform: scaleX(-1); transform-origin: center; }
        .hidden { display:none; }
        .license-banner { display:flex; gap:12px; align-items:center; padding:10px 16px;
          background:#fff4ce; color:#5c4400; font-size:.9rem; }
        .license-banner--warn { background:#ffe2e5; color:#8d1f33; }
        .license-overlay { position:fixed; inset:0; background:rgba(15,23,42,.78);
          display:flex; align-items:center; justify-content:center; z-index:9999; }
        .license-overlay__card { background:#fff; padding:28px; border-radius:14px;
          width:min(440px,92vw); box-shadow:0 24px 60px rgba(0,0,0,.35); }
        .license-overlay__card textarea { width:100%; margin:12px 0; font-family:monospace; }
        .license-overlay__status { margin-top:10px; min-height:18px; font-size:.85rem; }
        body.view-only [data-write] { pointer-events:none; opacity:.5; }
    </style>
</head>
<body>
    <div id="license-renew-banner" class="license-banner hidden">
      <span id="license-renew-text"></span>
      <button type="button" onclick="openLicenseActivation()">Renew</button>
      <button type="button" onclick="dismissRenewBanner()">Dismiss</button>
    </div>
    <div id="license-viewonly-banner" class="license-banner license-banner--warn hidden">
      <span>License inactive — view only. Renew to make changes.</span>
      <button type="button" onclick="openLicenseActivation()">Renew</button>
    </div>
    <div id="license-gate-overlay" class="license-overlay hidden">
      <div class="license-overlay__card">
        <h2>Activate this clinic</h2>
        <p>Paste the serial token from your vendor to activate.</p>
        <textarea id="license-gate-token" rows="4" placeholder="serial token"></textarea>
        <button type="button" onclick="submitLicenseActivation()">Activate</button>
        <div id="license-gate-status" class="license-overlay__status"></div>
        <div id="license-link-panel" class="hidden">
          <h2>Enable secure cloud backup?</h2>
          <p>Back up this clinic to the cloud. You can do this later in Settings.</p>
          <button type="button" id="license-link-cloud" onclick="linkCloud()">Enable secure cloud backup</button>
          <button type="button" id="license-link-skip" onclick="skipCloudLink()">Not now</button>
          <div id="license-link-status" class="license-overlay__status"></div>
        </div>
      </div>
    </div>
    <div class="container">
        <div class="header">
            <div class="header-accent-line"></div>
            <div class="header-top">
                <div class="header-brand">
                    <div class="header-logo-mark">
                        <img src="/logo" alt="DentaCare" class="header-logo-img">
                    </div>
                    <div class="header-text">
                        <div class="header-system-name" data-i18n="title">{{ SYSTEM_NAME }}</div>
                        <div class="header-clinic-name">{{ CLINIC_NAME }}</div>
                    </div>
                </div>
                <div class="header-meta">
                    <div class="doctor-badge" id="doctor-badge-el" onclick="toggleDoctorEditPopover(event)" title="Click to edit doctor name">
                        <span data-i18n="doctor_name" class="doctor-badge-name" id="doctor-name-display">{{ DOCTOR_NAME }}</span>
                        <span class="doctor-edit-icon">✏ edit</span>
                    </div>
                    <button id="theme-toggle" class="theme-toggle" title="Night Mode" aria-label="Night Mode">🌙</button>
                    <button id="language-toggle" class="language-toggle">EN</button>
                    <a id="logout-link" href="/logout" class="language-toggle" style="text-decoration:none;display:inline-flex;align-items:center;" title="Sign out" data-i18n="logout">Logout</a>
                </div>
            </div>
        </div>

        <div class="header-bridge"></div>
        <div class="app-body">
        <div class="nav-tabs" id="main-nav">
            <div class="nav-tabs-label" data-i18n="navigation">Navigation</div>

            <button class="nav-tab active" data-tab="dashboard" onclick="switchTab('dashboard', this)">
                <span class="tab-icon">🏠</span>
                <span data-en="Dashboard" data-ar="لوحة المعلومات">Dashboard</span>
            </button>
            <button class="nav-tab" data-tab="patients" onclick="switchTab('patients', this)">
                <span class="tab-icon">👥</span>
                <span data-en="Patients" data-ar="المرضى">Patients</span>
            </button>

            <div class="nav-group-label" data-i18n="scheduling">Scheduling</div>
            <button class="nav-tab" data-tab="appointments" onclick="switchTab('appointments', this)">
                <span class="tab-icon">📅</span>
                <span data-en="Appointments" data-ar="المواعيد">Appointments</span>
            </button>

            <div class="nav-group-label" data-i18n="financial">Financial</div>
            <button class="nav-tab" data-tab="financial" onclick="switchTab('financial', this)">
                <span class="tab-icon">💰</span>
                <span data-en="Billing" data-ar="المالي">Billing</span>
            </button>
            <button class="nav-tab" data-tab="reports" onclick="switchTab('reports', this)">
                <span class="tab-icon">📊</span>
                <span data-en="Reports" data-ar="التقارير">Reports</span>
            </button>

            <div class="nav-group-label" data-i18n="management">Management</div>
            <button class="nav-tab" data-tab="treatments" onclick="switchTab('treatments', this)">
                <span class="tab-icon">🗂️</span>
                <span data-en="Catalog" data-ar="الفهرس">Catalog</span>
            </button>
            <button class="nav-tab" data-tab="support" onclick="switchTab('support', this)">
                <span class="tab-icon">🔧</span>
                <span data-en="Settings" data-ar="الإعدادات">Settings</span>
            </button>
        </div>

        <div class="content">
            <!-- Dashboard Tab -->
            <div id="dashboard" class="tab-content active">
                <div class="screen-shell">
                    <div class="section-card">
                        <div class="section-card-header">
                            <div>
                                <h2 data-i18n="dashboard_overview">Dashboard Overview</h2>
                                <p data-i18n="dashboard_summary">Snapshot of today's activity, totals, and recent appointments.</p>
                            </div>
                            <div class="section-card-actions">
                                <span id="cloud-sync-badge" style="display:none;align-self:center;font-size:0.85em;color:var(--muted);"></span>
                                <button class="btn btn-primary" onclick="downloadBackup()" data-i18n="download_backup">💾 Download Backup</button>
                            </div>
                        </div>
                        <div class="stats-grid" id="stats-grid">
                            <div class="stat-card stat-card-teal">
                                <span class="stat-icon">👥</span>
                                <h3 id="total-patients">0</h3>
                                <p data-i18n="total_patients">Total Patients</p>
                            </div>
                            <div class="stat-card stat-card-blue">
                                <span class="stat-icon">📅</span>
                                <h3 id="today-appointments">0</h3>
                                <p data-i18n="todays_appointments">Today's Appointments</p>
                            </div>
                            <div class="stat-card stat-card-green">
                                <span class="stat-icon">🩺</span>
                                <h3 id="total-visits">0</h3>
                                <p data-i18n="todays_visits">Today's Visits</p>
                            </div>
                            <div class="stat-card stat-card-amber">
                                <span class="stat-icon">💰</span>
                                <h3 id="total-revenue">₪ 0</h3>
                                <p data-i18n="todays_revenue">Today's Revenue</p>
                            </div>
                        </div>
                    </div>

                    <div class="section-card table-shell">
                        <div class="table-meta">
                            <div>
                                <div class="section-card-title" data-i18n="recent_appointments">Recent Appointments</div>
                                <div class="table-meta-text" data-i18n="recent_appointments_hint">Latest scheduled visits and their current status.</div>
                            </div>
                        </div>
                        <div class="responsive-table-wrap">
                            <table id="recent-appointments-table">
                                <thead>
                                    <tr>
                                        <th data-i18n="patient">Patient</th>
                                        <th data-i18n="date_time">Date & Time</th>
                                        <th data-i18n="treatment_type">Treatment Type</th>
                                        <th class="center-cell" data-i18n="status">Status</th>
                                    </tr>
                                </thead>
                                <tbody id="recent-appointments-body"></tbody>
                            </table>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- Patients Tab -->
            <div id="patients" class="tab-content">
                <div class="screen-shell">
                    <div class="section-card">
                        <div class="section-card-header">
                            <div>
                                <h2 data-i18n="patient_management">Patient Management</h2>
                                <p data-i18n="patient_management_summary">Search, open, and manage patient records from one place.</p>
                            </div>
                            <div class="section-card-actions">
                                <button class="btn btn-primary" onclick="showAddPatientModal()" data-i18n="add_new_patient">+ Add New Patient</button>
                            </div>
                        </div>
                        <div class="form-row" style="margin-top:0; margin-bottom:0;">
                            <div class="form-group" style="margin-bottom:0;">
                                <label data-i18n="search_by_name_phone_email">Search by name, phone, or email</label>
                                <input type="text" id="patient-search-input" data-i18n-placeholder="search_placeholder" placeholder="Type patient name, phone, or email" oninput="filterPatientsTable()">
                            </div>
                            <div class="form-group" style="margin-bottom:0; display:flex; align-items:flex-end; gap:10px;">
                                <button class="btn btn-primary" type="button" onclick="openFirstPatientMatch()" data-i18n="open_patient_by_name">Open Patient by Name</button>
                                <button class="btn btn-warning" type="button" onclick="clearPatientSearch()" data-i18n="clear">Clear</button>
                            </div>
                        </div>
                        <div id="patient-search-status" class="search-status" data-i18n="showing_all_patients">Showing all patients.</div>
                    </div>

                    <div class="section-card table-shell">
                        <div class="table-meta">
                            <div>
                                <div class="section-card-title" data-i18n="patients_list">Patients</div>
                                <div class="table-meta-text" data-i18n="patients_list_hint">Patient details, quick access, and row actions.</div>
                            </div>
                        </div>
                        <div class="responsive-table-wrap">
                            <table id="patients-table">
                                <thead>
                                    <tr>
                                        <th class="center-cell">ID</th>
                                        <th data-i18n="name">Name</th>
                                        <th data-i18n="date_of_birth">Date of Birth</th>
                                        <th data-i18n="gender">Gender</th>
                                        <th data-i18n="phone">Phone</th>
                                        <th class="center-cell" data-i18n="appointments">Appointments</th>
                                        <th class="numeric-cell" data-i18n="finance">Finance</th>
                                        <th class="numeric-cell" data-i18n="balance">Balance</th>
                                        <th class="center-cell" data-i18n="actions">Actions</th>
                                    </tr>
                                </thead>
                                <tbody id="patients-body"></tbody>
                            </table>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Appointments Tab -->
            <div id="appointments" class="tab-content">
                <div class="screen-shell">
                    <div class="section-card">
                        <div class="section-card-header">
                            <div>
                                <h2 data-i18n="appointments">Appointments</h2>
                                <p data-i18n="appointments_summary">Track upcoming, confirmed, and completed visits.</p>
                            </div>
                            <div class="section-card-actions">
                                <button class="btn btn-primary" onclick="showAddAppointmentModal()" data-i18n="schedule_appointment">+ Schedule Appointment</button>
                            </div>
                        </div>
                    </div>

                    <!-- CALENDAR sub-tab -->
                    <div id="appointments-calendar-view" style="margin-top:20px;" class="">
                        <div class="section-card">
                            <div class="section-card-header">
                                <div>
                                    <div class="section-card-title" data-i18n="calendar">Calendar</div>
                                    <div class="table-meta-text" data-i18n="calendar_summary">Move between months, inspect day cards, and manage holidays.</div>
                                </div>
                                <div class="section-card-actions">
                                    <button class="btn btn-warning" type="button" onclick="loadAppointments()" data-i18n="refresh">Refresh</button>
                                </div>
                            </div>
                            <div class="calendar-controls">
                                <div class="toolbar-row" style="margin-top:0;">
                                    <button class="btn btn-warning" type="button" onclick="changeCalendarMonth(-1)" data-i18n="previous_month">Previous Month</button>
                                    <button class="btn btn-warning" type="button" onclick="goToCurrentCalendarMonth()" data-i18n="current_month">Current Month</button>
                                    <button class="btn btn-warning" type="button" onclick="changeCalendarMonth(1)" data-i18n="next_month">Next Month</button>
                                </div>
                                <div id="calendar-month-label" class="calendar-month-title"></div>
                            </div>
                            <div id="appointments-calendar" class="appointments-calendar"></div>
                        </div>

                        <details class="holiday-panel section-card">
                            <summary>📆 <span data-i18n="holiday_management">Holiday Management</span></summary>
                            <div class="holiday-panel-body">
                                <form id="holiday-form">
                                    <div class="form-row">
                                        <div class="form-group">
                                            <label data-i18n="holiday_date">Holiday Date *</label>
                                            <div class="date-input-wrap"><input type="text" name="holiday_date" id="holiday-date" placeholder="DD/MM/YYYY" data-date-field="1" title="Enter date in DD/MM/YYYY format" required><button type="button" class="date-picker-btn" title="Pick date" aria-label="Pick date">📅</button></div>
                                        </div>
                                        <div class="form-group">
                                            <label data-i18n="holiday_name">Holiday Name *</label>
                                            <input type="text" name="name" required>
                                        </div>
                                    </div>
                                    <div class="form-group">
                                        <label data-i18n="notes">Notes</label>
                                        <textarea name="notes" data-i18n-placeholder="optional_note" placeholder="Optional note"></textarea>
                                    </div>
                                    <button class="btn btn-primary" type="submit" data-i18n="add_holiday">Add Holiday</button>
                                </form>
                                <div class="table-container" style="margin-top:16px;">
                                    <table>
                                        <thead>
                                            <tr>
                                                <th data-i18n="date">Date</th>
                                                <th data-i18n="holiday">Holiday</th>
                                                <th data-i18n="notes">Notes</th>
                                                <th data-i18n="actions">Actions</th>
                                            </tr>
                                        </thead>
                                        <tbody id="holidays-body"><tr><td colspan="4" data-i18n="no_holidays_yet">No holidays yet</td></tr></tbody>
                                    </table>
                                </div>
                            </div>
                        </details>
                    </div><!-- /appointments-calendar-view -->

                    <!-- LIST sub-tab -->
                    <div id="appointments-list-view" class="section-card table-shell" style="margin-top:20px;">
                        <div class="table-meta">
                            <div>
                                <div class="section-card-title" data-i18n="appointments_list">Appointments</div>
                                <div class="table-meta-text" data-i18n="appointments_list_hint">Sorted appointment list with status badges and duration.</div>
                            </div>
                        </div>
                        <div class="responsive-table-wrap">
                            <table id="appointments-table">
                                <thead>
                                    <tr>
                                        <th class="center-cell">ID</th>
                                        <th data-i18n="patient">Patient</th>
                                        <th data-i18n="date_time">Date &amp; Time</th>
                                        <th class="numeric-cell" data-i18n="duration">Duration</th>
                                        <th data-i18n="treatment_type">Treatment Type</th>
                                        <th class="center-cell" data-i18n="status">Status</th>
                                    </tr>
                                </thead>
                                <tbody id="appointments-body"></tbody>
                            </table>
                        </div>
                    </div>
                </div>
            </div><!-- /appointments -->

            <!-- Catalog Tab (Procedure Catalog) -->
            <div id="treatments" class="tab-content">
                <div class="screen-shell">
                    <div class="section-card">
                        <div class="section-card-header">
                            <div>
                                <h2 data-i18n="catalog">Catalog</h2>
                                <p data-i18n="catalog_summary">Manage the clinic's procedure catalog from one place.</p>
                            </div>
                        </div>
                        <div class="admin-overview-cards">
                            <div class="stat-card stat-card-teal">
                                <span class="stat-icon">🗂️</span>
                                <h3 id="treatments-procedure-count">0</h3>
                                <p data-i18n="procedure_catalog_items">Procedure Catalog Items</p>
                            </div>
                        </div>
                    </div>

                    <div class="section-card">
                        <!-- ── Procedure Catalog ── -->
                        <div id="catalog-subtab-procedure" class="admin-sub-tab-content active">
                            <details id="catalog-procedure-panel" class="form-panel" open ontoggle="if(this.open&&typeof handleProcedureCatalogToggle==='function')handleProcedureCatalogToggle(this)">
                                <summary>➕ <span data-i18n="save_procedure">Add / Edit Procedure</span></summary>
                                <div class="form-panel-body">
                                    <form id="procedure-form">
                                        <input type="hidden" id="procedure-id" value="">
                                        <div class="form-row-3">
                                            <div class="form-group">
                                                <label data-i18n="procedure_name_required">Procedure Name *</label>
                                                <input type="text" id="procedure-name" required>
                                            </div>
                                            <div class="form-group">
                                                <label data-i18n="default_price">Default Price <small style="font-weight:400;color:var(--muted);">(or expression)</small></label>
                                                <input type="text" inputmode="decimal" id="procedure-default-price" value="0" class="calc-input" data-calc-field="1" placeholder="0" autocomplete="off">
                                            </div>
                                            <div class="form-group">
                                                <label data-i18n="default_lab_expense">Default Lab Expense <small style="font-weight:400;color:var(--muted);">(or expression)</small></label>
                                                <input type="text" inputmode="decimal" id="procedure-default-lab-expense" value="0" class="calc-input" data-calc-field="1" placeholder="0" autocomplete="off">
                                            </div>
                                        </div>
                                        <div class="toolbar-row" style="margin-top:0; margin-bottom:10px;">
                                            <label style="display:flex; gap:8px; align-items:center; font-weight:600;">
                                                <input type="checkbox" id="procedure-requires-lab">
                                                <span data-i18n="requires_lab">Requires Lab</span>
                                            </label>
                                            <label style="display:flex; gap:8px; align-items:center; font-weight:600;">
                                                <input type="checkbox" id="procedure-active" checked>
                                                <span data-i18n="active">Active</span>
                                            </label>
                                        </div>
                                        <div class="toolbar-row" style="margin-top:0; margin-bottom:10px;">
                                            <button class="btn btn-primary" type="submit" id="procedure-save-btn" data-i18n="save_procedure">Save Procedure</button>
                                            <button class="btn btn-warning" type="button" id="procedure-cancel-btn" onclick="resetProcedureForm()" data-i18n="cancel">Cancel</button>
                                        </div>
                                    </form>
                                </div>
                            </details>
                            <div class="table-container" style="margin-top:12px;">
                                <table>
                                    <thead>
                                        <tr>
                                            <th data-i18n="procedure_name">Procedure</th>
                                            <th class="center-cell" data-i18n="requires_lab">Requires Lab</th>
                                            <th class="numeric-cell" data-i18n="default_price">Default Price</th>
                                            <th class="numeric-cell" data-i18n="default_lab_expense">Default Lab Expense</th>
                                            <th class="center-cell" data-i18n="active">Active</th>
                                            <th class="actions-cell" data-i18n="actions">Actions</th>
                                        </tr>
                                    </thead>
                                    <tbody id="procedures-body"><tr><td colspan="6" data-i18n="no_data">No data</td></tr></tbody>
                                </table>
                            </div>
                        </div><!-- /catalog-subtab-procedure -->
                    </div><!-- /section-card -->

                    <!-- ── Tooth Conditions Admin ── -->
                    <div class="section-card">
                        <div class="card">
                            <h3 data-i18n="tooth_conditions">Tooth conditions</h3>
                            <div id="tooth-conditions-table"></div>
                            <div class="form-row" style="display:flex;gap:8px;flex-wrap:wrap;margin-top:10px;">
                                <input type="text" id="tc-name" placeholder="Name">
                                <input type="text" id="tc-name-ar" placeholder="الاسم">
                                <input type="color" id="tc-color" value="#9ca3af">
                                <input type="number" id="tc-sort" placeholder="#" style="width:64px;">
                                <button class="btn btn-primary" id="tc-add" data-i18n="add">Add</button>
                            </div>
                        </div>
                    </div>

                </div>
            </div><!-- /treatments -->

            <div id="reports" class="tab-content">
                <div class="page-header">
                    <h2 data-i18n="reporting_system">Reporting System</h2>
                </div>
                <div class="sub-tabs" id="reports-sub-tabs">
                    <button class="sub-tab active" onclick="switchReportsSubTab('weekly', this)" data-i18n="weekly_tab">Weekly</button>
                    <button class="sub-tab" onclick="switchReportsSubTab('monthly', this)" data-i18n="monthly_tab">Monthly</button>
                    <button class="sub-tab" onclick="switchReportsSubTab('lab', this)" data-i18n="lab_tab">Lab</button>
                </div>

                <div id="reports-subtab-weekly" class="sub-tab-content active">
                    <div class="toolbar-row" style="margin-top:0; align-items:flex-end;">
                        <div class="form-group" style="margin:0;">
                            <label data-i18n="start_date">Start Date</label>
                            <input type="date" id="weekly-start-picker">
                        </div>
                        <button class="btn btn-success" onclick="loadWeeklyReport()" data-i18n="this_week">This Week</button>
                        <button class="btn btn-primary" onclick="loadWeeklyReportFromPicker()" data-i18n="run_report">Run Report</button>
                    </div>
                    <div id="weekly-report-range" class="search-status" data-i18n="weekly_range_not_selected">Weekly range not selected.</div>
                </div>

                <div id="reports-subtab-monthly" class="sub-tab-content">
                    <div class="form-row">
                        <div class="form-group">
                            <label data-i18n="month">Month</label>
                            <input type="month" id="report-month-picker">
                        </div>
                    </div>
                    <div class="toolbar-row" style="margin-top:0;">
                        <button class="btn btn-primary" onclick="loadMonthlyReport()" data-i18n="run_monthly_report">Run Monthly Report</button>
                    </div>
                </div>

                <div id="reports-subtab-lab" class="sub-tab-content">
                    <div class="form-row">
                        <div class="form-group">
                            <label data-i18n="start_date">Start Date</label>
                            <input type="date" id="report-start-date">
                        </div>
                        <div class="form-group">
                            <label data-i18n="end_date">End Date</label>
                            <input type="date" id="report-end-date">
                        </div>
                    </div>
                    <div class="toolbar-row" style="margin-top:0;">
                        <button class="btn btn-primary" onclick="loadLabReport()" data-i18n="run_lab_report">Run Lab Report</button>
                    </div>

                    <!-- Procedure Catalog moved to Administration tab -->

                    <!-- Treatment Catalog moved to Administration tab -->
                </div>

                <div class="stats-grid" style="margin-top:20px;">
                    <div class="stat-card"><h3 id="report-visits">0</h3><p data-i18n="visits">Visits</p></div>
                    <div class="stat-card"><h3 id="report-revenue">₪ 0</h3><p data-i18n="revenue">Revenue</p></div>
                    <div class="stat-card"><h3 id="report-expenses">₪ 0</h3><p data-i18n="expenses">Expenses</p></div>
                    <div class="stat-card"><h3 id="report-lab-expenses">₪ 0</h3><p data-i18n="lab_expenses">Lab Expenses</p></div>
                    <div class="stat-card"><h3 id="report-clinic-gross-profit">₪ 0</h3><p data-i18n="clinic_gross_profit">Clinic Gross Profit</p></div>
                    <div class="stat-card"><h3 id="report-profit">₪ 0</h3><p data-i18n="profit">Profit</p></div>
                    <div class="stat-card"><h3 id="report-receivables-total">₪ 0</h3><p data-i18n="unpaid_by_patients">Unpaid by Patients</p></div>
                </div>
                <h3 style="margin-top:20px;" data-i18n="outstanding_balances">Outstanding Balances (current)</h3>
                <div class="table-container" style="margin-top:12px;">
                    <table>
                        <thead>
                            <tr>
                                <th data-i18n="patient_name">Patient Name</th>
                                <th data-i18n="total_to_pay">Total to Pay</th>
                                <th data-i18n="paid">Paid</th>
                                <th data-i18n="left">Left</th>
                                <th data-i18n="last_date">Last Date</th>
                                <th data-i18n="overdue_days">Overdue Days</th>
                            </tr>
                        </thead>
                        <tbody id="report-receivables-body"><tr><td colspan="6" data-i18n="no_data">No data</td></tr></tbody>
                    </table>
                </div>
            </div>

            <div id="financial" class="tab-content">
                <div class="screen-shell">
                    <div class="section-card">
                        <div class="section-card-header">
                            <div>
                                <h2 data-i18n="financial_management">Financial Management</h2>
                                <p data-i18n="financial_summary">Review receivables, expenses, billing, and invoice summaries.</p>
                            </div>
                        </div>
                    </div>
                    <div class="sub-tabs" id="financial-sub-tabs">
                    <button class="sub-tab active" onclick="switchFinancialSubTab('management', this)" data-i18n="management_tab">Management</button>
                    <button class="sub-tab" onclick="switchFinancialSubTab('billing', this)" data-i18n="payments_tab">💳 Payments</button>
                    <button class="sub-tab" onclick="switchFinancialSubTab('invoices', this)" data-i18n="statement_tab">📄 Statement</button>
                    </div>

                    <div id="financial-subtab-management" class="sub-tab-content active section-card">

                <h3 style="margin-top:20px;" data-i18n="receivables_tracking">Receivables Tracking</h3>
                <div class="stats-grid" style="margin-top:10px; margin-bottom:10px;">
                    <div class="stat-card"><h3 id="receivables-total">₪ 0</h3><p data-i18n="total_receivables">Total Receivables</p></div>
                    <div class="stat-card"><h3 id="receivables-count">0</h3><p data-i18n="patients_with_balance">Patients with Balance</p></div>
                </div>
                <div class="table-container" style="margin-top:12px;">
                    <table>
                        <thead>
                            <tr>
                                <th data-i18n="patient_name">Patient Name</th>
                                <th data-i18n="total_to_pay">Total to Pay</th>
                                <th data-i18n="paid">Paid</th>
                                <th data-i18n="left">Left</th>
                                <th data-i18n="last_date">Last Date</th>
                                <th data-i18n="overdue_days">Overdue Days</th>
                            </tr>
                        </thead>
                        <tbody id="receivables-body"><tr><td colspan="6" data-i18n="no_data">No data</td></tr></tbody>
                    </table>
                </div>

                <details class="form-panel" open>
                <summary>➕ <span data-i18n="expense_tracking">Expense Tracking</span></summary>
                <div class="form-panel-body">
                <div class="toolbar-row" style="margin-top:0; margin-bottom:10px;">
                    <label for="expense-filter-period" style="font-weight:600;" data-i18n="period">Period:</label>
                    <select id="expense-filter-period" onchange="loadExpenses()" style="max-width:190px;">
                        <option value="all" data-i18n="all">All</option>
                        <option value="today" data-i18n="today">Today</option>
                        <option value="week" data-i18n="this_week">This Week</option>
                        <option value="month" data-i18n="this_month">This Month</option>
                    </select>
                    <label for="expense-filter-status-select" style="font-weight:600;" data-i18n="status">Status:</label>
                    <select id="expense-filter-status-select" onchange="loadExpenses()" style="max-width:190px;">
                        <option value="all" data-i18n="all_status">All Status</option>
                        <option value="paid" data-i18n="paid">Paid</option>
                        <option value="postponed" data-i18n="postponed">Postponed</option>
                    </select>
                </div>
                <div id="expense-filter-status" class="search-status" style="margin-bottom:12px;" data-i18n="showing_all_expenses">Showing all expenses.</div>
                <form id="expense-form">
                    <div class="form-row-3">
                        <div class="form-group">
                            <label data-i18n="category_required">Category *</label>
                            <input type="text" name="category" required>
                        </div>
                        <div class="form-group">
                            <label data-i18n="amount_required">Amount (₪) *<small style="font-weight:400;color:var(--muted);"> (or expression)</small></label>
                            <input type="text" inputmode="decimal" name="amount" class="calc-input" data-calc-field="1" placeholder="0" autocomplete="off" required>
                        </div>
                        <div class="form-group">
                            <label data-i18n="vendor">Vendor</label>
                            <input type="text" name="vendor">
                        </div>
                    </div>
                    <div class="form-row">
                        <div class="form-group">
                            <label data-i18n="date_required">Date *</label>
                            <div class="date-input-wrap"><input type="text" name="expense_date" id="expense-date" placeholder="DD/MM/YYYY" data-date-field="1" title="Enter date in DD/MM/YYYY format" required><button type="button" class="date-picker-btn" title="Pick date" aria-label="Pick date">📅</button></div>
                        </div>
                        <div class="form-group">
                            <label data-i18n="status_required">Status *</label>
                            <select name="payment_status" required>
                                <option value="paid" data-i18n="paid">Paid</option>
                                <option value="postponed" data-i18n="postponed">Postponed</option>
                            </select>
                        </div>
                    </div>
                    <div class="form-group">
                        <label data-i18n="notes">Notes</label>
                        <textarea name="notes" data-i18n-placeholder="optional_note" placeholder="Optional note" style="min-height: 48px;"></textarea>
                    </div>
                    <button class="btn btn-primary" type="submit" data-i18n="add_expense">Add Expense</button>
                </form>
                </div>
                </details>
                <div class="table-container" style="margin-top:16px;">
                    <table>
                        <thead>
                            <tr>
                                <th data-i18n="date">Date</th>
                                <th data-i18n="category">Category</th>
                                <th data-i18n="amount">Amount</th>
                                <th data-i18n="status">Status</th>
                                <th data-i18n="vendor">Vendor</th>
                                <th data-i18n="notes">Notes</th>
                                <th data-i18n="actions">Actions</th>
                            </tr>
                        </thead>
                        <tbody id="expenses-body"><tr><td colspan="7" data-i18n="no_expenses_yet">No expenses yet</td></tr></tbody>
                    </table>
                </div>
                </div>

                    <div id="financial-subtab-billing" class="sub-tab-content section-card">

                <details class="form-panel" open>
                <summary>➕ <span data-i18n="payment_management">Payment Record</span></summary>
                <div class="form-panel-body">
                <form id="billing-form">
                    <div class="form-row">
                        <div class="form-group">
                            <label data-i18n="patient_required">Patient *</label>
                            <select name="patient_id" id="billing-patient-select" required>
                                <option value="" data-i18n="select_patient">Select Patient</option>
                            </select>
                        </div>
                        <div class="form-group">
                            <label data-i18n="date">Date</label>
                            <div class="date-input-wrap"><input type="text" name="payment_date" id="billing-date" placeholder="DD/MM/YYYY" data-date-field="1" title="Enter date in DD/MM/YYYY format"><button type="button" class="date-picker-btn" title="Pick date" aria-label="Pick date">📅</button></div>
                        </div>
                    </div>
                    <div class="form-row-3">
                        <div class="form-group">
                            <label data-i18n="subtotal_required">Subtotal *<small style="font-weight:400;color:var(--muted);"> (or expression)</small></label>
                            <input type="text" inputmode="decimal" name="subtotal" id="billing-subtotal" class="calc-input" data-calc-field="1" placeholder="0" autocomplete="off" required>
                        </div>
                        <div class="form-group">
                            <label data-i18n="discount">Discount <small style="font-weight:400;color:var(--muted);">(or %, e.g. 20%)</small></label>
                            <input type="text" inputmode="decimal" name="discount" value="0" class="calc-input" data-calc-field="1" data-percent-base="billing-subtotal" placeholder="0" autocomplete="off">
                        </div>
                        <div class="form-group">
                            <label>Credit Used <small id="billing-credit-available" style="font-weight:400;color:var(--muted);"></small></label>
                            <input type="text" inputmode="decimal" name="credit_used" value="0" id="billing-credit-used" class="calc-input" data-calc-field="1" placeholder="0" autocomplete="off">
                        </div>
                    </div>
                    <div class="form-row">
                        <div class="form-group">
                            <label data-i18n="paid_amount">Paid Amount</label>
                            <input type="text" inputmode="decimal" name="paid_amount" value="0" class="calc-input" data-calc-field="1" placeholder="0" autocomplete="off">
                        </div>
                        <div class="form-group">
                            <label data-i18n="payment_method">Payment Method</label>
                            <select name="payment_method">
                                <option value="Cash" data-i18n="cash">Cash</option>
                                <option value="Card" data-i18n="card">Card</option>
                                <option value="Transfer" data-i18n="transfer">Transfer</option>
                            </select>
                        </div>
                    </div>
                    <button class="btn btn-primary" type="submit" data-i18n="record_payment">Record Payment</button>
                </form>
                </div>
                </details>
                <div class="table-container" id="billing-history-container" style="margin-top:12px;display:none;">
                    <div class="section-card-header" style="margin-bottom:12px;">
                        <div>
                            <h3 id="billing-history-title" style="margin:0;" data-i18n="payment_history">Payment History</h3>
                            <p style="margin:3px 0 0;color:var(--muted);font-size:0.86em;" data-i18n="payment_history_meta">Every payment recorded for this patient — from the follow-up sheet and from payment records.</p>
                        </div>
                        <button class="btn btn-secondary" type="button" onclick="clearBillingPatientFilter()" data-i18n="show_all_records">Show all records</button>
                    </div>
                    <table>
                        <thead>
                            <tr>
                                <th data-i18n="date">Date</th>
                                <th data-i18n="source">Source</th>
                                <th data-i18n="description">Description</th>
                                <th data-i18n="payment_method">Payment Method</th>
                                <th data-i18n="amount_paid">Amount Paid</th>
                            </tr>
                        </thead>
                        <tbody id="billing-history-body"></tbody>
                        <tfoot id="billing-history-foot"></tfoot>
                    </table>
                </div>
                <div class="table-container" id="billing-all-container" style="margin-top:12px;">
                    <table>
                        <thead>
                            <tr>
                                <th data-i18n="invoice_no">Invoice #</th>
                                <th data-i18n="patient">Patient</th>
                                <th data-i18n="amount">Amount</th>
                                <th data-i18n="paid_amount">Paid Amount</th>
                                <th data-i18n="balance_due">Balance Due</th>
                                <th data-i18n="status">Status</th>
                                <th data-i18n="date">Date</th>
                                <th data-i18n="actions">Actions</th>
                            </tr>
                        </thead>
                        <tbody id="billing-body"><tr><td colspan="8" data-i18n="no_data">No data</td></tr></tbody>
                    </table>
                </div>
                </div>

                    <div id="financial-subtab-invoices" class="sub-tab-content section-card">

                <h3 style="margin-top:20px;" data-i18n="patient_statement">Patient Statement</h3>
                <div class="form-row">
                    <div class="form-group">
                        <label data-i18n="patient_required">Patient *</label>
                        <select id="invoice-patient-select">
                            <option value="" data-i18n="select_patient">Select Patient</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label data-i18n="start_date">Start Date</label>
                        <input type="date" id="invoice-start-date">
                    </div>
                    <div class="form-group">
                        <label data-i18n="end_date">End Date</label>
                        <input type="date" id="invoice-end-date">
                    </div>
                </div>
                <div class="toolbar-row" style="margin-top:0; margin-bottom:10px; align-items:flex-end;">
                    <div class="form-group" style="margin:0; min-width:220px;">
                        <label for="invoice-print-language" data-i18n="print_language">Print Language</label>
                        <select id="invoice-print-language">
                            <option value="current" data-i18n="print_language_current">Current App Language</option>
                            <option value="ar" data-i18n="print_language_arabic">Arabic</option>
                            <option value="en" data-i18n="print_language_english">English</option>
                        </select>
                    </div>
                    <button class="btn btn-success" type="button" onclick="loadPatientInvoiceSummary()" data-i18n="generate_total_invoice">Generate Total Invoice</button>
                    <button class="btn btn-primary" type="button" onclick="printCurrentPatientInvoice()" data-i18n="print_invoice">Print Invoice</button>
                </div>
                <div class="stats-grid" style="margin-top:10px; margin-bottom:10px;">
                    <div class="stat-card"><h3 id="invoice-total-to-pay">₪ 0</h3><p data-i18n="total_to_pay">Total to Pay</p></div>
                    <div class="stat-card"><h3 id="invoice-total-discount">₪ 0</h3><p data-i18n="discount">Discount</p></div>
                    <div class="stat-card"><h3 id="invoice-total-paid">₪ 0</h3><p data-i18n="paid">Paid</p></div>
                    <div class="stat-card"><h3 id="invoice-total-left">₪ 0</h3><p data-i18n="left">Left</p></div>
                </div>
                <div class="table-container" style="margin-top:12px;">
                    <table>
                        <thead>
                            <tr>
                                <th data-i18n="date">Date</th>
                                <th data-i18n="treatment_procedure">Treatment Procedure</th>
                                <th data-i18n="price">Price</th>
                                <th data-i18n="discount">Discount</th>
                                <th data-i18n="payment">Payment</th>
                                <th data-i18n="balance">Balance</th>
                            </tr>
                        </thead>
                        <tbody id="patient-invoice-body"><tr><td colspan="6" data-i18n="no_data">No data</td></tr></tbody>
                    </table>
                </div>
                    </div>
                </div>
            </div>

            <div id="support" class="tab-content">
                <div class="page-header">
                    <h2 data-i18n="settings">Settings</h2>
                </div>
                <h3 style="margin-top:4px;" data-i18n="account">Account</h3>
                <div class="section-card" style="max-width:460px;margin-bottom:18px;">
                    <div class="form-group">
                        <label data-i18n="current_password">Current Password</label>
                        <input type="password" id="acct-current-password" autocomplete="current-password">
                    </div>
                    <div class="form-group">
                        <label data-i18n="new_password">New Password</label>
                        <input type="password" id="acct-new-password" autocomplete="new-password">
                    </div>
                    <div class="form-group">
                        <label data-i18n="confirm_password">Confirm New Password</label>
                        <input type="password" id="acct-confirm-password" autocomplete="new-password">
                    </div>
                    <button class="btn btn-primary" type="button" onclick="changeAccountPassword()" data-i18n="change_password">Change Password</button>
                </div>

                <h3 style="margin-top:18px;" data-en="Cloud Sync" data-ar="المزامنة السحابية">Cloud Sync</h3>
                <div class="section-card" style="max-width:560px;margin-bottom:18px;">
                    <p style="margin:0 0 12px;color:var(--muted);font-size:0.9em;line-height:1.6;"
                       data-en="Mirror this clinic's data to the cloud node so it stays reachable online and from mobile when off the local network. Staff keep using this local server — syncing runs in the background."
                       data-ar="انسخ بيانات هذه العيادة إلى الخادم السحابي لتبقى متاحة عبر الإنترنت ومن الهاتف خارج الشبكة المحلية. يستمر الموظفون باستخدام هذا الخادم المحلي — تتم المزامنة في الخلفية.">Mirror this clinic's data to the cloud node so it stays reachable online and from mobile when off the local network. Staff keep using this local server — syncing runs in the background.</p>
                    <div id="cloud-status-line" style="font-size:0.92em;line-height:1.7;margin-bottom:14px;color:var(--text,#1f2d2f);"></div>
                    <div id="cloud-pair-form" style="display:none;">
                        <div class="form-group">
                            <label data-en="Cloud server URL" data-ar="رابط الخادم السحابي">Cloud server URL</label>
                            <input type="text" id="cloud-url-input" placeholder="https://app.dentacare.tech">
                        </div>
                        <div class="form-group">
                            <label data-en="Serial number" data-ar="الرقم التسلسلي">Serial number</label>
                            <input type="text" id="cloud-serial-input" placeholder="XXXX-XXXX-XXXX-XXXX" autocomplete="off">
                        </div>
                        <button class="btn btn-primary" type="button" onclick="cloudPair(this)" data-en="Pair with cloud" data-ar="الربط بالسحابة">Pair with cloud</button>
                    </div>
                    <div id="cloud-paired-actions" style="display:none;">
                        <button class="btn btn-primary" type="button" onclick="cloudSyncNow(this)" data-en="Sync now" data-ar="مزامنة الآن">Sync now</button>
                        <button class="btn btn-secondary" type="button" onclick="cloudShowPairingQr()" data-en="Link a phone" data-ar="ربط هاتف">Link a phone</button>
                        <button class="btn btn-warning" type="button" onclick="cloudUnpair()" data-en="Unpair" data-ar="إلغاء الربط">Unpair</button>
                        <div id="cloud-pairing-qr" style="display:none;margin-top:14px;">
                            <p style="margin:0 0 10px;color:var(--muted);font-size:0.9em;line-height:1.6;"
                               data-en="Open the mobile app, then Settings, then Scan QR."
                               data-ar="افتح تطبيق الهاتف، ثم الإعدادات، ثم مسح رمز QR.">Open the mobile app, then Settings, then Scan QR.</p>
                            <img id="cloud-pairing-qr-img" alt="Pairing QR"
                                 style="width:220px;height:220px;background:#fff;padding:10px;border-radius:8px;border:1px solid var(--border,#d8e0e2);">
                        </div>
                    </div>
                </div>

                <h3 style="margin-top:18px;" data-en="Bluetooth sync" data-ar="مزامنة بلوتوث">Bluetooth sync</h3>
                <div class="section-card" id="bt-sync-card" style="max-width:560px;margin-bottom:18px;">
                    <p style="margin:0 0 12px;color:var(--muted);font-size:0.9em;line-height:1.6;"
                       data-en="When the phone can't reach Wi-Fi or the cloud, it syncs with this PC over Bluetooth. Pair your phone in Windows Bluetooth settings once, then flip the toggle."
                       data-ar="عندما لا يمكن للهاتف الوصول إلى الواي فاي أو السحابة، يقوم بالمزامنة مع هذا الحاسوب عبر البلوتوث. قم بإقران الهاتف في إعدادات بلوتوث ويندوز مرة واحدة، ثم قم بتفعيل المفتاح.">
                    </p>

                    <div class="bt-toggle-row">
                        <label>
                            <input type="checkbox" id="bt-enabled" onchange="bluetoothToggleEnabled(this.checked)"/>
                            <span data-en="Bluetooth sync" data-ar="مزامنة بلوتوث">Bluetooth sync</span>
                        </label>
                    </div>

                    <div id="bt-error-line"
                         style="display:none;margin-top:10px;color:var(--danger,#d9434e);font-size:0.9em;line-height:1.5;"
                         role="alert" aria-live="polite"></div>
                </div>

                <h3 style="margin-top:4px;" data-i18n="audit_log">Audit Log</h3>
                <div class="table-container" style="margin-top:12px;">
                    <table>
                        <thead>
                            <tr>
                                <th>ID</th>
                                <th data-i18n="date_time">Date and Time</th>
                                <th data-i18n="action">Action</th>
                                <th data-i18n="entity">Entity</th>
                                <th data-i18n="details">Details</th>
                            </tr>
                        </thead>
                        <tbody id="audit-logs-body"><tr><td colspan="5" data-i18n="no_data">No data</td></tr></tbody>
                    </table>
                </div>
                <div id="support-content"></div>
                <div style="margin-top:20px;">
                    <button class="btn btn-primary" onclick="loadSupportSection()" data-i18n="refresh_help">Refresh Help</button>
                </div>
            </div>
        </div>
        </div><!-- end app-body -->
    </div>

    <!-- Mobile nav overlay + hamburger -->
    <div class="nav-overlay" id="nav-overlay" onclick="closeMobileNav()"></div>
    <button class="nav-hamburger" id="nav-hamburger" onclick="toggleMobileNav()" aria-label="Open navigation">☰</button>

    <!-- Add Patient Modal -->
    <div id="add-patient-modal" class="modal" onclick="if(event.target===this)closeModal('add-patient-modal')">
        <div class="modal-content">
            <div class="modal-header">
                <span class="close-modal" onclick="closeModal('add-patient-modal')">&times;</span>
                <h2 data-i18n="add_new_patient">Add New Patient</h2>
            </div>
            <form id="add-patient-form">
                <div class="form-row">
                    <div class="form-group">
                        <label data-i18n="first_name_required">First Name *</label>
                        <input type="text" name="first_name" id="ap-first-name" required>
                    </div>
                    <div class="form-group">
                        <label data-i18n="last_name_required">Last Name *</label>
                        <input type="text" name="last_name" id="ap-last-name" required>
                    </div>
                </div>
                <div id="add-patient-dup-warning" style="display:none;background:#fff8e1;border:1px solid #f9a825;border-radius:6px;padding:10px 14px;font-size:0.88em;color:#5d4037;margin:6px 0 4px;line-height:1.6;"></div>
                <div class="form-row">
                    <div class="form-group">
                        <label data-i18n="date_of_birth">Date of Birth</label>
                        <input type="hidden" name="date_of_birth" id="add-patient-dob">
                        <div style="display:flex;gap:6px;">
                            <select id="add-patient-dob-day" style="flex:1;" onchange="syncDobHidden('add-patient-dob-day','add-patient-dob-month','add-patient-dob-year','add-patient-dob')">
                                <option value="">Day</option>
                            </select>
                            <select id="add-patient-dob-month" style="flex:2;" onchange="syncDobHidden('add-patient-dob-day','add-patient-dob-month','add-patient-dob-year','add-patient-dob')">
                                <option value="">Month</option>
                            </select>
                            <select id="add-patient-dob-year" style="flex:1.5;" onchange="syncDobHidden('add-patient-dob-day','add-patient-dob-month','add-patient-dob-year','add-patient-dob')">
                                <option value="">Year</option>
                            </select>
                        </div>
                    </div>
                    <div class="form-group">
                        <label data-i18n="phone">Phone</label>
                        <input type="tel" name="phone" id="ap-phone">
                    </div>
                </div>
                <div class="form-group">
                    <label data-i18n="email">Email</label>
                    <input type="email" name="email">
                </div>
                <div class="form-group">
                    <label data-i18n="address">Address</label>
                    <input type="text" name="address">
                </div>
                <div class="form-group">
                    <label data-i18n="medical_history">Medical History</label>
                    <textarea name="medical_history"></textarea>
                </div>
                <button type="submit" class="btn btn-primary" data-i18n="add_patient">Add Patient</button>
            </form>
        </div>
    </div>
    
    <!-- Add Appointment Modal -->
    <div id="add-appointment-modal" class="modal" onclick="if(event.target===this)closeModal('add-appointment-modal')">
        <div class="modal-content">
            <div class="modal-header">
                <span class="close-modal" onclick="closeModal('add-appointment-modal')">&times;</span>
                <h2 data-i18n="schedule_appointment">Schedule Appointment</h2>
            </div>
            <form id="add-appointment-form" novalidate>
                <div class="form-section">
                    <div class="form-row">
                        <div class="form-group">
                            <label data-i18n="patient_required">Patient <span class="required">*</span></label>
                            <select name="patient_id" id="appointment-patient-select" required>
                                <option value="" data-i18n="select_patient">Select Patient</option>
                            </select>
                            <div class="field-error" data-for="patient_id"></div>
                        </div>
                        <div class="form-group">
                            <label data-i18n="status">Status</label>
                            <select name="status" id="appointment-status-select">
                                <option value="scheduled" data-i18n="scheduled">Scheduled</option>
                                <option value="confirmed" data-i18n="confirmed">Confirmed</option>
                                <option value="cancelled" data-i18n="cancelled">Cancelled</option>
                                <option value="completed" data-i18n="completed">Completed</option>
                            </select>
                        </div>
                    </div>
                </div>

                <div class="form-section">
                    <div class="form-row">
                        <div class="form-group">
                            <label data-i18n="date_time_required">Date &amp; Time <span class="required">*</span></label>
                            <input type="datetime-local" name="appointment_date" id="appointment-date-input" required>
                            <div class="field-error" data-for="appointment_date"></div>
                        </div>
                        <div class="form-group">
                            <label data-i18n="duration_minutes">Duration (minutes)</label>
                            <input type="number" name="duration" id="appointment-duration-input" value="30" min="1" max="480">
                        </div>
                    </div>
                </div>

                <div class="form-section">
                    <div class="form-group">
                        <label data-i18n="treatment_type">Treatment / Procedure</label>
                        <select name="treatment_type" id="appointment-treatment-select">
                            <option value="">-- Select Treatment --</option>
                        </select>
                    </div>
                </div>

                <div class="form-section">
                    <div class="form-group">
                        <label data-i18n="notes">Notes</label>
                        <textarea name="notes" id="appointment-notes" rows="3"></textarea>
                    </div>
                </div>

                <div class="form-actions">
                    <button type="button" class="btn btn-secondary" id="add-appointment-clear" data-i18n="clear">Clear</button>
                    <button type="button" class="btn btn-warning" onclick="closeModal('add-appointment-modal')" data-i18n="cancel">Cancel</button>
                    <button type="submit" id="add-appointment-submit" class="btn btn-primary btn-large" data-i18n="schedule_appointment">Schedule Appointment</button>
                </div>
                <div id="add-appointment-toast" class="toast" aria-live="polite" role="status" style="display:none"></div>
            </form>
        </div>
    </div>
    
    <!-- Edit Patient Modal -->
    <div id="edit-patient-modal" class="modal" onclick="if(event.target===this)closeModal('edit-patient-modal')">
        <div class="modal-content">
            <div class="modal-header">
                <span class="close-modal" onclick="closeModal('edit-patient-modal')">&times;</span>
                <h2 data-i18n="edit_personal_data">Edit Personal Data</h2>
            </div>
            <form id="edit-patient-form">
                <input type="hidden" name="patient_id" id="edit-patient-id">
                <div class="form-row">
                    <div class="form-group"><label data-i18n="first_name">First Name</label><input type="text" name="first_name" id="edit-first-name"></div>
                    <div class="form-group"><label data-i18n="last_name">Last Name</label><input type="text" name="last_name" id="edit-last-name"></div>
                </div>
                <div class="form-row">
                    <div class="form-group"><label data-i18n="phone">Phone</label><input type="tel" name="phone" id="edit-phone"></div>
                    <div class="form-group">
                        <label><span data-i18n="date_of_birth">Date of Birth</span></label>
                        <input type="hidden" name="date_of_birth" id="edit-dob">
                        <div style="display:flex;gap:6px;">
                            <select id="edit-dob-day" style="flex:1;" onchange="syncDobHidden('edit-dob-day','edit-dob-month','edit-dob-year','edit-dob')">
                                <option value="">Day</option>
                            </select>
                            <select id="edit-dob-month" style="flex:2;" onchange="syncDobHidden('edit-dob-day','edit-dob-month','edit-dob-year','edit-dob')">
                                <option value="">Month</option>
                            </select>
                            <select id="edit-dob-year" style="flex:1.5;" onchange="syncDobHidden('edit-dob-day','edit-dob-month','edit-dob-year','edit-dob')">
                                <option value="">Year</option>
                            </select>
                        </div>
                    </div>
                </div>
                <div class="form-row">
                    <div class="form-group"><label data-i18n="gender">Gender</label><select name="gender" id="edit-gender"><option value="">--</option><option value="male" data-i18n="male">Male</option><option value="female" data-i18n="female">Female</option></select></div>
                    <div class="form-group"><label data-i18n="address">Address</label><input type="text" name="address" id="edit-address"></div>
                </div>
                <div class="form-group"><label data-i18n="notes">Notes</label><textarea name="notes" id="edit-notes"></textarea></div>
                <button type="submit" class="btn btn-primary" data-i18n="save">Save</button>
            </form>
        </div>
    </div>

    <!-- Edit Followup Modal -->
    <div id="edit-followup-modal" class="modal" onclick="if(event.target===this)closeEditFollowup()">
        <div class="modal-content">
            <div class="modal-header">
                <span class="close-modal" onclick="closeEditFollowup()">&times;</span>
                <h2 data-i18n="edit_entry">Edit Entry</h2>
            </div>
            <form id="edit-followup-form">
                <input type="hidden" id="ef-patient-id">
                <input type="hidden" id="ef-followup-id">
                <div class="form-row">
                    <div class="form-group">
                        <label data-i18n="date">Date</label>
                        <div class="date-input-wrap"><input type="text" id="ef-date" placeholder="DD/MM/YYYY" data-date-field="1" title="Enter date in DD/MM/YYYY format"><button type="button" class="date-picker-btn" title="Pick date" aria-label="Pick date">📅</button></div>
                    </div>
                    <div class="form-group">
                        <label data-i18n="procedure">Procedure</label>
                        <input type="text" id="ef-procedure">
                    </div>
                    <div class="form-group">
                        <label data-i18n="tooth_no">Tooth No.</label>
                        <input type="text" id="ef-tooth-no" maxlength="10" placeholder="e.g. 16" autocomplete="off">
                    </div>
                </div>
                <div class="form-row">
                    <div class="form-group">
                        <label data-i18n="price">Price <small style="font-weight:400;color:var(--muted);">(or expression e.g. 50+50)</small></label>
                        <input type="text" inputmode="decimal" id="ef-price" value="0" class="calc-input" data-calc-field="1" placeholder="0" autocomplete="off">
                    </div>
                    <div class="form-group">
                        <label data-i18n="discount">Discount <small style="font-weight:400;color:var(--muted);">(or expression, or % e.g. 20%)</small></label>
                        <input type="text" inputmode="decimal" id="ef-discount" value="0" class="calc-input" data-calc-field="1" data-percent-base="ef-price" placeholder="0" autocomplete="off">
                    </div>
                    <div class="form-group">
                        <label data-i18n="lab_expense">Lab Expense <small style="font-weight:400;color:var(--muted);">(or expression)</small></label>
                        <input type="text" inputmode="decimal" id="ef-lab-expense" value="0" class="calc-input" data-calc-field="1" placeholder="0" autocomplete="off">
                    </div>
                    <div class="form-group">
                        <label data-i18n="payment">Payment <small style="font-weight:400;color:var(--muted);">(or expression)</small></label>
                        <input type="text" inputmode="decimal" id="ef-payment" value="0" class="calc-input" data-calc-field="1" placeholder="0" autocomplete="off">
                    </div>
                </div>
                <div class="form-group">
                    <label data-i18n="notes">Notes</label>
                    <textarea id="ef-notes"></textarea>
                </div>
                <button type="submit" class="btn btn-primary" data-i18n="save">Save</button>
                <button type="button" class="btn btn-warning" onclick="closeEditFollowup()" data-i18n="cancel">Cancel</button>
            </form>
        </div>
    </div>

    <!-- Full Patient Profile Modal -->
    <div id="patient-profile-modal" class="modal" onclick="if(event.target===this)closeModal('patient-profile-modal')">
        <div class="modal-content" style="max-width: 1100px;">
            <div class="modal-header">
                <span class="close-modal" onclick="closeModal('patient-profile-modal')">&times;</span>
                <h2 data-i18n="patient_profile">Patient Profile</h2>
            </div>
            <div id="patient-profile-content"></div>
        </div>
    </div>

    <!-- Tooth Popup Modal -->
    <div id="tooth-popup" class="modal" style="display:none;" onclick="if(event.target===this)closeToothPopup()">
      <div class="modal-content" style="max-width:360px;">
        <h3 id="tooth-popup-title">—</h3>
        <div class="form-group">
          <label data-i18n="condition">Condition</label>
          <select id="tooth-popup-condition"></select>
        </div>
        <div class="form-group">
          <label data-i18n="notes">Note</label>
          <input type="text" id="tooth-popup-note" autocomplete="off">
        </div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:8px;">
          <button class="btn btn-primary" id="tooth-popup-save" data-i18n="save">Save</button>
          <button class="btn" id="tooth-popup-log" data-i18n="log_treatment">+ Log treatment</button>
          <button class="btn" id="tooth-popup-plan" data-i18n="add_to_plan">+ Add to plan</button>
          <button class="btn btn-ghost" id="tooth-popup-close" data-i18n="cancel">Cancel</button>
        </div>
      </div>
    </div>

    <script>
        let patientsCache = [];
        let appointmentsCache = [];
        let holidaysCache = [];
        let treatmentProceduresCache = [];
        let billingCache = [];
        let currentPatientInvoicePayload = null;
        let currentProfilePatient = null;
        let currentFollowupBalance = 0;
        let patientProfileCache = {};
        let followupsCache = {};
        let currentCalendarDate = new Date();
        let currentLanguage = localStorage.getItem('clinic-language') || 'en';
        let currentTheme = localStorage.getItem('clinic-theme') || 'light';
        let currentReportsSubTab = localStorage.getItem('reports-subtab') || 'weekly';
        let currentFinancialSubTab = localStorage.getItem('financial-subtab') || 'management';
        let currentCatalogSubTab = localStorage.getItem('catalog-subtab') || 'procedure';
        let currentAdministrationFocus = 'all';

        // Language translations map
        const translations = {
            en: {
                title: '{{ SYSTEM_NAME }}',
                subtitle: '{{ CLINIC_TAGLINE }}',
                doctor_name: '{{ DOCTOR_NAME }}',
                language_toggle: 'English/العربية',
                dashboard_overview: 'Dashboard Overview',
                total_patients: 'Total Patients',
                todays_appointments: "Today's Appointments",
                appointments: 'Appointments',
                recent_appointments: 'Recent Appointments',
                patient: 'Patient',
                patient_required: 'Patient *',
                date_time: 'Date and Time',
                date_time_required: 'Date and Time *',
                duration: 'Duration',
                duration_minutes: 'Duration (minutes)',
                treatment_type: 'Treatment Type',
                treatment_checkup: 'Checkup',
                treatment_cleaning: 'Cleaning',
                treatment_filling: 'Filling',
                treatment_root_canal: 'Root Canal',
                treatment_extraction: 'Extraction',
                treatment_whitening: 'Whitening',
                treatment_crown: 'Crown',
                treatment_braces: 'Braces',
                status: 'Status',
                patient_management: 'Patient Management',
                add_new_patient: 'Add New Patient',
                add_patient: 'Add Patient',
                first_name: 'First Name',
                first_name_required: 'First Name *',
                last_name: 'Last Name',
                last_name_required: 'Last Name *',
                date_of_birth: 'Date of Birth',
                phone: 'Phone',
                phone_required: 'Phone *',
                email: 'Email',
                address: 'Address',
                gender: 'Gender',
                male: 'Male',
                female: 'Female',
                medical_history: 'Medical History',
                search_by_name_phone_email: 'Search by name, phone, or email',
                search_placeholder: 'Type patient name, phone, or email',
                open_patient_by_name: 'Open Patient by Name',
                clear: 'Clear',
                showing_all_patients: 'Showing all patients.',
                showing_n_patients: 'Showing {count} patient(s).',
                name: 'Name',
                actions: 'Actions',
                download_backup: 'Download Backup',
                logout: 'Logout',
                account: 'Account',
                current_password: 'Current Password',
                new_password: 'New Password',
                confirm_password: 'Confirm New Password',
                change_password: 'Change Password',
                fill_all_fields: 'Please fill in all fields.',
                password_too_short: 'New password must be at least 4 characters.',
                passwords_do_not_match: 'New passwords do not match.',
                password_changed: 'Password changed successfully.',
                schedule_appointment: 'Schedule Appointment',
                schedule: 'Schedule',
                select_patient: 'Select Patient',
                search_patient: '🔍 Search patients by name or phone…',
                no_patient_matches: 'No patient matches your search',
                available: 'available',
                no_credit: 'no credit',
                appointment_date_required: 'Appointment Date *',
                appointment_time_required: 'Appointment Time *',
                previous_month: 'Previous Month',
                current_month: 'Current Month',
                next_month: 'Next Month',
                refresh: 'Refresh',
                holiday_management: 'Holiday Management',
                holiday_date: 'Holiday Date *',
                holiday_name: 'Holiday Name *',
                add_holiday: 'Add Holiday',
                date: 'Date',
                holiday: 'Holiday',
                no_holidays_yet: 'No holidays yet',
                optional_note: 'Optional note',
                reporting_system: 'Reporting System',
                financial_management: 'Financial Management',
                weekly_tab: 'Weekly',
                monthly_tab: 'Monthly',
                lab_tab: 'Lab',
                weekly_reports: 'Weekly',
                monthly_reports: 'Monthly',
                lab_reports: 'Lab',
                management_tab: 'Management',
                billing_tab: 'Billing',
                invoices_tab: 'Invoices',
                payments_tab: '💳 Payments',
                statement_tab: '📄 Statement',
                record_payment: 'Record Payment',
                payment_management: 'Payment Record',
                payment_history: 'Payment History',
                payment_history_meta: 'Every payment recorded for this patient — from the follow-up sheet and from payment records.',
                source: 'Source',
                amount_paid: 'Amount Paid',
                show_all_records: 'Show all records',
                from_followup: 'Follow-up sheet',
                from_payment_record: 'Payment record',
                total_collected: 'Total Collected',
                no_payments_recorded: 'No payments recorded for this patient yet.',
                patient_statement: 'Patient Statement',
                list_tab: '📋 List',
                calendar_tab: '📆 Calendar',
                catalog: 'Catalog',
                catalog_summary: "Manage the clinic's procedure catalog from one place.",
                appointments_summary: 'Track upcoming, confirmed, and completed visits.',
                month: 'Month',
                run_monthly_report: 'Run Monthly Report',
                run_lab_report: 'Run Lab Report',
                print_invoice: 'Print Invoice',
                print_language: 'Print Language',
                print_language_current: 'Current App Language',
                print_language_arabic: 'Arabic',
                print_language_english: 'English',
                invoice_preview_unavailable: 'No invoice data to print yet.',
                description: 'Description',
                start_date: 'Start Date',
                end_date: 'End Date',
                run_report: 'Run Report',
                this_week: 'This Week',
                weekly_range_not_selected: 'Weekly range not selected.',
                night_mode: 'Night Mode',
                day_mode: 'Day Mode',
                visits: 'Visits',
                revenue: 'Revenue',
                expenses: 'Expenses',
                lab_expenses: 'Lab Expenses',
                clinic_gross_profit: 'Clinic Gross Profit',
                profit: 'Profit',
                scheduling: 'Scheduling',
                financial: 'Financial',
                management: 'Management',
                procedure_catalog: 'Procedure Catalog',
                treatment_catalog: 'Treatment Catalog',
                arabic_name: 'Arabic Name',
                english_name: 'English Name',
                procedure_name: 'Procedure',
                procedure_name_required: 'Procedure Name *',
                default_price: 'Default Price',
                default_lab_expense: 'Default Lab Expense',
                active: 'Active',
                inactive: 'Inactive',
                enable: 'Enable',
                disable: 'Disable',
                save_procedure: 'Save Procedure',
                save_treatment: 'Save Treatment',
                edit_procedure: 'Edit',
                procedure_saved: 'Procedure saved successfully.',
                unable_save_procedure: 'Unable to save procedure.',
                treatment_catalog_admin_summary: 'Manage treatment names and pricing from one place.',
                no_treatment_catalog_yet: 'No treatment catalog items yet',
                treatment_catalog_empty_hint: 'Add a treatment item to make the admin catalog ready for booking and billing flows.',
                treatment_saved: 'Treatment saved successfully.',
                unable_save_treatment: 'Unable to save treatment.',
                arabic_name_required: 'Arabic Name *',
                arabic_name_is_required: 'Arabic name is required.',
                loading: 'Loading...',
                treatments_overview_note: 'Use Administration to edit the procedure catalog and treatment catalog. This tab provides a shorter path to those tools.',
                receivables_tracking: 'Receivables Tracking',
                total_receivables: 'Total Receivables',
                patients_with_balance: 'Patients Owing Money',
                last_date: 'Last Date',
                overdue_days: 'Overdue Days',
                billing_management: 'Billing Management',
                subtotal_required: 'Subtotal *',
                discount: 'Discount',
                paid_amount: 'Paid Amount',
                payment_method: 'Payment Method',
                cash: 'Cash',
                card: 'Card',
                transfer: 'Transfer',
                todays_revenue: "Today's Revenue",
                todays_visits: "Today's Visits",
                unpaid_by_patients: 'Unpaid by Patients',
                outstanding_balances: 'Amounts Still Owed (current)',
                create_invoice: 'Create Invoice',
                invoice_no: 'Invoice #',
                balance_due: 'Amount to Pay',
                patient_total_invoice: 'Patient Total Invoice',
                generate_total_invoice: 'Generate Total Invoice',
                audit_log: 'Audit Log',
                calendar: 'Calendar',
                treatments: 'Treatments',
                settings: 'Settings',
                quick_access: 'Quick Access',
                procedure_catalog_items: 'Procedure Catalog Items',
                treatment_catalog_items: 'Treatment Catalog Items',
                open_administration: 'Open Administration',
                open_procedure_catalog: 'Open Procedure Catalog',
                open_treatment_catalog: 'Open Treatment Catalog',
                refresh_treatment_data: 'Refresh Treatment Data',
                action: 'Action',
                entity: 'Entity',
                details: 'Details',
                unable_add_billing: 'Unable to create invoice.',
                no_receivables: 'No receivables found.',
                expense_tracking: 'Expense Tracking',
                period: 'Period:',
                all: 'All',
                today: 'Today',
                this_month: 'This Month',
                all_status: 'All Status',
                paid: 'Paid',
                postponed: 'Postponed',
                showing_all_expenses: 'Showing all expenses.',
                category_required: 'Category *',
                amount_required: 'Amount (ILS) *',
                date_required: 'Date *',
                status_required: 'Status *',
                category: 'Category',
                amount: 'Amount',
                vendor: 'Vendor',
                add_expense: 'Add Expense',
                no_expenses_yet: 'No expenses yet',
                technical_support: 'Technical Support',
                refresh_help: 'Refresh Help',
                patient_profile: 'Patient Profile',
                cancel: 'Cancel',
                other: 'Other',
                no_data: 'No data',
                yes: 'Yes',
                no: 'No',
                range: 'Range',
                full_period: 'full period',
                weekly_range_text: 'Weekly range: {start} to {end}',
                showing_expenses_count: 'Showing {count} expense(s).',
                no_expenses_found: 'No expenses found',
                no_appointments: 'No appointments',
                holiday_label: 'Holiday',
                no_holidays_for_day: 'No holidays',
                no_appointments_for_day: 'No appointments',
                visit_label: 'Visit',
                delete: 'Delete',
                edit: 'Edit',
                delete_expense_confirm: 'Delete this expense?',
                delete_holiday_confirm: 'Delete this holiday?',
                confirm_delete_patient: 'Are you sure you want to delete this patient?',
                select_patient_first: 'Please type a patient name first.',
                no_patient_match: 'No patient matched your search.',
                patient_not_found: 'Patient not found',
                saved_successfully: 'Saved successfully.',
                no_phone: 'No phone',
                view: 'View',
                book: 'Book',
                min: 'min',
                followups: 'Follow-ups',
                current_balance: 'Amount to Pay',
                total_to_pay: 'Total to pay',
                left: 'Still to Pay',
                book_for_patient: 'Book Appointment for This Patient',
                open_calendar: 'Open Calendar',
                patient_name: 'Patient Name',
                followup_sheet: 'Patient Follow-up Sheet',
                treatment_procedure: 'Treatment Procedure',
                select_procedure: 'Select Procedure',
                custom_procedure_name: 'Custom Procedure Name',
                custom_procedure_placeholder: 'Type procedure name',
                requires_lab: 'Requires Lab',
                price: 'Price',
                tooth_no: 'Tooth No.',
                lab_expense: 'Lab Expense',
                clinic_profit: 'Clinic Profit',
                payment: 'Payment',
                balance: 'Amount to Pay',
                add_entry: 'Add Entry',
                procedure_required: 'Please select a procedure or enter a custom procedure name.',
                medical_images: 'Medical Images',
                image_notes: 'Image notes',
                upload_image: 'Upload Image',
                file: 'File',
                uploaded: 'Uploaded',
                no_entries_yet: 'No entries yet',
                unable_save_followup: 'Unable to save follow-up.',
                unable_schedule_appointment: 'Unable to schedule appointment.',
                unable_add_expense: 'Unable to add expense.',
                unable_add_holiday: 'Unable to add holiday.',
                unable_start_visit: 'Unable to start visit.',
                visit_started: 'Visit started from appointment successfully.',
                unknown: 'Unknown',
                confirm_delete: 'Are you sure you want to delete?',
                no_entry_found: 'Entry not found',
                save_failed: 'Save failed',
                age: 'Age',
                age_unknown: 'Age not recorded',
                edit_personal_data: 'Edit Personal Data',
                edit_entry: 'Edit Entry',
                save: 'Save',
                credit_balance: 'Patient Credit Balance',
                edit_notes: 'Edit Notes',
                this_week: 'This Week',
                session_count: 'Sessions',
                patient_count: 'Patients',
                new_entries: 'New Entries',
                followups_count: 'Follow-ups',
                overview: 'Overview',
                patient_info: 'Patient Information',
                total_visits: 'Total Visits',
                total_revenue: 'Total Revenue',
                navigation: 'Navigation',
                notes: 'Notes',
                scheduled: 'Scheduled',
                confirmed: 'Confirmed',
                cancelled: 'Cancelled',
                completed: 'Completed',
                edit_doctor_name: 'Edit Doctor Name',
                dup_name_warning: '⚠️ A patient with this name already exists:',
                dup_phone_warning: '⚠️ This phone number is registered to:',
                dup_proceed: 'You can still add the patient.',
                dashboard_summary: 'Snapshot of current activity, totals, and recent appointments.',
                recent_appointments_hint: 'Latest scheduled visits and their current status.',
                patient_management_summary: 'Search, open, and manage patient records from one place.',
                patients_list: 'Patients',
                patients_list_hint: 'Patient details, quick access, and row actions.',
                finance: 'Finance',
                calendar_summary: 'Move between months, inspect day cards, and manage holidays.',
                appointments_list: 'Appointments',
                appointments_list_hint: 'Sorted appointment list with status badges and duration.',
                financial_summary: 'Review receivables, expenses, billing, and invoice summaries.',
                procedure: 'Procedure',
                appointment_saved: 'Appointment saved',
                loading_dashboard: 'Loading dashboard...',
                loading_dashboard_hint: 'Refreshing totals and recent appointments.',
                dashboard_load_failed: 'Unable to load dashboard',
                dashboard_load_failed_hint: 'Check the connection and try again.',
                loading_patients: 'Loading patients...',
                loading_patients_hint: 'Fetching the patient list.',
                patients_load_failed: 'Unable to load patients',
                patients_load_failed_hint: 'Refresh the page or try again in a moment.',
                no_patients_found: 'No patients found',
                no_patients_found_hint: 'Add a patient or adjust your search to see matching records.',
                loading_appointments: 'Loading appointments...',
                loading_appointments_hint: 'Refreshing the appointment list and calendar.',
                no_appointments_yet: 'No appointments yet',
                no_appointments_yet_hint: 'Create the first appointment to populate the schedule table and calendar.',
                appointments_load_failed: 'Unable to load appointments',
                appointments_load_failed_hint: 'Try refreshing the tab or the page.',
                no_recent_appointments: 'No recent appointments yet',
                no_recent_appointments_hint: 'Schedule the first appointment to populate this area.',
                no_procedures_yet: 'No procedures yet',
                procedure_catalog_empty_hint: 'Add a procedure to build the clinic catalog and populate related forms.',
                procedures: 'Procedures',
                select_treatment: '-- Select Treatment --',
                no_treatments_available: 'No treatments available — add them in the Catalog tab',
                no_invoices_yet: 'No invoices yet',
                billing_empty_hint: 'Create a billing record to start tracking invoice history and balances.',
                receivables_empty_hint: 'Once invoices are created, the outstanding balance will appear here.',
                expenses_empty_hint: 'Adjust the filters or add the first expense entry.',
                or_expression: 'or expression',
                or_percent: 'or % e.g. 20%',
                unknown_patient: 'Unknown patient',
                odontogram: 'Tooth chart',
                tooth: 'Tooth',
                condition: 'Condition',
                tooth_conditions: 'Tooth conditions',
                healthy: 'Healthy',
                has_plan: 'Has plan',
                unpaid: 'Unpaid',
                log_treatment: '+ Log treatment',
                add_to_plan: '+ Add to plan',
                deactivate: 'Deactivate',
                name_ar: 'Arabic name',
                plan_pick_hint: 'Enter a number, or a new plan name:',
                plan_new_name: 'New plan name:',
                plan: 'Plan'
            },
            ar: {
                title: '{{ SYSTEM_NAME }}',
                subtitle: 'إدارة شاملة للمرضى والمواعيد',
                doctor_name: '{{ DOCTOR_NAME_AR }}',
                language_toggle: 'العربية/English',
                dashboard_overview: 'نظرة عامة على لوحة التحكم',
                total_patients: 'إجمالي المرضى',
                todays_appointments: 'مواعيد اليوم',
                appointments: 'المواعيد',
                recent_appointments: 'أحدث المواعيد',
                patient: 'المريض',
                patient_required: 'المريض *',
                date_time: 'التاريخ والوقت',
                date_time_required: 'التاريخ والوقت *',
                duration: 'المدة',
                duration_minutes: 'المدة (بالدقائق)',
                treatment_type: 'نوع العلاج',
                treatment_checkup: 'فحص',
                treatment_cleaning: 'تنظيف',
                treatment_filling: 'حشو',
                treatment_root_canal: 'علاج عصب',
                treatment_extraction: 'خلع',
                treatment_whitening: 'تبييض',
                treatment_crown: 'تلبيسة',
                treatment_braces: 'تقويم',
                status: 'الحالة',
                patient_management: 'إدارة المرضى',
                add_new_patient: 'إضافة مريض جديد',
                add_patient: 'إضافة المريض',
                first_name: 'الاسم الأول',
                first_name_required: 'الاسم الأول *',
                last_name: 'اسم العائلة',
                last_name_required: 'اسم العائلة *',
                date_of_birth: 'تاريخ الميلاد',
                phone: 'رقم الهاتف',
                phone_required: 'رقم الهاتف *',
                email: 'البريد الإلكتروني',
                address: 'العنوان',
                gender: 'الجنس',
                male: 'ذكر',
                female: 'أنثى',
                medical_history: 'التاريخ الطبي',
                search_by_name_phone_email: 'ابحث بالاسم أو الهاتف أو البريد الإلكتروني',
                search_placeholder: 'اكتب اسم المريض أو الهاتف أو البريد الإلكتروني',
                open_patient_by_name: 'فتح المريض حسب الاسم',
                clear: 'مسح',
                showing_all_patients: 'عرض جميع المرضى.',
                showing_n_patients: 'يتم عرض {count} مريض/مرضى.',
                name: 'الاسم',
                actions: 'الإجراءات',
                download_backup: 'تنزيل نسخة احتياطية',
                logout: 'تسجيل الخروج',
                account: 'الحساب',
                current_password: 'كلمة المرور الحالية',
                new_password: 'كلمة المرور الجديدة',
                confirm_password: 'تأكيد كلمة المرور الجديدة',
                change_password: 'تغيير كلمة المرور',
                fill_all_fields: 'يرجى تعبئة جميع الحقول.',
                password_too_short: 'يجب أن تتكون كلمة المرور الجديدة من 4 أحرف على الأقل.',
                passwords_do_not_match: 'كلمتا المرور غير متطابقتين.',
                password_changed: 'تم تغيير كلمة المرور بنجاح.',
                schedule_appointment: 'جدولة موعد',
                schedule: 'حفظ الموعد',
                select_patient: 'اختر المريض',
                search_patient: '🔍 ابحث عن مريض بالاسم أو الهاتف…',
                no_patient_matches: 'لا يوجد مريض مطابق لبحثك',
                available: 'متاح',
                no_credit: 'لا يوجد رصيد',
                appointment_date_required: 'تاريخ الموعد *',
                appointment_time_required: 'وقت الموعد *',
                previous_month: 'الشهر السابق',
                current_month: 'الشهر الحالي',
                next_month: 'الشهر التالي',
                refresh: 'تحديث',
                holiday_management: 'إدارة العطلات',
                holiday_date: 'تاريخ العطلة *',
                holiday_name: 'اسم العطلة *',
                add_holiday: 'إضافة عطلة',
                date: 'التاريخ',
                holiday: 'العطلة',
                no_holidays_yet: 'لا توجد عطلات بعد',
                optional_note: 'ملاحظة اختيارية',
                reporting_system: 'نظام التقارير',
                financial_management: 'الإدارة المالية',
                weekly_tab: 'أسبوعي',
                monthly_tab: 'شهري',
                lab_tab: 'المعمل',
                weekly_reports: 'أسبوعي',
                monthly_reports: 'شهري',
                lab_reports: 'المعمل',
                management_tab: 'الإدارة',
                billing_tab: 'الفواتير',
                invoices_tab: 'ملخص الفواتير',
                payments_tab: '💳 المدفوعات',
                statement_tab: '📄 كشف الحساب',
                record_payment: 'تسجيل دفعة',
                payment_management: 'تسجيل دفعة',
                payment_history: 'سجل المدفوعات',
                payment_history_meta: 'كل دفعة مسجلة لهذا المريض — من ورقة المتابعة ومن سجلات الدفعات.',
                source: 'المصدر',
                amount_paid: 'المبلغ المدفوع',
                show_all_records: 'عرض كل السجلات',
                from_followup: 'ورقة المتابعة',
                from_payment_record: 'سجل دفعة',
                total_collected: 'إجمالي المحصّل',
                no_payments_recorded: 'لا توجد مدفوعات مسجلة لهذا المريض بعد.',
                patient_statement: 'كشف حساب المريض',
                list_tab: '📋 القائمة',
                calendar_tab: '📆 التقويم',
                catalog: 'الفهرس',
                catalog_summary: 'إدارة كتالوج إجراءات العيادة من مكان واحد.',
                appointments_summary: 'تتبع المواعيد القادمة والمؤكدة والمكتملة.',
                month: 'الشهر',
                run_monthly_report: 'تشغيل التقرير الشهري',
                run_lab_report: 'تشغيل تقرير المعمل',
                print_invoice: 'طباعة فاتورة',
                print_language: 'لغة الطباعة',
                print_language_current: 'نفس لغة التطبيق',
                print_language_arabic: 'العربية',
                print_language_english: 'الإنجليزية',
                invoice_preview_unavailable: 'لا توجد بيانات فاتورة للطباعة بعد.',
                description: 'الوصف',
                start_date: 'تاريخ البداية',
                end_date: 'تاريخ النهاية',
                run_report: 'تشغيل التقرير',
                this_week: 'هذا الأسبوع',
                weekly_range_not_selected: 'لم يتم اختيار نطاق الأسبوع بعد.',
                night_mode: 'الوضع الليلي',
                day_mode: 'الوضع النهاري',
                visits: 'الزيارات',
                revenue: 'الإيرادات',
                expenses: 'المصروفات',
                lab_expenses: 'مصاريف المعمل',
                clinic_gross_profit: 'ربح العيادة الإجمالي',
                profit: 'صافي الربح',
                scheduling: 'الجدولة',
                financial: 'المالية',
                management: 'الإدارة',
                procedure_catalog: 'كتالوج الإجراءات',
                treatment_catalog: 'كتالوج العلاجات',
                arabic_name: 'الاسم بالعربية',
                english_name: 'الاسم بالإنجليزية',
                procedure_name: 'الإجراء',
                procedure_name_required: 'اسم الإجراء *',
                default_price: 'السعر الافتراضي',
                default_lab_expense: 'تكلفة المعمل الافتراضية',
                active: 'مفعّل',
                inactive: 'غير مفعّل',
                enable: 'تفعيل',
                disable: 'تعطيل',
                save_procedure: 'حفظ الإجراء',
                save_treatment: 'حفظ العلاج',
                edit_procedure: 'تعديل',
                procedure_saved: 'تم حفظ الإجراء بنجاح.',
                unable_save_procedure: 'تعذر حفظ الإجراء.',
                treatment_catalog_admin_summary: 'إدارة أسماء العلاجات والأسعار من مكان واحد.',
                no_treatment_catalog_yet: 'لا توجد عناصر في كتالوج العلاجات بعد',
                treatment_catalog_empty_hint: 'أضف علاجًا ليصبح كتالوج الإدارة جاهزًا للحجز والفوترة.',
                treatment_saved: 'تم حفظ العلاج بنجاح.',
                unable_save_treatment: 'تعذر حفظ العلاج.',
                arabic_name_required: 'الاسم بالعربية *',
                arabic_name_is_required: 'اسم العلاج بالعربية مطلوب.',
                loading: 'جار التحميل...',
                treatments_overview_note: 'استخدم الإدارة لتعديل كتالوج الإجراءات وكتالوج العلاجات. توفر هذه الصفحة طريقًا أقصر إلى تلك الأدوات.',
                receivables_tracking: 'متابعة الذمم',
                total_receivables: 'إجمالي الذمم',
                patients_with_balance: 'مرضى عليهم مبلغ',
                last_date: 'آخر تاريخ',
                overdue_days: 'أيام التأخير',
                billing_management: 'إدارة الفواتير',
                subtotal_required: 'الإجمالي قبل الخصم *',
                discount: 'الخصم',
                paid_amount: 'المبلغ المدفوع',
                payment_method: 'طريقة الدفع',
                cash: 'نقداً',
                card: 'بطاقة',
                transfer: 'تحويل',
                todays_revenue: 'إيرادات اليوم',
                todays_visits: 'زيارات اليوم',
                unpaid_by_patients: 'مستحق على المرضى',
                outstanding_balances: 'مبالغ ما زالت مستحقة (حالياً)',
                create_invoice: 'إنشاء فاتورة',
                invoice_no: 'رقم الفاتورة',
                balance_due: 'المبلغ المطلوب',
                patient_total_invoice: 'فاتورة كلية للمريض',
                generate_total_invoice: 'توليد الفاتورة الكلية',
                audit_log: 'سجل التعديلات',
                calendar: 'التقويم',
                treatments: 'العلاجات',
                settings: 'الإعدادات',
                quick_access: 'وصول سريع',
                procedure_catalog_items: 'عناصر كتالوج الإجراءات',
                treatment_catalog_items: 'عناصر كتالوج العلاجات',
                open_administration: 'فتح الإدارة',
                open_procedure_catalog: 'فتح كتالوج الإجراءات',
                open_treatment_catalog: 'فتح كتالوج العلاجات',
                refresh_treatment_data: 'تحديث بيانات العلاجات',
                action: 'الإجراء',
                entity: 'الكيان',
                details: 'التفاصيل',
                unable_add_billing: 'تعذر إنشاء الفاتورة.',
                no_receivables: 'لا توجد ذمم حالياً.',
                expense_tracking: 'متابعة المصروفات',
                period: 'الفترة:',
                all: 'الكل',
                today: 'اليوم',
                this_month: 'هذا الشهر',
                all_status: 'كل الحالات',
                paid: 'مدفوع',
                postponed: 'مؤجل',
                showing_all_expenses: 'عرض جميع المصروفات.',
                category_required: 'التصنيف *',
                amount_required: 'المبلغ (شيكل) *',
                date_required: 'التاريخ *',
                status_required: 'الحالة *',
                category: 'التصنيف',
                amount: 'المبلغ',
                vendor: 'المورّد',
                add_expense: 'إضافة مصروف',
                no_expenses_yet: 'لا توجد مصروفات بعد',
                technical_support: 'الدعم الفني',
                refresh_help: 'تحديث المساعدة',
                patient_profile: 'ملف المريض',
                cancel: 'إلغاء',
                other: 'أخرى',
                no_data: 'لا توجد بيانات',
                yes: 'نعم',
                no: 'لا',
                range: 'النطاق',
                full_period: 'كامل الفترة',
                weekly_range_text: 'نطاق الأسبوع: من {start} إلى {end}',
                showing_expenses_count: 'يتم عرض {count} مصروف/مصروفات.',
                no_expenses_found: 'لا توجد مصروفات',
                no_appointments: 'لا توجد مواعيد',
                holiday_label: 'عطلة',
                no_holidays_for_day: 'لا توجد عطلات',
                no_appointments_for_day: 'لا توجد مواعيد',
                visit_label: 'زيارة',
                delete: 'حذف',
                edit: 'تعديل',
                delete_expense_confirm: 'هل تريد حذف هذا المصروف؟',
                delete_holiday_confirm: 'هل تريد حذف هذه العطلة؟',
                confirm_delete_patient: 'هل أنت متأكد من حذف هذا المريض؟',
                select_patient_first: 'يرجى كتابة اسم المريض أولا.',
                no_patient_match: 'لم يتم العثور على مريض مطابق للبحث.',
                patient_not_found: 'المريض غير موجود',
                saved_successfully: 'تم الحفظ بنجاح.',
                no_phone: 'لا يوجد رقم هاتف',
                view: 'عرض',
                book: 'حجز',
                min: 'دقيقة',
                followups: 'المتابعات',
                current_balance: 'المبلغ المطلوب',
                total_to_pay: 'الإجمالي المطلوب',
                left: 'ما زال مطلوباً',
                book_for_patient: 'حجز موعد لهذا المريض',
                open_calendar: 'فتح التقويم',
                patient_name: 'اسم المريض',
                followup_sheet: 'نموذج متابعة المريض',
                treatment_procedure: 'الإجراء العلاجي',
                select_procedure: 'اختر الإجراء',
                custom_procedure_name: 'اسم إجراء مخصص',
                custom_procedure_placeholder: 'اكتب اسم الإجراء',
                requires_lab: 'يتطلب معمل',
                price: 'السعر',
                tooth_no: 'رقم السن',
                lab_expense: 'مصروف المعمل',
                clinic_profit: 'ربح العيادة',
                payment: 'الدفعة',
                balance: 'المبلغ المطلوب',
                add_entry: 'إضافة سجل',
                procedure_required: 'يرجى اختيار إجراء أو إدخال اسم إجراء مخصص.',
                medical_images: 'الصور الطبية',
                image_notes: 'ملاحظات الصورة',
                upload_image: 'رفع الصورة',
                file: 'الملف',
                uploaded: 'تاريخ الرفع',
                no_entries_yet: 'لا توجد سجلات بعد',
                unable_save_followup: 'تعذر حفظ المتابعة.',
                unable_schedule_appointment: 'تعذر جدولة الموعد.',
                unable_add_expense: 'تعذر إضافة المصروف.',
                unable_add_holiday: 'تعذر إضافة العطلة.',
                unable_start_visit: 'تعذر بدء الزيارة.',
                visit_started: 'تم بدء الزيارة من الموعد بنجاح.',
                unknown: 'غير معروف',
                confirm_delete: 'هل أنت متأكد من الحذف؟',
                no_entry_found: 'لم يتم العثور على القيد',
                save_failed: 'فشل الحفظ',
                age: 'العمر',
                age_unknown: 'العمر غير مسجل',
                edit_personal_data: 'تعديل البيانات الشخصية',
                edit_entry: 'تعديل القيد',
                save: 'حفظ',
                credit_balance: 'رصيد المريض لدى العيادة',
                edit_notes: 'تعديل الملاحظات',
                session_count: 'الجلسات',
                patient_count: 'المرضى',
                new_entries: 'علاجات جديدة',
                followups_count: 'مراجعات',
                overview: 'نظرة عامة',
                patient_info: 'بيانات المريض',
                total_visits: 'إجمالي الزيارات',
                total_revenue: 'إجمالي الإيرادات',
                navigation: 'التنقل',
                notes: 'الملاحظات',
                scheduled: 'مجدول',
                confirmed: 'مؤكد',
                cancelled: 'ملغي',
                completed: 'مكتمل',
                edit_doctor_name: 'تعديل اسم الطبيب',
                dup_name_warning: '⚠️ يوجد مريض بهذا الاسم بالفعل:',
                dup_phone_warning: '⚠️ رقم الهاتف مسجل بالفعل لـ:',
                dup_proceed: 'يمكنك المتابعة وإضافة المريض.',
                dashboard_summary: 'لمحة سريعة عن نشاط اليوم والإجماليات والمواعيد الأخيرة.',
                recent_appointments_hint: 'آخر الزيارات المجدولة وحالتها الحالية.',
                patient_management_summary: 'بحث وفتح وإدارة سجلات المرضى من مكان واحد.',
                patients_list: 'المرضى',
                patients_list_hint: 'تفاصيل المرضى والوصول السريع وإجراءات الصف.',
                finance: 'المالية',
                calendar_summary: 'التنقل بين الأشهر وفحص بطاقات الأيام وإدارة الإجازات.',
                appointments_list: 'المواعيد',
                appointments_list_hint: 'قائمة المواعيد مرتبة مع شارات الحالة والمدة.',
                financial_summary: 'مراجعة المستحقات والمصاريف والفواتير وملخصات الحسابات.',
                procedure: 'الإجراء',
                appointment_saved: 'تم حفظ الموعد',
                loading_dashboard: 'جارٍ تحميل لوحة التحكم...',
                loading_dashboard_hint: 'تحديث الإجماليات والمواعيد الأخيرة.',
                dashboard_load_failed: 'تعذر تحميل لوحة التحكم',
                dashboard_load_failed_hint: 'تحقق من الاتصال وحاول مرة أخرى.',
                loading_patients: 'جارٍ تحميل المرضى...',
                loading_patients_hint: 'جارٍ جلب قائمة المرضى.',
                patients_load_failed: 'تعذر تحميل المرضى',
                patients_load_failed_hint: 'أعد تحميل الصفحة أو حاول مرة أخرى.',
                no_patients_found: 'لم يُعثر على مرضى',
                no_patients_found_hint: 'أضف مريضاً أو عدّل بحثك لعرض النتائج المطابقة.',
                loading_appointments: 'جارٍ تحميل المواعيد...',
                loading_appointments_hint: 'تحديث قائمة المواعيد والتقويم.',
                no_appointments_yet: 'لا توجد مواعيد بعد',
                no_appointments_yet_hint: 'أنشئ أول موعد لملء جدول المواعيد والتقويم.',
                appointments_load_failed: 'تعذر تحميل المواعيد',
                appointments_load_failed_hint: 'جرّب تحديث التبويب أو الصفحة.',
                no_recent_appointments: 'لا توجد مواعيد حديثة بعد',
                no_recent_appointments_hint: 'جدوِل أول موعد لملء هذه المنطقة.',
                no_procedures_yet: 'لا توجد إجراءات بعد',
                procedure_catalog_empty_hint: 'أضف إجراءً لبناء كتالوج العيادة وملء النماذج المرتبطة.',
                procedures: 'الإجراءات',
                select_treatment: '-- اختر العلاج --',
                no_treatments_available: 'لا تتوفر علاجات — أضفها من تبويب الكتالوج',
                no_invoices_yet: 'لا توجد فواتير بعد',
                billing_empty_hint: 'أنشئ سجل فواتير لبدء تتبع تاريخ الفواتير والأرصدة.',
                receivables_empty_hint: 'بمجرد إنشاء الفواتير، سيظهر الرصيد المستحق هنا.',
                expenses_empty_hint: 'عدّل الفلاتر أو أضف أول إدخال مصاريف.',
                or_expression: 'أو تعبير',
                or_percent: 'أو نسبة مثل ٪20',
                unknown_patient: 'مريض غير معروف',
                odontogram: 'مخطط الأسنان',
                tooth: 'سن',
                condition: 'الحالة',
                tooth_conditions: 'حالات الأسنان',
                healthy: 'سليم',
                has_plan: 'ضمن خطة',
                unpaid: 'غير مدفوع',
                log_treatment: '+ تسجيل علاج',
                add_to_plan: '+ إضافة إلى خطة',
                deactivate: 'إلغاء التفعيل',
                name_ar: 'الاسم بالعربية',
                plan_pick_hint: 'أدخل رقمًا، أو اسم خطة جديدة:',
                plan_new_name: 'اسم الخطة الجديدة:',
                plan: 'خطة'
            }
        };

        function t(key, fallback = '') {
            const value = translations[currentLanguage]?.[key];
            return typeof value === 'string' ? value : fallback;
        }

        function tForLang(lang, key, fallback = '') {
            const selectedLang = lang === 'ar' ? 'ar' : 'en';
            const value = translations[selectedLang]?.[key];
            return typeof value === 'string' ? value : fallback;
        }

        function getInvoicePrintLanguage() {
            const selected = document.getElementById('invoice-print-language')?.value || 'current';
            if (selected === 'ar' || selected === 'en') {
                return selected;
            }
            return currentLanguage === 'ar' ? 'ar' : 'en';
        }

        function getDoctorNameForLanguage(lang) {
            return tForLang(lang, 'doctor_name', translations.en.doctor_name || 'Dr. Wasfy Barzaq');
        }

        function applyTheme() {
            document.body.setAttribute('data-theme', currentTheme);
            const themeToggle = document.getElementById('theme-toggle');
            if (themeToggle) {
                const isDark = currentTheme === 'dark';
                const label = isDark ? t('day_mode', 'Day Mode') : t('night_mode', 'Night Mode');
                themeToggle.textContent = isDark ? '☀️' : '🌙';
                themeToggle.title = label;
                themeToggle.setAttribute('aria-label', label);
            }
        }

        function toggleTheme() {
            currentTheme = currentTheme === 'dark' ? 'light' : 'dark';
            localStorage.setItem('clinic-theme', currentTheme);
            applyTheme();
        }

        function toggleLanguage() {
            currentLanguage = currentLanguage === 'en' ? 'ar' : 'en';
            localStorage.setItem('clinic-language', currentLanguage);
            applyLanguage();
        }

        // ── Doctor name edit ──────────────────────────────────
        async function loadDoctorName() {
            try {
                const d = await fetch('/api/clinic-settings').then(r => r.json());
                if (d.doctor_name)    translations.en.doctor_name = d.doctor_name;
                if (d.doctor_name_ar) translations.ar.doctor_name = d.doctor_name_ar;
                const el = document.getElementById('doctor-name-display');
                if (el) el.textContent = translations[currentLanguage]?.doctor_name || d.doctor_name || '';
                const inp = document.getElementById('doctor-name-en-input');
                const inpAr = document.getElementById('doctor-name-ar-input');
                if (inp)   inp.value   = d.doctor_name    || '';
                if (inpAr) inpAr.value = d.doctor_name_ar || '';
            } catch(_) {}
        }

        function toggleDoctorEditPopover(e) {
            if (e) e.stopPropagation();
            const pop   = document.getElementById('doctor-edit-popover');
            const badge = document.getElementById('doctor-badge-el');
            if (!pop) return;
            const isOpen = pop.classList.contains('open');
            if (isOpen) { pop.classList.remove('open'); return; }
            const rect = badge.getBoundingClientRect();
            const popW = 280;
            let left = rect.right - popW;
            if (left < 8) left = 8;
            pop.style.top  = (rect.bottom + 8) + 'px';
            pop.style.left = left + 'px';
            pop.style.right = 'auto';
            pop.classList.add('open');
        }

        async function saveDoctorName() {
            const nameEn = (document.getElementById('doctor-name-en-input')?.value || '').trim();
            const nameAr = (document.getElementById('doctor-name-ar-input')?.value || '').trim();
            if (!nameEn && !nameAr) return;
            try {
                const resp = await fetch('/api/clinic-settings', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({doctor_name: nameEn, doctor_name_ar: nameAr})
                });
                if (!resp.ok) { alert(t('save_failed','Save failed')); return; }
                if (nameEn) translations.en.doctor_name = nameEn;
                if (nameAr) translations.ar.doctor_name = nameAr;
                const el = document.getElementById('doctor-name-display');
                if (el) el.textContent = translations[currentLanguage]?.doctor_name || nameEn;
                document.getElementById('doctor-edit-popover')?.classList.remove('open');
            } catch(_) { alert(t('save_failed','Save failed')); }
        }

        document.addEventListener('click', (e) => {
            const badge = document.getElementById('doctor-badge-el');
            const pop   = document.getElementById('doctor-edit-popover');
            if (pop && pop.classList.contains('open') &&
                !pop.contains(e.target) && (!badge || !badge.contains(e.target))) {
                pop.classList.remove('open');
            }
        });

        function applyLanguage() {
            const html = document.documentElement;
            html.lang = currentLanguage;
            html.dir = currentLanguage === 'ar' ? 'rtl' : 'ltr';

            document.querySelectorAll('[data-en][data-ar]').forEach(el => {
                el.textContent = currentLanguage === 'ar'
                    ? el.getAttribute('data-ar')
                    : el.getAttribute('data-en');
            });

            document.querySelectorAll('[data-i18n]').forEach(el => {
                const key = el.getAttribute('data-i18n');
                const text = t(key);
                if (typeof text === 'string') {
                    el.textContent = text;
                }
            });

            document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
                const key = el.getAttribute('data-i18n-placeholder');
                const text = t(key);
                if (typeof text === 'string') {
                    el.placeholder = text;
                }
            });

            const langBtn = document.getElementById('language-toggle');
            if (langBtn) langBtn.textContent = currentLanguage === 'ar' ? 'EN' : 'AR';

            const activeTab = document.querySelector('.tab-content.active')?.id;
            if (activeTab === 'dashboard') loadDashboard();
            else if (activeTab === 'patients') filterPatientsTable();
            else if (activeTab === 'appointments') loadAppointments();
            else if (activeTab === 'calendar') loadAppointments();
            else if (activeTab === 'treatments') loadTreatmentsSection();
            else if (activeTab === 'reports') loadReportsSection();
            else if (activeTab === 'financial') loadFinancialSection();
            else if (activeTab === 'support') loadSupportSection();

            applyTheme();
        }

        function setNavSubtabActive(containerSelector, targetTabName = '', clickedBtn = null) {
            const container = document.querySelector(containerSelector);
            if (!container) return;

            container.querySelectorAll('.nav-subtab').forEach(btn => btn.classList.remove('active'));
            if (clickedBtn) {
                clickedBtn.classList.add('active');
                return;
            }
            if (!targetTabName) return;

            const fallback = Array.from(container.querySelectorAll('.nav-subtab')).find(btn =>
                btn.getAttribute('onclick')?.includes(`'${targetTabName}'`)
            );
            if (fallback) fallback.classList.add('active');
        }

        function openCalendarView(clickedBtn = null) {
            // Calendar is now a sub-tab inside Appointments
            const appointmentsBtn = document.querySelector('.nav-tab[data-tab="appointments"]');
            switchTab('appointments', appointmentsBtn);
            // Activate the calendar sub-tab after the appointments tab loads
            
        }

        // Initialize language and doctor name on page load
        applyLanguage();
        loadDoctorName();

        function toDatetimeLocalValue(dateObj) {
            const pad = (n) => String(n).padStart(2, '0');
            return `${dateObj.getFullYear()}-${pad(dateObj.getMonth() + 1)}-${pad(dateObj.getDate())}T${pad(dateObj.getHours())}:${pad(dateObj.getMinutes())}`;
        }

        function isFridayDateTimeValue(value) {
            if (!value) return false;
            const normalized = String(value).trim().replace(' ', 'T');
            const parsed = new Date(normalized);
            return !Number.isNaN(parsed.getTime()) && parsed.getDay() === 5;
        }

        function monthLabel(dateObj) {
            const locale = currentLanguage === 'ar' ? 'ar-EG' : 'en-US';
            return dateObj.toLocaleString(locale, { month: 'long', year: 'numeric' });
        }

        function escapeHtml(value) {
            if (value === null || value === undefined) return '';
            return String(value)
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#39;');
        }

        function parseCurrency(value) {
            const str = String(value || '').trim();
            const direct = parseFloat(str);
            if (Number.isFinite(direct) && !/[+\\-*/]/.test(str.replace(/^[-]/, ''))) return direct;
            // Try arithmetic expression (only reached when evalArithmeticExpr is available)
            if (typeof evalArithmeticExpr === 'function') {
                const evaled = evalArithmeticExpr(str);
                if (evaled !== null) return evaled;
            }
            return Number.isFinite(direct) ? direct : 0;
        }

        async function loadTreatmentProcedures() {
            const response = await fetch('/api/treatment-procedures');
            treatmentProceduresCache = await response.json();
            if (!Array.isArray(treatmentProceduresCache)) {
                treatmentProceduresCache = [];
            }
        }

        function getProcedureById(idValue) {
            const id = parseInt(idValue, 10);
            if (!Number.isFinite(id)) return null;
            return treatmentProceduresCache.find(item => item.id === id) || null;
        }

        function updateFollowupProcedureUi() {
            const select = document.getElementById('followup-procedure-id');
            const customWrap = document.getElementById('followup-custom-procedure-wrap');
            const customInput = document.getElementById('followup-custom-procedure');
            const labExpenseInput = document.getElementById('followup-lab-expense');
            const requiresLabField = document.getElementById('followup-requires-lab');
            if (!select || !customWrap || !customInput || !labExpenseInput || !requiresLabField) return;

            const procedure = getProcedureById(select.value);
            const isCustom = String(select.value) === '';
            const requiresLab = Boolean(procedure && parseInt(procedure.requires_lab, 10) === 1);

            customWrap.style.display = isCustom ? 'block' : 'none';
            customInput.required = isCustom;

            labExpenseInput.disabled = !requiresLab;
            if (!requiresLab) {
                labExpenseInput.value = '0';
            } else if (parseCurrency(labExpenseInput.value) === 0 && procedure) {
                labExpenseInput.value = parseCurrency(procedure.default_lab_expense).toFixed(2);
            }

            requiresLabField.value = requiresLab ? '1' : '0';
        }

        function resetProcedureForm() {
            const idInput = document.getElementById('procedure-id');
            const nameInput = document.getElementById('procedure-name');
            const priceInput = document.getElementById('procedure-default-price');
            const labInput = document.getElementById('procedure-default-lab-expense');
            const requiresLabInput = document.getElementById('procedure-requires-lab');
            const activeInput = document.getElementById('procedure-active');
            const saveBtn = document.getElementById('procedure-save-btn');
            if (!idInput || !nameInput || !priceInput || !labInput || !requiresLabInput || !activeInput || !saveBtn) return;

            idInput.value = '';
            nameInput.value = '';
            priceInput.value = '0';
            labInput.value = '0';
            requiresLabInput.checked = false;
            activeInput.checked = true;
            saveBtn.textContent = t('save_procedure', 'Save Procedure');
        }

        function startEditProcedure(id) {
            const procedure = getProcedureById(id);
            if (!procedure) return;
            const idInput = document.getElementById('procedure-id');
            const nameInput = document.getElementById('procedure-name');
            const priceInput = document.getElementById('procedure-default-price');
            const labInput = document.getElementById('procedure-default-lab-expense');
            const requiresLabInput = document.getElementById('procedure-requires-lab');
            const activeInput = document.getElementById('procedure-active');
            const saveBtn = document.getElementById('procedure-save-btn');
            if (!idInput || !nameInput || !priceInput || !labInput || !requiresLabInput || !activeInput || !saveBtn) return;

            idInput.value = String(procedure.id);
            nameInput.value = procedure.name || '';
            priceInput.value = parseCurrency(procedure.default_price || 0).toFixed(2);
            labInput.value = parseCurrency(procedure.default_lab_expense || 0).toFixed(2);
            requiresLabInput.checked = parseInt(procedure.requires_lab, 10) === 1;
            activeInput.checked = parseInt(procedure.active, 10) === 1;
            saveBtn.textContent = t('edit_procedure', 'Edit');
        }

        function renderProcedureCatalogTable() {
            const tbody = document.getElementById('procedures-body');
            if (!tbody) return;

            if (!treatmentProceduresCache.length) {
                tbody.innerHTML = renderStateRow(t('no_data', 'No data'), {
                    icon: '🦷',
                    title: t('no_procedures_yet', 'No procedures yet'),
                    text: t('procedure_catalog_empty_hint', 'Add a procedure to build the clinic catalog and populate related forms.'),
                    colSpan: 6,
                    buttonHtml: `<button class="btn btn-primary" type="button" onclick="document.getElementById('procedure-name')?.focus()">${t('save_procedure', 'Save Procedure')}</button>`
                });
                return;
            }

            tbody.innerHTML = treatmentProceduresCache.map(item => {
                const requiresLabText = parseInt(item.requires_lab, 10) === 1 ? t('yes', 'Yes') : t('no', 'No');
                const activeText = parseInt(item.active, 10) === 1 ? t('yes', 'Yes') : t('no', 'No');
                return `
                    <tr>
                        <td>${item.name || ''}</td>
                        <td class="center-cell"><span class="badge ${parseInt(item.requires_lab, 10) === 1 ? 'badge-pending' : 'badge-muted'}">${requiresLabText}</span></td>
                        <td class="numeric-cell">₪ ${parseCurrency(item.default_price).toFixed(2)}</td>
                        <td class="numeric-cell">₪ ${parseCurrency(item.default_lab_expense).toFixed(2)}</td>
                        <td class="center-cell"><span class="badge ${parseInt(item.active, 10) === 1 ? 'badge-active' : 'badge-blocked'}">${activeText}</span></td>
                        <td><button class="btn btn-primary" type="button" onclick="startEditProcedure(${item.id})">${t('edit_procedure', 'Edit')}</button></td>
                    </tr>
                `;
            }).join('');
        }

        async function loadProcedureCatalog() {
            const response = await fetch('/api/treatment-procedures?include_inactive=1').catch(() => null);
            if (!response || !response.ok) { treatmentProceduresCache = []; }
            else {
                treatmentProceduresCache = await response.json().catch(() => []);
                if (!Array.isArray(treatmentProceduresCache)) treatmentProceduresCache = [];
            }
            const section = document.getElementById('procedures-body');
            if (section) {
                renderProcedureCatalogTable();
            }
            updateTreatmentOverviewCounts();
        }

        function updateTreatmentOverviewCounts() {
            const procedureCountEl = document.getElementById('treatments-procedure-count');
            if (procedureCountEl) procedureCountEl.textContent = String(treatmentProceduresCache.length || 0);
        }

        async function loadTreatmentsSection() {
            await loadProcedureCatalog();
            updateTreatmentOverviewCounts();
            // Wire date picker buttons inside the catalog section
            attachDatePickerButtons(document.getElementById('treatments'));
            // Load tooth conditions admin
            renderToothConditionsTable();
        }

        // ── Tooth Conditions Admin ────────────────────────────────────────────────
        async function renderToothConditionsTable() {
          const wrap = document.getElementById('tooth-conditions-table');
          if (!wrap) return;
          const rows = await (await fetch('/api/tooth-conditions?all=1')).json();
          wrap.innerHTML = `<table><thead><tr>
              <th>${t('color','Color')}</th><th>${t('name','Name')}</th><th>${t('name_ar','Arabic')}</th>
              <th>#</th><th></th></tr></thead><tbody>` +
            rows.map(c => `<tr style="${c.active ? '' : 'opacity:.5;'}">
              <td><i style="display:inline-block;width:16px;height:16px;border-radius:3px;background:${c.color};border:1px solid #334155;"></i></td>
              <td>${escapeHtml(c.name)}</td><td>${escapeHtml(c.name_ar || '')}</td><td>${c.sort_order}</td>
              <td>${c.active ? `<button class="btn btn-ghost" onclick="deleteToothCondition(${c.id})">${t('deactivate','Deactivate')}</button>` : ''}</td>
            </tr>`).join('') + '</tbody></table>';
        }

        async function addToothCondition() {
          const name = document.getElementById('tc-name').value.trim();
          if (!name) return;
          await fetch('/api/tooth-conditions', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
              name, name_ar: document.getElementById('tc-name-ar').value.trim() || null,
              color: document.getElementById('tc-color').value,
              sort_order: parseInt(document.getElementById('tc-sort').value, 10) || 0,
            }),
          });
          document.getElementById('tc-name').value = '';
          document.getElementById('tc-name-ar').value = '';
          renderToothConditionsTable();
        }

        async function deleteToothCondition(id) {
          await fetch(`/api/tooth-conditions/${id}`, { method: 'DELETE' });
          renderToothConditionsTable();
        }

        document.getElementById('tc-add')?.addEventListener('click', addToothCondition);

        // openAdministrationHome / openAdministrationCatalog now route to the Catalog tab
        function openAdministrationHome(clickedBtn = null) {
            const catalogBtn = document.querySelector('.nav-tab[data-tab="treatments"]');
            switchTab('treatments', clickedBtn || catalogBtn);
        }

        function openAdministrationCatalog(targetPanel, clickedBtn = null) {
            const catalogBtn = document.querySelector('.nav-tab[data-tab="treatments"]');
            switchTab('treatments', catalogBtn);
        }

        // ── Main tab switching ────────────────────────────────────────────────────
        function switchTab(tabName, clickedBtn = null) {
            const tabs = document.querySelectorAll('.tab-content');
            const navTabs = document.querySelectorAll('.nav-tab');

            tabs.forEach(tab => tab.classList.remove('active'));
            navTabs.forEach(navTab => navTab.classList.remove('active'));

            const tabEl = document.getElementById(tabName);
            if (!tabEl) { console.warn('switchTab: no element with id', tabName); return; }
            tabEl.classList.add('active');

            if (clickedBtn) {
                clickedBtn.classList.add('active');
            } else {
                const match = document.querySelector(`.nav-tab[data-tab="${tabName}"]`)
                    || Array.from(navTabs).find(btn => btn.getAttribute('onclick')?.includes(`'${tabName}'`));
                if (match) match.classList.add('active');
            }

            // Load data for the active tab
            if (tabName === 'dashboard')     loadDashboard();
            else if (tabName === 'patients')     loadPatients();
            else if (tabName === 'appointments') { loadAppointments(); }
            else if (tabName === 'treatments')   loadTreatmentsSection();
            else if (tabName === 'reports')      loadReportsSection();
            else if (tabName === 'financial')    loadFinancialSection();
            else if (tabName === 'support')      loadSupportSection();
        }

        function switchReportsSubTab(tabName, clickedBtn = null, shouldLoad = true) {
            const container = document.getElementById('reports');
            if (!container) return;

            currentReportsSubTab = tabName;
            localStorage.setItem('reports-subtab', tabName);

            container.querySelectorAll('#reports-sub-tabs .sub-tab').forEach(btn => btn.classList.remove('active'));
            container.querySelectorAll('.sub-tab-content[id^="reports-subtab-"]').forEach(panel => panel.classList.remove('active'));

            if (clickedBtn) {
                clickedBtn.classList.add('active');
            } else {
                const fallbackBtn = container.querySelector(`#reports-sub-tabs .sub-tab[onclick*="'${tabName}'"]`);
                if (fallbackBtn) fallbackBtn.classList.add('active');
            }

            const activePanel = document.getElementById(`reports-subtab-${tabName}`);
            if (activePanel) activePanel.classList.add('active');

            if (!shouldLoad) return;
            if (tabName === 'weekly') loadWeeklyReport();
            else if (tabName === 'monthly') loadMonthlyReport();
            else if (tabName === 'lab') loadLabReport();
        }

        function switchFinancialSubTab(tabName, clickedBtn = null, shouldLoad = true) {
            const container = document.getElementById('financial');
            if (!container) return;

            currentFinancialSubTab = tabName;
            localStorage.setItem('financial-subtab', tabName);

            container.querySelectorAll('#financial-sub-tabs .sub-tab').forEach(btn => btn.classList.remove('active'));
            container.querySelectorAll('.sub-tab-content[id^="financial-subtab-"]').forEach(panel => panel.classList.remove('active'));

            if (clickedBtn) {
                clickedBtn.classList.add('active');
            } else {
                const fallbackBtn = container.querySelector(`#financial-sub-tabs .sub-tab[onclick*="'${tabName}'"]`);
                if (fallbackBtn) fallbackBtn.classList.add('active');
            }

            const activePanel = document.getElementById(`financial-subtab-${tabName}`);
            if (activePanel) activePanel.classList.add('active');

            if (!shouldLoad) return;
            if (tabName === 'management') {
                loadReceivables();
                loadExpenses();
            } else if (tabName === 'billing') {
                loadBilling();
            } else if (tabName === 'invoices') {
                loadPatientsSelect('invoice-patient-select');
            }
        }

        function handleProcedureCatalogToggle(detailsElement) {
            if (detailsElement && detailsElement.open) {
                loadProcedureCatalog();
            }
        }

        async function loadAdministrationSection() {
            // Administration tab is removed — redirect to Catalog tab
            switchTab('treatments', document.querySelector('.nav-tab[data-tab="treatments"]'));
        }

        // ── Sidebar / Mobile Nav ──────────────────────────────────────────────
        function toggleMobileNav() {
            const nav = document.getElementById('main-nav');
            const overlay = document.getElementById('nav-overlay');
            if (!nav) return;
            const isOpen = nav.classList.contains('mobile-open');
            if (isOpen) { closeMobileNav(); } else {
                nav.classList.add('mobile-open');
                overlay.classList.add('active');
                document.getElementById('nav-hamburger').textContent = '✕';
            }
        }
        function closeMobileNav() {
            const nav = document.getElementById('main-nav');
            const overlay = document.getElementById('nav-overlay');
            if (nav) nav.classList.remove('mobile-open');
            if (overlay) overlay.classList.remove('active');
            const btn = document.getElementById('nav-hamburger');
            if (btn) btn.textContent = '☰';
        }

        // Close mobile nav when a tab is selected on mobile
        (function patchMobileNavClose() {
            document.addEventListener('DOMContentLoaded', function() {
                document.querySelectorAll('.nav-tab, .nav-subtab').forEach(function(el) {
                    el.addEventListener('click', function() {
                        if (window.innerWidth <= 760) { setTimeout(closeMobileNav, 80); }
                    });
                });
            });
        })();

        // Desktop: click "Navigation" label to collapse/expand sidebar
        document.addEventListener('DOMContentLoaded', function() {
            const navLabel = document.querySelector('.nav-tabs-label');
            if (navLabel) {
                navLabel.style.cursor = 'pointer';
                navLabel.title = 'Toggle navigation';
                navLabel.addEventListener('click', () => {
                    if (window.innerWidth > 760) {
                        document.body.classList.toggle('sidebar-collapsed');
                    }
                });
            }
            // Auto-collapse sidebar on mid-size screens (not mobile, not full desktop)
            function updateSidebarOnResize() {
                if (window.innerWidth > 760 && window.innerWidth <= 980) {
                    document.body.classList.add('sidebar-collapsed');
                } else if (window.innerWidth > 980) {
                    document.body.classList.remove('sidebar-collapsed');
                }
                // On mobile, ensure slide-in nav is closed when resizing back up
                if (window.innerWidth > 760) { closeMobileNav(); }
            }
            updateSidebarOnResize();
            window.addEventListener('resize', updateSidebarOnResize);
        });

        // Modal functions
        
        function initDobDropdowns(dayId, monthId, yearId) {
            const dayEl = document.getElementById(dayId);
            const monthEl = document.getElementById(monthId);
            const yearEl = document.getElementById(yearId);
            if (!dayEl || !monthEl || !yearEl) return;
            if (dayEl.options.length > 1) return; // already populated

            for (let d = 1; d <= 31; d++) {
                const v = String(d).padStart(2, '0');
                dayEl.add(new Option(v, v));
            }
            const monthNames = ['January','February','March','April','May','June',
                                'July','August','September','October','November','December'];
            monthNames.forEach((name, i) => {
                const v = String(i + 1).padStart(2, '0');
                monthEl.add(new Option(name, v));
            });
            const currentYear = new Date().getFullYear();
            for (let y = currentYear; y >= currentYear - 110; y--) {
                yearEl.add(new Option(String(y), String(y)));
            }
        }

        function syncDobHidden(dayId, monthId, yearId, hiddenId) {
            const day   = document.getElementById(dayId)?.value   || '';
            const month = document.getElementById(monthId)?.value || '';
            const year  = document.getElementById(yearId)?.value  || '';
            const hidden = document.getElementById(hiddenId);
            if (hidden) hidden.value = (day && month && year) ? `${year}-${month}-${day}` : '';
        }

        function showCalendarPickerModal(onDateSelect) {
            if (!document.getElementById('date-picker-modal')) {
                const modal = document.createElement('div');
                modal.id = 'date-picker-modal';
                modal.className = 'date-picker-modal';
                modal.innerHTML = `
                    <div class="date-picker-modal-content">
                        <div class="date-picker-modal-header">
                            <button type="button" onclick="changePickerMonth(-1)">❮</button>
                            <div class="date-picker-modal-month" id="picker-month-label"></div>
                            <button type="button" onclick="changePickerMonth(1)">❯</button>
                        </div>
                        <div id="picker-calendar-grid" class="date-picker-grid"></div>
                        <div style="display: flex; gap: 8px; margin-top: 16px;">
                            <button class="btn btn-warning" type="button" onclick="closePickerModal()">${t('cancel','Cancel')}</button>
                            <button class="btn btn-primary" type="button" onclick="selectTodayInPicker()">${t('today','Today')}</button>
                        </div>
                    </div>
                </div>
                `;
                document.body.appendChild(modal);
                modal.addEventListener('click', (e) => {
                    if (e.target === modal) closePickerModal();
                });
            }
            window.datePickerCallback = onDateSelect;
            window.pickerDate = new Date();
            renderPickerCalendar();
            document.getElementById('date-picker-modal').classList.add('active');
        }

        function renderPickerCalendar() {
            const year = window.pickerDate.getFullYear();
            const month = window.pickerDate.getMonth();
            const firstDay = new Date(year, month, 1);
            const startDay = firstDay.getDay();
            const daysInMonth = new Date(year, month + 1, 0).getDate();
            const monthLabelEl = document.getElementById('picker-month-label');
            const today = new Date();
            const locale = currentLanguage === 'ar' ? 'ar-EG' : 'en-US';
            const monthStr = window.pickerDate.toLocaleDateString(locale, { month: 'long', year: 'numeric' });
            monthLabelEl.textContent = monthStr;
            const dayNames = currentLanguage === 'ar'
                ? ['الأحد', 'الإثنين', 'الثلاثاء', 'الأربعاء', 'الخميس', 'الجمعة', 'السبت']
                : ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
            const gridEl = document.getElementById('picker-calendar-grid');
            gridEl.innerHTML = dayNames.map(d => `<div class="date-picker-day-name">${d}</div>`).join('') +
                Array.from({length: startDay}, () => '<div class="date-picker-day empty"></div>').join('') +
                Array.from({length: daysInMonth}, (_, i) => {
                    const day = i + 1;
                    const dateStr = `${String(day).padStart(2, '0')}/${String(month + 1).padStart(2, '0')}/${year}`;
                    const isToday = today.getFullYear() === year && today.getMonth() === month && today.getDate() === day;
                    const todayClass = isToday ? 'today' : '';
                    return `<div class="date-picker-day ${todayClass}" onclick="selectPickerDate('${dateStr}')">${day}</div>`;
                }).join('');
        }

        function changePickerMonth(offset) {
            if (!window.pickerDate) window.pickerDate = new Date();
            window.pickerDate = new Date(window.pickerDate.getFullYear(), window.pickerDate.getMonth() + offset, 1);
            renderPickerCalendar();
        }

        function selectPickerDate(dateStr) {
            if (window.datePickerCallback) {
                window.datePickerCallback(dateStr);
            }
            closePickerModal();
        }

        function selectTodayInPicker() {
            const today = new Date();
            const day = String(today.getDate()).padStart(2, '0');
            const month = String(today.getMonth() + 1).padStart(2, '0');
            const year = today.getFullYear();
            selectPickerDate(`${day}/${month}/${year}`);
        }

        function closePickerModal() {
            const modal = document.getElementById('date-picker-modal');
            if (modal) modal.classList.remove('active');
        }

        function showAddPatientModal() {
            initDobDropdowns('add-patient-dob-day', 'add-patient-dob-month', 'add-patient-dob-year');
            const modal = document.getElementById('add-patient-modal');
            modal.classList.add('active');
        }
        
        async function showAddAppointmentModal(patientId = null, preferredDate = null) {
            const form = document.getElementById('add-appointment-form');
            if (form) {
                form.reset();
                form.querySelectorAll('.field-error').forEach(el => el.textContent = '');
            }
            const toast = document.getElementById('add-appointment-toast');
            if (toast) { toast.style.display = 'none'; toast.className = 'toast'; }

            await loadPatientsSelect('appointment-patient-select');
            if (patientId) {
                const patientSelect = document.getElementById('appointment-patient-select');
                if (patientSelect) {
                    patientSelect.value = String(patientId);
                    patientSelect.dispatchEvent(new Event('change', { bubbles: true }));
                }
            }

            const dateInput = document.getElementById('appointment-date-input');
            if (dateInput) {
                let targetDate;
                if (preferredDate) {
                    targetDate = new Date(String(preferredDate).replace(' ', 'T'));
                    if (Number.isNaN(targetDate.getTime())) targetDate = new Date(Date.now() + 3600000);
                } else {
                    targetDate = new Date(Date.now() + 3600000);
                }
                if (targetDate.getDay() === 5) targetDate.setDate(targetDate.getDate() + 1);
                dateInput.value = toDatetimeLocalValue(targetDate);
            }

            const statusSel = document.getElementById('appointment-status-select');
            if (statusSel) statusSel.value = 'scheduled';

            const durInput = document.getElementById('appointment-duration-input');
            if (durInput) durInput.value = '30';

            await populateAppointmentTreatmentSelect();

            document.getElementById('add-appointment-modal').classList.add('active');
        }

        async function populateAppointmentTreatmentSelect() {
            const sel = document.getElementById('appointment-treatment-select');
            if (!sel) return;

            if (!Array.isArray(treatmentProceduresCache) || !treatmentProceduresCache.length) {
                const r = await fetch('/api/treatment-procedures').catch(() => null);
                if (r && r.ok) {
                    const data = await r.json().catch(() => []);
                    treatmentProceduresCache = Array.isArray(data) ? data : [];
                }
            }

            const opts = [`<option value="">${t('select_treatment', '-- Select Treatment --')}</option>`];

            if (Array.isArray(treatmentProceduresCache) && treatmentProceduresCache.length) {
                treatmentProceduresCache.forEach(p => {
                    const n = String(p.name || '').trim();
                    if (n) opts.push(`<option value="${n}">${n}</option>`);
                });
            }

            if (opts.length === 1) {
                opts.push(`<option value="" disabled>${t('no_treatments_available', 'No treatments available — add them in the Catalog tab')}</option>`);
            }

            sel.innerHTML = opts.join('');
        }

        function closeModal(modalId) {
            document.getElementById(modalId).classList.remove('active');
        }

        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape') {
                document.querySelectorAll('.modal.active').forEach(m => m.classList.remove('active'));
            }
        });

        // Load patients into select dropdown
        async function loadPatientsSelect(selectId) {
            const response = await fetch('/api/patients');
            const patients = await response.json();
            const select = document.getElementById(selectId);
            if (!select) return;
            const optsHtml = [`<option value="">${t('select_patient', 'Select Patient')}</option>`];
            (Array.isArray(patients) ? patients : []).forEach(patient => {
                const name = `${patient.first_name || ''} ${patient.last_name || ''}`.trim();
                const phone = String(patient.phone || '').trim();
                optsHtml.push(`<option value="${patient.id}" data-phone="${phone.replace(/"/g, '')}">${name}${phone ? ' — ' + phone : ''}</option>`);
            });
            select.innerHTML = optsHtml.join('');
            attachPatientSearch(select);
            if (select._comboSync) select._comboSync();
        }

        // Turn a patient <select> into a single searchable combobox: one field
        // that filters as you type and shows matches in a slide-down list. The
        // native <select> stays in the DOM (visually hidden) as the value holder,
        // so form submission, .value reads, and change events keep working.
        function attachPatientSearch(select) {
            if (!select || select.dataset.comboAttached || !select.parentNode) return;
            select.dataset.comboAttached = '1';

            const wrap = document.createElement('div');
            wrap.className = 'patient-combo';
            select.parentNode.insertBefore(wrap, select);
            wrap.appendChild(select);
            select.classList.add('patient-combo-native');
            select.tabIndex = -1;
            select.setAttribute('aria-hidden', 'true');

            const input = document.createElement('input');
            input.type = 'text';
            input.className = 'patient-combo-input';
            input.placeholder = t('search_patient', 'Search patients…');
            input.setAttribute('autocomplete', 'off');
            input.setAttribute('role', 'combobox');
            input.setAttribute('aria-autocomplete', 'list');
            input.setAttribute('aria-expanded', 'false');
            input.setAttribute('aria-label', t('patient', 'Patient'));

            const menu = document.createElement('div');
            menu.className = 'patient-combo-menu';
            menu.setAttribute('role', 'listbox');
            menu.hidden = true;

            wrap.appendChild(input);
            wrap.appendChild(menu);

            let activeIndex = -1;

            function matchesFor(query) {
                const q = String(query || '').trim().toLowerCase();
                return Array.from(select.options).filter(opt => {
                    if (!opt.value) return false;
                    if (!q) return true;
                    const hay = (opt.textContent + ' ' + (opt.dataset.phone || '')).toLowerCase();
                    return hay.includes(q);
                });
            }

            function openMenu() { menu.hidden = false; input.setAttribute('aria-expanded', 'true'); }
            function closeMenu() { menu.hidden = true; input.setAttribute('aria-expanded', 'false'); activeIndex = -1; }

            function renderMenu(query) {
                const matches = matchesFor(query);
                activeIndex = -1;
                if (!matches.length) {
                    menu.innerHTML = `<div class="patient-combo-empty">${t('no_patients_found', 'No patients found')}</div>`;
                } else {
                    menu.innerHTML = matches.map(opt =>
                        `<div class="patient-combo-option" role="option" data-value="${opt.value}">${escapeHtml(opt.textContent)}</div>`
                    ).join('');
                }
                openMenu();
            }

            function rows() { return Array.from(menu.querySelectorAll('.patient-combo-option')); }

            function highlight(idx) {
                const list = rows();
                if (!list.length) return;
                activeIndex = (idx + list.length) % list.length;
                list.forEach((el, i) => el.classList.toggle('is-active', i === activeIndex));
                list[activeIndex].scrollIntoView({ block: 'nearest' });
            }

            function commit(value, label) {
                select.value = value;
                input.value = label;
                closeMenu();
                select.dispatchEvent(new Event('change', { bubbles: true }));
            }

            function syncInput() {
                const opt = select.selectedOptions[0];
                input.value = (opt && opt.value) ? opt.textContent : '';
            }
            select._comboSync = syncInput;

            input.addEventListener('focus', () => { input.select(); renderMenu(''); });
            input.addEventListener('input', () => renderMenu(input.value));
            input.addEventListener('keydown', (e) => {
                if (e.key === 'ArrowDown') {
                    e.preventDefault();
                    if (menu.hidden) renderMenu(input.value); else highlight(activeIndex + 1);
                } else if (e.key === 'ArrowUp') {
                    e.preventDefault();
                    if (!menu.hidden) highlight(activeIndex - 1);
                } else if (e.key === 'Enter') {
                    const list = rows();
                    let pick = -1;
                    if (activeIndex >= 0) pick = activeIndex;
                    else if (list.length === 1) pick = 0;
                    if (!menu.hidden && pick >= 0 && list[pick]) {
                        e.preventDefault();
                        commit(list[pick].dataset.value, list[pick].textContent);
                    }
                } else if (e.key === 'Escape') {
                    closeMenu();
                }
            });

            menu.addEventListener('mousedown', (e) => {
                const opt = e.target.closest('.patient-combo-option');
                if (!opt) return;
                e.preventDefault();
                commit(opt.dataset.value, opt.textContent);
            });

            input.addEventListener('blur', () => {
                setTimeout(() => { closeMenu(); syncInput(); }, 120);
            });

            // Resync the visible field whenever the value changes from elsewhere
            // (programmatic .value set + dispatched change, or a form reset).
            select.addEventListener('change', syncInput);
            if (select.form) select.form.addEventListener('reset', () => setTimeout(syncInput, 0));

            syncInput();
        }

        function getStatusBadgeClass(status) {
            const normalized = String(status || '').toLowerCase();
            if (normalized === 'completed' || normalized === 'paid' || normalized === 'active') return 'badge-active';
            if (normalized === 'confirmed' || normalized === 'scheduled' || normalized === 'pending') return 'badge-secondary';
            if (normalized === 'cancelled' || normalized === 'postponed' || normalized === 'inactive') return 'badge-pending';
            if (normalized === 'error' || normalized === 'failed') return 'badge-blocked';
            return 'badge-neutral';
        }

        function renderStateRow(message, options = {}) {
            const icon = options.icon || 'ℹ️';
            const title = options.title || message;
            const text = options.text || '';
            const buttonHtml = options.buttonHtml || '';
            return `
                <tr>
                    <td colspan="${options.colSpan || 1}">
                        <div class="${options.kind === 'error' ? 'error-state' : options.kind === 'loading' ? 'loading-state' : 'empty-state'}">
                            <div class="state-icon">${icon}</div>
                            <div class="state-title">${title}</div>
                            ${text ? `<div class="state-text">${text}</div>` : ''}
                            ${buttonHtml ? `<div class="state-actions">${buttonHtml}</div>` : ''}
                        </div>
                    </td>
                </tr>
            `;
        }

        function renderStatusBadge(status, fallback = '') {
            const label = safeDisplayText(status, fallback || t('unknown', 'Unknown'));
            return `<span class="badge ${getStatusBadgeClass(status)}">${label}</span>`;
        }
        
        // Dashboard
        async function loadDashboard() {
            refreshCloudBadge();
            const tbody = document.getElementById('recent-appointments-body');
            if (tbody) {
                tbody.innerHTML = renderStateRow(t('loading', 'Loading...'), {
                    icon: '⏳',
                    title: t('loading_dashboard', 'Loading dashboard data...'),
                    text: t('loading_dashboard_hint', 'Refreshing totals and recent appointments.'),
                    colSpan: 4,
                    kind: 'loading'
                });
            }

            try {
                const stats = await fetch('/api/stats').then(r => r.json());
                document.getElementById('total-patients').textContent = stats.total_patients;
                document.getElementById('today-appointments').textContent = stats.today_appointments;
                const visitsEl = document.getElementById('total-visits');
                if (visitsEl) visitsEl.textContent = stats.total_visits || 0;
                const revenueEl = document.getElementById('total-revenue');
                if (revenueEl) revenueEl.textContent = '₪ ' + (parseFloat(stats.total_revenue) || 0).toLocaleString('en-US', {minimumFractionDigits: 0, maximumFractionDigits: 0});

                const appointments = await fetch('/api/appointments/recent').then(r => r.json());
                if (!tbody) return;
                if (!appointments.length) {
                    tbody.innerHTML = renderStateRow(t('no_data', 'No data'), {
                        icon: '🗓️',
                        title: t('no_recent_appointments', 'No recent appointments yet'),
                        text: t('no_recent_appointments_hint', 'Schedule the first appointment to populate this area.'),
                        colSpan: 4,
                        buttonHtml: `<button class="btn btn-primary" type="button" onclick="showAddAppointmentModal()">${t('schedule_appointment', 'Schedule Appointment')}</button>`
                    });
                    return;
                }
                tbody.innerHTML = appointments.map(apt => `
                    <tr>
                        <td>${apt.patient_name}</td>
                        <td>${formatApptDate(apt.appointment_date)}</td>
                        <td>${apt.treatment_type || t('no_data', 'No data')}</td>
                        <td class="center-cell">${renderStatusBadge(apt.status, apt.status)}</td>
                    </tr>
                `).join('');
            } catch (error) {
                if (tbody) {
                    tbody.innerHTML = renderStateRow(t('save_failed', 'Save failed'), {
                        icon: '⚠️',
                        title: t('dashboard_load_failed', 'Unable to load dashboard'),
                        text: t('dashboard_load_failed_hint', 'Check the connection and try again.'),
                        colSpan: 4,
                        kind: 'error',
                        buttonHtml: `<button class="btn btn-primary" type="button" onclick="loadDashboard()">${t('refresh', 'Refresh')}</button>`
                    });
                }
            }
        }
        
        // Patients
        async function loadPatients() {
            const tbody = document.getElementById('patients-body');
            if (tbody) {
                tbody.innerHTML = renderStateRow(t('loading', 'Loading...'), {
                    icon: '⏳',
                    title: t('loading_patients', 'Loading patients...'),
                    text: t('loading_patients_hint', 'Fetching the patient list.'),
                    colSpan: 9,
                    kind: 'loading'
                });
            }
            try {
                const patients = await fetch('/api/patients').then(r => r.json());
                patientsCache = patients;
                renderPatientsTable(patientsCache);
            } catch (error) {
                if (tbody) {
                    tbody.innerHTML = renderStateRow(t('save_failed', 'Save failed'), {
                        icon: '⚠️',
                        title: t('patients_load_failed', 'Unable to load patients'),
                        text: t('patients_load_failed_hint', 'Refresh the page or try again in a moment.'),
                        colSpan: 9,
                        kind: 'error',
                        buttonHtml: `<button class="btn btn-primary" type="button" onclick="loadPatients()">${t('refresh', 'Refresh')}</button>`
                    });
                }
            }
        }

        function renderPatientsTable(patients) {
            const tbody = document.getElementById('patients-body');
            if (!patients || !patients.length) {
                tbody.innerHTML = renderStateRow(t('no_data', 'No data'), {
                    icon: '👥',
                    title: t('no_patients_found', 'No patients found'),
                    text: t('no_patients_found_hint', 'Add a patient or adjust your search to see matching records.'),
                    colSpan: 9,
                    buttonHtml: `<button class="btn btn-primary" type="button" onclick="showAddPatientModal()">${t('add_new_patient', 'Add New Patient')}</button>`
                });
                const status = document.getElementById('patient-search-status');
                if (status) status.textContent = t('no_patients_found', 'No patients found');
                return;
            }

            tbody.innerHTML = patients.map(patient => `
                <tr>
                    <td class="center-cell">${patient.id}</td>
                    <td><a href="#" onclick="viewPatientProfile(${patient.id}); return false;">${patient.first_name} ${patient.last_name}</a></td>
                    <td>${formatDateDisplay(patient.date_of_birth) || t('no_data', 'No data')}</td>
                    <td>${patient.gender ? t(patient.gender, patient.gender) : '—'}</td>
                    <td>${patient.phone || t('no_data', 'No data')}</td>
                    <td class="center-cell">${patient.appointment_count ?? 0}</td>
                    <td class="numeric-cell">₪ ${parseCurrency(patient.total_billed).toFixed(2)}</td>
                    <td class="numeric-cell">₪ ${parseCurrency(patient.balance).toFixed(2)}</td>
                    <td class="actions-cell">
                        <div class="action-buttons">
                            <button class="btn btn-primary" onclick="viewPatientProfile(${patient.id})">${t('view', 'View')}</button>
                            <button class="btn btn-success" onclick="showAddAppointmentModal(${patient.id})">${t('book', 'Book')}</button>
                            <button class="btn btn-warning" onclick="deletePatient(${patient.id})">${t('delete', 'Delete')}</button>
                        </div>
                    </td>
                </tr>
            `).join('');

            const status = document.getElementById('patient-search-status');
            if (status) {
                status.textContent = t('showing_n_patients', 'Showing {count} patient(s).').replace('{count}', patients.length);
            }
        }

        function filterPatientsTable() {
            const query = (document.getElementById('patient-search-input')?.value || '').trim().toLowerCase();
            if (!query) {
                renderPatientsTable(patientsCache);
                return;
            }

            const filtered = patientsCache.filter(patient => {
                const fullName = `${patient.first_name || ''} ${patient.last_name || ''}`.toLowerCase();
                return fullName.includes(query)
                    || String(patient.phone || '').toLowerCase().includes(query)
                    || String(patient.email || '').toLowerCase().includes(query);
            });
            renderPatientsTable(filtered);
        }

        function openFirstPatientMatch() {
            const query = (document.getElementById('patient-search-input')?.value || '').trim().toLowerCase();
            if (!query) {
                alert(t('select_patient_first', 'Please type a patient name first.'));
                return;
            }

            const match = patientsCache.find(patient => {
                const fullName = `${patient.first_name || ''} ${patient.last_name || ''}`.toLowerCase();
                return fullName.includes(query)
                    || String(patient.phone || '').toLowerCase().includes(query)
                    || String(patient.email || '').toLowerCase().includes(query);
            });

            if (!match) {
                alert(t('no_patient_match', 'No patient matched your search.'));
                return;
            }

            viewPatientProfile(match.id);
        }

        function clearPatientSearch() {
            const input = document.getElementById('patient-search-input');
            if (input) input.value = '';
            renderPatientsTable(patientsCache);
        }

        function safeDisplayText(value, fallback = '') {
            if (value === null || value === undefined) return fallback;
            const text = String(value).trim();
            if (!text) return fallback;
            const lowered = text.toLowerCase();
            if (lowered === 'null' || lowered === 'undefined') return fallback;
            return text;
        }

        function getAppointmentDateValue(appointment) {
            return safeDisplayText(
                appointment?.appointment_date || appointment?.appointment_datetime || appointment?.date_time,
                ''
            );
        }

        function parseAppointmentDate(value) {
            const normalized = safeDisplayText(value, '');
            if (!normalized) return null;
            const parsed = new Date(String(normalized).replace(' ', 'T'));
            return Number.isNaN(parsed.getTime()) ? null : parsed;
        }

        function hasDateAndTimeValue(value) {
            const normalized = safeDisplayText(value, '');
            if (!normalized) return false;
            if (!(normalized.includes('T') || normalized.includes(' '))) return false;
            const timePart = normalized.includes('T') ? normalized.split('T', 2)[1] : normalized.split(' ', 2)[1];
            return !!timePart && String(timePart).includes(':');
        }
        
        // Appointments
        async function loadAppointments() {
            const tbody = document.getElementById('appointments-body');
            if (tbody) {
                tbody.innerHTML = renderStateRow(t('loading', 'Loading...'), {
                    icon: '⏳',
                    title: t('loading_appointments', 'Loading appointments...'),
                    text: t('loading_appointments_hint', 'Refreshing the appointment list and calendar.'),
                    colSpan: 6,
                    kind: 'loading'
                });
            }
            try {
                const appointments = await fetch('/api/appointments').then(r => r.json());
                appointmentsCache = appointments;
                holidaysCache = await fetch('/api/holidays').then(r => r.json());
                renderAppointmentsCalendar(appointmentsCache);
                renderHolidaysTable();
                if (!tbody) return;
                if (!appointments.length) {
                    tbody.innerHTML = renderStateRow(t('no_data', 'No data'), {
                        icon: '📅',
                        title: t('no_appointments_yet', 'No appointments yet'),
                        text: t('no_appointments_yet_hint', 'Create the first appointment to populate the schedule table and calendar.'),
                        colSpan: 6,
                        buttonHtml: `<button class="btn btn-primary" type="button" onclick="showAddAppointmentModal()">${t('schedule_appointment', 'Schedule Appointment')}</button>`
                    });
                    return;
                }
                tbody.innerHTML = appointments.map(apt => `
                    <tr>
                        <td class="center-cell">${apt.id}</td>
                        <td><a href="#" onclick="viewPatientProfile(${apt.patient_id}); return false;">${safeDisplayText(apt.patient_name, t('unknown_patient', 'Unknown patient'))}</a></td>
                        <td>${formatApptDate(getAppointmentDateValue(apt)) || t('no_data', 'No data')}</td>
                        <td class="numeric-cell">${parseInt(apt.duration || apt.duration_minutes || 0, 10) || 0} ${t('min', 'min')}</td>
                        <td>${safeDisplayText(apt.treatment_type, t('no_data', 'No data'))}</td>
                        <td class="center-cell">${renderStatusBadge(apt.status, safeDisplayText(apt.status, 'scheduled'))}</td>
                    </tr>
                `).join('');
            } catch (error) {
                if (tbody) {
                    tbody.innerHTML = renderStateRow(t('save_failed', 'Save failed'), {
                        icon: '⚠️',
                        title: t('appointments_load_failed', 'Unable to load appointments'),
                        text: t('appointments_load_failed_hint', 'Try refreshing the tab or the page.'),
                        colSpan: 6,
                        kind: 'error',
                        buttonHtml: `<button class="btn btn-primary" type="button" onclick="loadAppointments()">${t('refresh', 'Refresh')}</button>`
                    });
                }
            }
            // Always wire date picker buttons in the appointments section (holiday form is here now)
            const apptSection = document.getElementById('appointments');
            if (apptSection) attachDatePickerButtons(apptSection);
        }

        function renderAppointmentsCalendar(appointments) {
            const calendar = document.getElementById('appointments-calendar');
            if (!calendar) return;
            const year = currentCalendarDate.getFullYear();
            const month = currentCalendarDate.getMonth();
            const firstDay = new Date(year, month, 1);
            const startDay = firstDay.getDay();
            const daysInMonth = new Date(year, month + 1, 0).getDate();
            const monthLabelElement = document.getElementById('calendar-month-label');
            if (monthLabelElement) {
                monthLabelElement.textContent = monthLabel(currentCalendarDate);
            }

            const grouped = {};
            appointments.forEach(apt => {
                const d = parseAppointmentDate(getAppointmentDateValue(apt));
                if (!d) return;
                if (d.getFullYear() === year && d.getMonth() === month) {
                    const key = d.getDate();
                    grouped[key] = grouped[key] || [];
                    grouped[key].push(apt);
                }
            });
            
            // Sort appointments within each day by time
            Object.keys(grouped).forEach(day => {
                grouped[day].sort((a, b) => {
                    const aDate = parseAppointmentDate(getAppointmentDateValue(a));
                    const bDate = parseAppointmentDate(getAppointmentDateValue(b));
                    const aTime = aDate ? aDate.getTime() : 0;
                    const bTime = bDate ? bDate.getTime() : 0;
                    return aTime - bTime;
                });
            });
            
            // Create a set of holiday dates for this month
            const holidaySet = new Set();
            holidaysCache.forEach(holiday => {
                const hDate = new Date(holiday.holiday_date);
                if (hDate.getFullYear() === year && hDate.getMonth() === month) {
                    holidaySet.add(hDate.getDate());
                }
            });
            
            const dayNames = currentLanguage === 'ar'
                ? ['الأحد', 'الإثنين', 'الثلاثاء', 'الأربعاء', 'الخميس', 'الجمعة', 'السبت']
                : ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
            calendar.innerHTML = dayNames.map(d => `<div class="calendar-day-header">${d}</div>`).join('') + Array.from({length: startDay}, () => '<div></div>').join('') + Array.from({length: daysInMonth}, (_, i) => {
                const day = i + 1;
                const isFriday = new Date(year, month, day).getDay() === 5;
                const isHoliday = isFriday || holidaySet.has(day);
                const holidayMarker = isHoliday ? `<div style="font-size:9px;color:#da4c58;font-weight:700;margin-bottom:3px;">🏖️ ${t('holiday_label', 'Holiday')}</div>` : '';
                const items = (grouped[day] || []).slice(0, 3).map(apt => {
                    const aptDate = parseAppointmentDate(getAppointmentDateValue(apt));
                    const aptTime = aptDate
                        ? aptDate.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'})
                        : t('no_data', 'No data');
                    const patientName = safeDisplayText(apt.patient_name, t('unknown_patient', 'Unknown patient'));
                    const treatmentLabel = safeDisplayText(apt.treatment_type, t('visit_label', 'Visit'));
                    return `<div class="calendar-event"><a href="#" class="calendar-patient-link" data-patient-id="${apt.patient_id}">${patientName}</a><br>${aptTime} · ${treatmentLabel}</div>`;
                }).join('');
                const clickableClass = isHoliday ? 'cursor-not-allowed' : 'cursor-pointer';
                const dateStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
                const dayDataAttr = isHoliday ? '' : `data-date="${dateStr}"`;
                return `<div class="calendar-day-cell ${clickableClass}" ${dayDataAttr}><div class="calendar-day-number">${day}</div>${holidayMarker}${items || `<div class="calendar-empty">${t('no_appointments_for_day', 'No appointments')}</div>`}</div>`;
            }).join('');

            if (!calendar.dataset.boundClicks) {
                calendar.addEventListener('click', (e) => {
                    const patientLink = e.target.closest('.calendar-patient-link');
                    if (patientLink) {
                        e.preventDefault();
                        e.stopPropagation();
                        const patientId = parseInt(patientLink.dataset.patientId, 10);
                        if (Number.isFinite(patientId)) viewPatientProfile(patientId);
                        return;
                    }

                    const dayCell = e.target.closest('.calendar-day-cell[data-date]');
                    if (!dayCell) return;
                    scheduleFromCalendarDate(dayCell.dataset.date);
                });
                calendar.dataset.boundClicks = '1';
            }
        }

        function scheduleFromCalendarDate(dateStr) {
            const datetimeLocal = dateStr + 'T09:00';
            showAddAppointmentModal(null, datetimeLocal);
        }

        function renderHolidaysTable() {
            const tbody = document.getElementById('holidays-body');
            if (!tbody) return;
            if (!holidaysCache.length) {
                tbody.innerHTML = `<tr><td colspan="4">${t('no_holidays_yet', 'No holidays yet')}</td></tr>`;
                return;
            }
            tbody.innerHTML = holidaysCache
                .slice()
                .sort((a, b) => String(a.holiday_date).localeCompare(String(b.holiday_date)))
                .map(item => `
                    <tr>
                        <td>${item.holiday_date || ''}</td>
                        <td>${item.name || ''}</td>
                        <td>${item.notes || ''}</td>
                        <td><button class="btn btn-danger" onclick="deleteHoliday(${item.id})">${t('delete', 'Delete')}</button></td>
                    </tr>
                `).join('');
        }

        async function deleteHoliday(id) {
            if (!confirm(t('delete_holiday_confirm', 'Delete this holiday?'))) return;
            await fetch(`/api/holidays/${id}`, { method: 'DELETE' });
            await loadAppointments();
        }

        function changeCalendarMonth(offset) {
            currentCalendarDate = new Date(currentCalendarDate.getFullYear(), currentCalendarDate.getMonth() + offset, 1);
            renderAppointmentsCalendar(appointmentsCache);
        }

        function goToCurrentCalendarMonth() {
            currentCalendarDate = new Date();
            renderAppointmentsCalendar(appointmentsCache);
        }

        function loadAppointmentsCalendar() {
            loadAppointments();
        }

        function getWeekBounds(baseDate = new Date()) {
            const d = new Date(baseDate);
            d.setHours(0, 0, 0, 0);
            const day = d.getDay();
            const diffToMonday = (day + 6) % 7;
            const weekStart = new Date(d);
            weekStart.setDate(d.getDate() - diffToMonday);
            const weekEnd = new Date(weekStart);
            weekEnd.setDate(weekStart.getDate() + 6);
            const toIsoDate = (dateObj) => dateObj.toISOString().slice(0, 10);
            return {
                startDate: toIsoDate(weekStart),
                endDate: toIsoDate(weekEnd)
            };
        }

        async function loadReports(startDateOverride = null, endDateOverride = null) {
            const startDate = startDateOverride || document.getElementById('report-start-date').value;
            const endDate = endDateOverride || document.getElementById('report-end-date').value;
            const params = new URLSearchParams();
            if (startDate) params.set('start_date', startDate);
            if (endDate) params.set('end_date', endDate);
            const report = await fetch(`/api/reports/summary?${params.toString()}`).then(r => r.json());
            document.getElementById('report-visits').textContent = report.visits;
            const reportRevenue = parseCurrency(report.revenue);
            const reportExpenses = parseCurrency(report.expenses);
            const reportLabExpenses = parseCurrency(report.lab_expenses);
            const reportClinicGrossProfit = parseCurrency(report.clinic_gross_profit);
            const reportProfit = parseCurrency(report.profit);
            document.getElementById('report-revenue').textContent = '₪ ' + reportRevenue.toFixed(2);
            document.getElementById('report-expenses').textContent = '₪ ' + reportExpenses.toFixed(2);
            document.getElementById('report-lab-expenses').textContent = '₪ ' + reportLabExpenses.toFixed(2);
            document.getElementById('report-clinic-gross-profit').textContent = '₪ ' + reportClinicGrossProfit.toFixed(2);
            document.getElementById('report-profit').textContent = '₪ ' + reportProfit.toFixed(2);

            const rangeText = startDate && endDate
                ? `${t('range', 'Range')}: ${formatDateDisplay(startDate)} - ${formatDateDisplay(endDate)}`
                : `${t('range', 'Range')}: ${t('full_period', 'full period')}`;
            document.getElementById('weekly-report-range').textContent = rangeText;
            await loadReportReceivables();
        }

        async function loadWeeklyReportFromPicker() {
            const pickerVal = document.getElementById('weekly-start-picker')?.value;
            const baseDate = pickerVal ? new Date(pickerVal + 'T00:00:00') : new Date();
            const { startDate, endDate } = getWeekBounds(baseDate);
            await _doLoadWeeklyReport(startDate, endDate);
        }

        async function loadWeeklyReport() {
            const { startDate, endDate } = getWeekBounds(new Date());
            await _doLoadWeeklyReport(startDate, endDate);
        }

        async function _doLoadWeeklyReport(startDate, endDate) {
            const weekly = await fetch(`/api/reports/weekly?week_start=${encodeURIComponent(startDate)}`).then(r => r.json());
            document.getElementById('report-visits').textContent = weekly.session_count || weekly.visits || 0;
            const weeklyRevenue = parseCurrency(weekly.revenue);
            const weeklyExpenses = parseCurrency(weekly.expenses);
            const weeklyLabExpenses = parseCurrency(weekly.lab_expenses);
            const weeklyClinicGrossProfit = parseCurrency(weekly.clinic_gross_profit);
            const weeklyProfit = parseCurrency(weekly.profit);
            document.getElementById('report-revenue').textContent = '₪ ' + weeklyRevenue.toFixed(2);
            document.getElementById('report-expenses').textContent = '₪ ' + weeklyExpenses.toFixed(2);
            document.getElementById('report-lab-expenses').textContent = '₪ ' + weeklyLabExpenses.toFixed(2);
            document.getElementById('report-clinic-gross-profit').textContent = '₪ ' + weeklyClinicGrossProfit.toFixed(2);
            document.getElementById('report-profit').textContent = '₪ ' + weeklyProfit.toFixed(2);
            document.getElementById('weekly-report-range').textContent = t('weekly_range_text', 'Weekly range: {start} to {end}')
                .replace('{start}', weekly.week_start_display || weekly.week_start)
                .replace('{end}', weekly.week_end_display || weekly.week_end);
            await loadReportReceivables();
        }

        async function loadMonthlyReport() {
            const monthInput = document.getElementById('report-month-picker');
            const monthValue = monthInput?.value || new Date().toISOString().slice(0, 7);
            if (monthInput && !monthInput.value) monthInput.value = monthValue;

            const [yearStr, monthStr] = monthValue.split('-');
            const year = parseInt(yearStr, 10);
            const month = parseInt(monthStr, 10);
            if (!Number.isFinite(year) || !Number.isFinite(month)) return;

            const monthStart = `${yearStr}-${String(month).padStart(2, '0')}-01`;
            const monthEndDate = new Date(year, month, 0);
            const monthEnd = `${yearStr}-${String(month).padStart(2, '0')}-${String(monthEndDate.getDate()).padStart(2, '0')}`;
            await loadReports(monthStart, monthEnd);
        }

        async function loadLabReport() {
            const startInput = document.getElementById('report-start-date');
            const endInput = document.getElementById('report-end-date');
            const today = new Date();
            const defaultStart = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-01`;
            const defaultEnd = today.toISOString().slice(0, 10);

            const startDate = startInput?.value || defaultStart;
            const endDate = endInput?.value || defaultEnd;
            if (startInput && !startInput.value) startInput.value = startDate;
            if (endInput && !endInput.value) endInput.value = endDate;

            await loadReports(startDate, endDate);
        }

        async function loadReportsSection() {
            switchReportsSubTab(currentReportsSubTab, null, false);
            if (currentReportsSubTab === 'weekly') {
                await loadWeeklyReport();
            } else if (currentReportsSubTab === 'monthly') {
                await loadMonthlyReport();
            } else {
                await loadLabReport();
            }
        }

        async function loadFinancialSection() {
            switchFinancialSubTab(currentFinancialSubTab, null, false);
            if (currentFinancialSubTab === 'management') {
                await loadReceivables();
                await loadExpenses();
            } else if (currentFinancialSubTab === 'billing') {
                await loadBilling();
            } else {
                await loadPatientsSelect('invoice-patient-select');
            }
        }

        async function loadSupportSection() {
            await loadSupportTips();
            await loadAuditLogs();
            await loadCloudSyncSettings();
            loadBluetoothSyncSettings();
            bindBluetoothSyncControls();
        }

        async function loadReceivables() {
            const payload = await fetch('/api/reports/receivables').then(r => r.json());
            const total = parseCurrency(payload.total_receivables || 0);
            const count = parseInt(payload.count || 0, 10);
            const rows = Array.isArray(payload.rows) ? payload.rows : [];

            const totalEl = document.getElementById('receivables-total');
            const countEl = document.getElementById('receivables-count');
            const tbody = document.getElementById('receivables-body');
            if (!totalEl || !countEl || !tbody) return;

            totalEl.textContent = `₪ ${total.toFixed(2)}`;
            countEl.textContent = String(Number.isFinite(count) ? count : 0);

            if (!rows.length) {
                tbody.innerHTML = renderStateRow(t('no_receivables', 'No receivables found.'), {
                    icon: '💳',
                    title: t('no_receivables', 'No receivables found.'),
                    text: t('receivables_empty_hint', 'Once invoices are created, the outstanding balance will appear here.'),
                    colSpan: 6
                });
                return;
            }

            tbody.innerHTML = rows.map(item => `
                <tr>
                    <td>${item.patient_name || ''}</td>
                    <td>₪ ${(parseCurrency(item.total_to_pay) - parseCurrency(item.total_discount)).toFixed(2)}</td>
                    <td>₪ ${parseCurrency(item.total_paid).toFixed(2)}</td>
                    <td>₪ ${parseCurrency(item.outstanding).toFixed(2)}</td>
                    <td>${formatDateDisplay(item.last_followup_date) || ''}</td>
                    <td>${parseInt(item.overdue_days || 0, 10)}</td>
                </tr>
            `).join('');
        }

        // The Reports tab's "Outstanding Balances" block — what each patient still owes.
        // This is a current snapshot (not scoped to the report's date range), shown
        // whenever a weekly/monthly/lab report is run.
        async function loadReportReceivables() {
            const totalEl = document.getElementById('report-receivables-total');
            const tbody = document.getElementById('report-receivables-body');
            if (!totalEl && !tbody) return;
            let payload;
            try { payload = await fetch('/api/reports/receivables').then(r => r.json()); }
            catch (_) { return; }
            const total = parseCurrency(payload?.total_receivables || 0);
            const rows = Array.isArray(payload?.rows) ? payload.rows : [];
            if (totalEl) totalEl.textContent = `₪ ${total.toFixed(2)}`;
            if (!tbody) return;
            if (!rows.length) {
                tbody.innerHTML = `<tr><td colspan="6">${t('no_receivables', 'No outstanding balances — everyone is paid up.')}</td></tr>`;
                return;
            }
            tbody.innerHTML = rows.map(item => `
                <tr>
                    <td>${item.patient_name || ''}</td>
                    <td>₪ ${(parseCurrency(item.total_to_pay) - parseCurrency(item.total_discount)).toFixed(2)}</td>
                    <td>₪ ${parseCurrency(item.total_paid).toFixed(2)}</td>
                    <td>₪ ${parseCurrency(item.outstanding).toFixed(2)}</td>
                    <td>${formatDateDisplay(item.last_followup_date) || ''}</td>
                    <td>${parseInt(item.overdue_days || 0, 10)}</td>
                </tr>
            `).join('');
        }

        async function refreshBillingCreditHint() {
            const sel = document.getElementById('billing-patient-select');
            const hint = document.getElementById('billing-credit-available');
            if (!sel || !hint) return;
            const pid = sel.value;
            if (!pid) { hint.textContent = ''; return; }
            try {
                const data = await fetch(`/api/patients/${pid}/credit`).then(r => r.json());
                const bal = parseCurrency(data && data.balance || 0);
                hint.textContent = bal > 0 ? `(${t('available', 'available')}: ₪${bal.toFixed(2)})` : `(${t('no_credit', 'no credit')})`;
            } catch (_) { hint.textContent = ''; }
        }

        async function loadBilling() {
            await loadPatientsSelect('billing-patient-select');
            await loadPatientsSelect('invoice-patient-select');
            const billSel = document.getElementById('billing-patient-select');
            if (billSel && !billSel.dataset.creditHintWired) {
                billSel.dataset.creditHintWired = '1';
                billSel.addEventListener('change', onBillingPatientChange);
            }
            refreshBillingCreditHint();

            const items = await fetch('/api/billing').then(r => r.json());
            billingCache = Array.isArray(items) ? items : [];
            const tbody = document.getElementById('billing-body');
            if (!tbody) return;

            applyBillingPatientView();

            if (!billingCache.length) {
                tbody.innerHTML = renderStateRow(t('no_data', 'No data'), {
                    icon: '🧾',
                    title: t('no_invoices_yet', 'No invoices yet'),
                    text: t('billing_empty_hint', 'Create a billing record to start tracking invoice history and balances.'),
                    colSpan: 8,
                    buttonHtml: `<button class="btn btn-primary" type="button" onclick="switchFinancialSubTab('billing')">${t('billing_tab', 'Billing')}</button>`
                });
                return;
            }

            tbody.innerHTML = billingCache.map(item => `
                <tr>
                    <td>${item.invoice_number || ''}</td>
                    <td>${item.patient_name || ''}</td>
                    <td>₪ ${parseCurrency(item.amount).toFixed(2)}</td>
                    <td>${fmtAmount(item.paid_amount, item.paid_amount_expr)}${parseCurrency(item.credit_used) > 0 ? ` <small style="opacity:0.7;">(+₪${parseCurrency(item.credit_used).toFixed(2)} ${t('credit', 'credit')})</small>` : ''}</td>
                    <td>₪ ${parseCurrency(item.balance_due).toFixed(2)}</td>
                    <td class="center-cell">${renderStatusBadge(item.payment_status, item.payment_status)}</td>
                    <td>${formatDateDisplay(item.payment_date) || ''}</td>
                    <td class="actions-cell">
                        <button class="btn btn-primary" onclick="printBillingInvoice(${item.id})">${t('print_invoice', 'Print Invoice')}</button>
                        <button class="btn btn-danger" onclick="deleteBillingRecord(${item.id})">${t('delete', 'Delete')}</button>
                    </td>
                </tr>
            `).join('');
        }

        // ── Payment Record: per-patient payment history ──
        // Picking a patient swaps the all-records table for that patient's
        // combined payment history (follow-up sheet payments + payment records).
        function applyBillingPatientView() {
            const sel = document.getElementById('billing-patient-select');
            const pid = sel ? sel.value : '';
            const histC = document.getElementById('billing-history-container');
            const allC = document.getElementById('billing-all-container');
            if (pid) {
                if (allC) allC.style.display = 'none';
                if (histC) histC.style.display = '';
                loadBillingPatientHistory(pid);
            } else {
                if (histC) histC.style.display = 'none';
                if (allC) allC.style.display = '';
            }
        }

        function onBillingPatientChange() {
            refreshBillingCreditHint();
            applyBillingPatientView();
        }

        function clearBillingPatientFilter() {
            const sel = document.getElementById('billing-patient-select');
            if (sel) { sel.value = ''; sel.dispatchEvent(new Event('change', { bubbles: true })); }
        }

        async function loadBillingPatientHistory(patientId) {
            const body = document.getElementById('billing-history-body');
            const foot = document.getElementById('billing-history-foot');
            const title = document.getElementById('billing-history-title');
            if (!body) return;
            body.innerHTML = `<tr><td colspan="5">${t('loading', 'Loading…')}</td></tr>`;
            if (foot) foot.innerHTML = '';

            let payload;
            try {
                payload = await fetch(`/api/patients/${patientId}/payment-history`).then(r => r.json());
            } catch (_) {
                body.innerHTML = `<tr><td colspan="5">${t('no_data', 'No data')}</td></tr>`;
                return;
            }
            const events = (payload && payload.events) || [];
            const totals = (payload && payload.totals) || {};

            if (title) {
                const pname = payload && payload.patient ? (payload.patient.name || '') : '';
                title.textContent = pname
                    ? `${t('payment_history', 'Payment History')} — ${pname}`
                    : t('payment_history', 'Payment History');
            }

            if (!events.length) {
                body.innerHTML = `<tr><td colspan="5">${t('no_payments_recorded', 'No payments recorded for this patient yet.')}</td></tr>`;
                if (foot) foot.innerHTML = '';
                return;
            }

            body.innerHTML = events.map(ev => {
                const isFollowup = ev.source === 'followup';
                const srcLabel = isFollowup
                    ? t('from_followup', 'Follow-up sheet')
                    : t('from_payment_record', 'Payment record');
                const srcBadge = `<span class="badge ${isFollowup ? 'badge-muted' : 'badge-secondary'}">${srcLabel}</span>`;
                let desc = ev.description || '—';
                if (isFollowup && ev.tooth_no) desc += ` <small style="opacity:0.7;">#${ev.tooth_no}</small>`;
                const creditNote = parseCurrency(ev.credit_used) > 0
                    ? ` <small style="opacity:0.7;">(+₪${parseCurrency(ev.credit_used).toFixed(2)} ${t('credit', 'credit')})</small>`
                    : '';
                return `
                    <tr>
                        <td>${formatDateDisplay(ev.date) || '—'}</td>
                        <td>${srcBadge}</td>
                        <td>${desc}</td>
                        <td>${isFollowup ? '—' : (ev.method || '—')}</td>
                        <td>${fmtAmount(ev.amount, ev.amount_expr)}${creditNote}</td>
                    </tr>`;
            }).join('');

            if (foot) {
                const totalPaid = parseCurrency(totals.total_paid);
                const totalCredit = parseCurrency(totals.total_credit_used);
                const creditFoot = totalCredit > 0
                    ? ` <small style="opacity:0.7;">(+₪${totalCredit.toFixed(2)} ${t('credit', 'credit')})</small>`
                    : '';
                foot.innerHTML = `
                    <tr>
                        <td colspan="4" style="text-align:right;font-weight:700;">${t('total_collected', 'Total Collected')}</td>
                        <td style="font-weight:700;">₪ ${totalPaid.toFixed(2)}${creditFoot}</td>
                    </tr>`;
            }
        }

        async function deleteBillingRecord(id) {
            if (!confirm(t('confirm_delete', 'Are you sure you want to delete?'))) return;
            const resp = await fetch(`/api/billing/${id}`, { method: 'DELETE' });
            if (!resp.ok) { alert('Delete failed'); return; }
            loadBilling();
            loadAuditLogs();
        }

        async function loadPatientInvoiceSummary() {
            const patientId = document.getElementById('invoice-patient-select')?.value;
            const startDate = document.getElementById('invoice-start-date')?.value || '';
            const endDate = document.getElementById('invoice-end-date')?.value || '';
            const tbody = document.getElementById('patient-invoice-body');
            if (!tbody) return;
            if (!patientId) {
                currentPatientInvoicePayload = null;
                tbody.innerHTML = `<tr><td colspan="6">${t('select_patient', 'Select Patient')}</td></tr>`;
                return;
            }

            const params = new URLSearchParams();
            if (startDate) params.set('start_date', startDate);
            if (endDate) params.set('end_date', endDate);
            const payload = await fetch(`/api/patients/${patientId}/invoice-summary?${params.toString()}`).then(r => r.json());
            currentPatientInvoicePayload = payload;
            const items = payload.items || [];
            const totals = payload.totals || {};

            document.getElementById('invoice-total-to-pay').textContent = `₪ ${parseCurrency(totals.total_to_pay).toFixed(2)}`;
            const discEl = document.getElementById('invoice-total-discount');
            if (discEl) discEl.textContent = `₪ ${parseCurrency(totals.total_discount).toFixed(2)}`;
            document.getElementById('invoice-total-paid').textContent = `₪ ${parseCurrency(totals.total_paid).toFixed(2)}`;
            document.getElementById('invoice-total-left').textContent = `₪ ${parseCurrency(totals.total_left).toFixed(2)}`;

            if (!items.length) {
                tbody.innerHTML = `<tr><td colspan="6">${t('no_data', 'No data')}</td></tr>`;
                return;
            }

            tbody.innerHTML = items.map(item => `
                <tr>
                    <td>${formatDateDisplay(item.followup_date) || ''}</td>
                    <td>${item.treatment_procedure || ''}${item.tooth_no ? ` <small style="opacity:0.7;">#${item.tooth_no}</small>` : ''}</td>
                    <td>${fmtAmount(item.price, item.price_expr)}</td>
                    <td>${(parseCurrency(item.discount) > 0 || item.discount_expr) ? fmtAmount(item.discount, item.discount_expr) : '—'}</td>
                    <td>${fmtAmount(item.payment, item.payment_expr)}</td>
                    <td>₪ ${parseCurrency(item.remaining_amount).toFixed(2)}</td>
                </tr>
            `).join('');
        }

        function openPrintWindow(html) {
            const printWindow = window.open('', '_blank', 'width=900,height=700');
            if (!printWindow) return;
            printWindow.document.write(html);
            printWindow.document.close();
            printWindow.focus();
            const imgs = Array.from(printWindow.document.images);
            if (!imgs.length) { printWindow.print(); return; }
            let pending = imgs.length;
            const tryPrint = () => { if (--pending === 0) printWindow.print(); };
            imgs.forEach(img => {
                if (img.complete) tryPrint();
                else { img.onload = tryPrint; img.onerror = tryPrint; }
            });
        }

        function invoiceDocumentTemplate({ title, subtitle, rows, totals, lang = 'en' }) {
            const printLang = lang === 'ar' ? 'ar' : 'en';
            const printDir = printLang === 'ar' ? 'rtl' : 'ltr';
            const totalPrice = parseCurrency(totals?.total_price);
            const totalDiscount = parseCurrency(totals?.total_discount);
            const totalToPay = parseCurrency(totals?.total_to_pay);
            const totalPaid = parseCurrency(totals?.total_paid);
            const totalLeft = parseCurrency(totals?.total_left);
            return `
<!DOCTYPE html>
<html lang="${printLang}" dir="${printDir}">
<head>
    <meta charset="UTF-8">
    <title>${title}</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 24px; color: #222; direction: ${printDir}; text-align: ${printDir === 'rtl' ? 'right' : 'left'}; }
        .inv-header { display: flex; align-items: center; gap: 16px; margin-bottom: 4px; flex-direction: ${printDir === 'rtl' ? 'row-reverse' : 'row'}; }
        .inv-header img { height: 64px; width: auto; }
        .inv-header-text { flex: 1; }
        h1 { margin: 0 0 4px 0; font-size: 24px; }
        .sub { margin: 0 0 16px 0; color: #555; font-size: 13px; }
        table { width: 100%; border-collapse: collapse; margin-top: 12px; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: ${printDir === 'rtl' ? 'right' : 'left'}; }
        th { background: #f3f3f3; }
        .totals { margin-top: 16px; display: flex; gap: 16px; }
        .total-card { border: 1px solid #ddd; border-radius: 8px; padding: 10px 12px; min-width: 140px; }
    </style>
</head>
<body>
    <div class="inv-header">
        <img src="/logo" alt="DentaCare">
        <div class="inv-header-text">
            <h1>${title}</h1>
            <p class="sub">${subtitle || ''}</p>
        </div>
    </div>
    <table>
        <thead>
            <tr>
                <th>${tForLang(printLang, 'date', 'Date')}</th>
                <th>${tForLang(printLang, 'description', 'Description')}</th>
                <th>${tForLang(printLang, 'price', 'Price')}</th>
                <th>${tForLang(printLang, 'discount', 'Discount')}</th>
                <th>${tForLang(printLang, 'paid', 'Paid')}</th>
                <th>${tForLang(printLang, 'balance', 'Balance')}</th>
            </tr>
        </thead>
        <tbody>
            ${rows}
        </tbody>
    </table>
    <div class="totals">
        <div class="total-card">${tForLang(printLang, 'subtotal', 'Subtotal')}: ₪ ${totalPrice.toFixed(2)}</div>
        <div class="total-card">${tForLang(printLang, 'discount', 'Discount')}: ₪ ${totalDiscount.toFixed(2)}</div>
        <div class="total-card">${tForLang(printLang, 'total_to_pay', 'Total to Pay')}: ₪ ${totalToPay.toFixed(2)}</div>
        <div class="total-card">${tForLang(printLang, 'paid', 'Paid')}: ₪ ${totalPaid.toFixed(2)}</div>
        <div class="total-card">${tForLang(printLang, 'left', 'Left')}: ₪ ${totalLeft.toFixed(2)}</div>
    </div>
</body>
</html>
            `;
        }

        function printBillingInvoice(billingId) {
            const printLang = getInvoicePrintLanguage();
            const lang = printLang === 'ar' ? 'ar' : 'en';
            window.open(`/invoice/${billingId}?lang=${lang}`, '_blank');
        }

        function printInvoicePayload(payload) {
            if (!payload || !Array.isArray(payload.items)) {
                alert(t('invoice_preview_unavailable', 'No invoice data to print yet.'));
                return;
            }

            const printLang = getInvoicePrintLanguage();

            const amtCellHtml = (num, expr) => {
                const n = parseCurrency(num).toFixed(2);
                const e = String(expr || '').trim();
                return e ? `${escapeHtml(e)} = ₪ ${n}` : `₪ ${n}`;
            };
            const rows = payload.items.length
                ? payload.items.map(item => `
                    <tr>
                        <td>${escapeHtml(formatDateDisplay(item.followup_date) || '')}</td>
                        <td>${escapeHtml(item.treatment_procedure || '')}${item.tooth_no ? ' #' + escapeHtml(String(item.tooth_no)) : ''}</td>
                        <td>${amtCellHtml(item.price, item.price_expr)}</td>
                        <td>${(parseCurrency(item.discount) > 0 || item.discount_expr) ? amtCellHtml(item.discount, item.discount_expr) : '—'}</td>
                        <td>${amtCellHtml(item.payment, item.payment_expr)}</td>
                        <td>₪ ${parseCurrency(item.remaining_amount).toFixed(2)}</td>
                    </tr>
                `).join('')
                : `<tr><td colspan="6">${escapeHtml(tForLang(printLang, 'no_data', 'No data'))}</td></tr>`;

            const patientName = escapeHtml(payload.patient?.name || '');
            const phone = escapeHtml(payload.patient?.phone || '');
            const doctorName = escapeHtml(getDoctorNameForLanguage(printLang));
            const subtitle = `${tForLang(printLang, 'patient', 'Patient')}: ${patientName}${phone ? ` | ${tForLang(printLang, 'phone', 'Phone')}: ${phone}` : ''} | ${doctorName}`;
            const html = invoiceDocumentTemplate({
                title: tForLang(printLang, 'print_invoice', 'Print Invoice'),
                subtitle,
                rows,
                totals: payload.totals || {},
                lang: printLang
            });
            openPrintWindow(html);
        }

        function printCurrentPatientInvoice() {
            printInvoicePayload(currentPatientInvoicePayload);
        }

        async function printPatientInvoiceById(patientId) {
            const params = new URLSearchParams();
            const payload = await fetch(`/api/patients/${patientId}/invoice-summary?${params.toString()}`).then(r => r.json());
            printInvoicePayload(payload);
        }

        // Used from the patient profile — reads the per-profile language dropdown
        async function printPatientInvoiceByIdWithLang(patientId) {
            const profileLangSelect = document.getElementById('profile-invoice-lang');
            const selectedLang = profileLangSelect?.value || 'current';
            // Temporarily override the global invoice-print-language selector
            const globalSelect = document.getElementById('invoice-print-language');
            const prevVal = globalSelect?.value;
            if (globalSelect && selectedLang !== 'current') globalSelect.value = selectedLang;
            const params = new URLSearchParams();
            const payload = await fetch(`/api/patients/${patientId}/invoice-summary?${params.toString()}`).then(r => r.json());
            printInvoicePayload(payload);
            // Restore global selector
            if (globalSelect && prevVal !== undefined) globalSelect.value = prevVal;
        }

        async function loadAuditLogs() {
            const items = await fetch('/api/audit-logs?limit=200').then(r => r.json());
            const tbody = document.getElementById('audit-logs-body');
            if (!tbody) return;

            if (!items || !items.length) {
                tbody.innerHTML = `<tr><td colspan="5">${t('no_data', 'No data')}</td></tr>`;
                return;
            }

            tbody.innerHTML = items.map(item => `
                <tr>
                    <td>${item.id}</td>
                    <td>${formatDateDisplay((item.created_at||'').slice(0,10))} ${(item.created_at||'').slice(11,16)}</td>
                    <td>${item.action_type || ''}</td>
                    <td>${item.entity_type || ''}${item.entity_id ? ` #${item.entity_id}` : ''}</td>
                    <td>${item.details || ''}</td>
                </tr>
            `).join('');
        }

        async function loadExpenses() {
            const expenses = await fetch('/api/expenses').then(r => r.json());
            const selectedPeriod = document.getElementById('expense-filter-period')?.value || 'all';
            const selectedPaymentStatus = document.getElementById('expense-filter-status-select')?.value || 'all';
            const tbody = document.getElementById('expenses-body');
            const status = document.getElementById('expense-filter-status');
            if (!tbody) return;

            const today = new Date();
            today.setHours(0, 0, 0, 0);
            const dayOfWeek = today.getDay();
            const diffToMonday = (dayOfWeek + 6) % 7;
            const weekStart = new Date(today);
            weekStart.setDate(today.getDate() - diffToMonday);
            const weekEnd = new Date(weekStart);
            weekEnd.setDate(weekStart.getDate() + 6);
            const monthStart = new Date(today.getFullYear(), today.getMonth(), 1);
            const monthEnd = new Date(today.getFullYear(), today.getMonth() + 1, 0);

            const filteredExpenses = expenses.filter(item => {
                // Filter by period
                if (selectedPeriod !== 'all') {
                    const rawDate = item.expense_date || '';
                    if (!rawDate) return false;
                    const itemDate = new Date(rawDate);
                    if (Number.isNaN(itemDate.getTime())) return false;
                    itemDate.setHours(0, 0, 0, 0);

                    if (selectedPeriod === 'today') {
                        if (itemDate.getTime() !== today.getTime()) return false;
                    } else if (selectedPeriod === 'week') {
                        if (itemDate < weekStart || itemDate > weekEnd) return false;
                    } else if (selectedPeriod === 'month') {
                        if (itemDate < monthStart || itemDate > monthEnd) return false;
                    }
                }
                
                // Filter by payment status
                if (selectedPaymentStatus !== 'all') {
                    const itemStatus = item.payment_status || 'pending';
                    if (itemStatus !== selectedPaymentStatus) return false;
                }
                
                return true;
            });

            if (!filteredExpenses.length) {
                tbody.innerHTML = renderStateRow(t('no_expenses_found', 'No expenses found'), {
                    icon: '🧾',
                    title: t('no_expenses_found', 'No expenses found'),
                    text: t('expenses_empty_hint', 'Adjust the filters or add the first expense entry.'),
                    colSpan: 7
                });
                if (status) {
                    status.textContent = t('no_expenses_found', 'No expenses found');
                }
                return;
            }
            tbody.innerHTML = filteredExpenses.map(item => `
                <tr>
                    <td>${item.expense_date || ''}</td>
                    <td>${item.category || ''}</td>
                    <td class="numeric-cell">₪ ${parseCurrency(item.amount).toFixed(2)}</td>
                    <td class="center-cell">
                        <select class="expense-status-select" data-status="${item.payment_status || 'postponed'}" onchange="this.dataset.status=this.value;updateExpenseStatus(${item.id}, this.value)">
                            <option value="paid" ${item.payment_status === 'paid' ? 'selected' : ''}>${t('paid', 'Paid')}</option>
                            <option value="postponed" ${item.payment_status === 'postponed' ? 'selected' : ''}>${t('postponed', 'Postponed')}</option>
                        </select>
                    </td>
                    <td>${item.vendor || ''}</td>
                    <td>${item.notes || ''}</td>
                    <td class="actions-cell"><button class="btn btn-danger" onclick="deleteExpense(${item.id})">${t('delete', 'Delete')}</button></td>
                </tr>
            `).join('');

            if (status) {
                status.textContent = t('showing_expenses_count', 'Showing {count} expense(s).').replace('{count}', filteredExpenses.length);
            }
        }
        
        async function updateExpenseStatus(id, newStatus) {
            const response = await fetch(`/api/expenses/${id}`, {
                method: 'PUT',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({payment_status: newStatus})
            });
            if (response.ok) {
                loadExpenses();
                loadReports();
                loadAuditLogs();
                loadDashboard();
            }
        }

        async function deleteExpense(id) {
            if (!confirm(t('delete_expense_confirm', 'Delete this expense?'))) return;
            await fetch(`/api/expenses/${id}`, { method: 'DELETE' });
            loadExpenses();
            loadReports();
            loadAuditLogs();
            loadDashboard();
        }

        async function loadSupportTips() {
            const tips = await fetch('/api/support').then(r => r.json());
            const container = document.getElementById('support-content');
            container.innerHTML = tips.map(tip => `<div style="padding:16px;border:1px solid #e5e7eb;border-radius:12px;margin-bottom:12px;"><h4>${tip.title}</h4><p>${tip.detail}</p></div>`).join('');
        }

        async function downloadBackup() {
            window.location.href = '/api/backup';
        }

        async function changeAccountPassword() {
            const current = document.getElementById('acct-current-password')?.value || '';
            const next = document.getElementById('acct-new-password')?.value || '';
            const confirm = document.getElementById('acct-confirm-password')?.value || '';
            if (!current || !next) { alert(t('fill_all_fields', 'Please fill in all fields.')); return; }
            if (next.length < 4) { alert(t('password_too_short', 'New password must be at least 4 characters.')); return; }
            if (next !== confirm) { alert(t('passwords_do_not_match', 'New passwords do not match.')); return; }
            try {
                const resp = await fetch('/api/auth/change-password', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ current_password: current, new_password: next })
                });
                const payload = await resp.json().catch(() => ({}));
                if (!resp.ok) { alert(payload.error || t('save_failed', 'Save failed')); return; }
                document.getElementById('acct-current-password').value = '';
                document.getElementById('acct-new-password').value = '';
                document.getElementById('acct-confirm-password').value = '';
                alert(t('password_changed', 'Password changed successfully.'));
            } catch (_) {
                alert(t('save_failed', 'Save failed'));
            }
        }

        // ── Cloud sync (Settings → Cloud Sync, + dashboard badge) ─────────────
        function _ar() { return currentLanguage === 'ar'; }

        function _relativeTime(iso) {
            if (!iso) return '';
            const ms = Date.parse(String(iso).replace(' ', 'T'));
            if (!Number.isFinite(ms)) return String(iso);
            const secs = Math.max(0, Math.round((Date.now() - ms) / 1000));
            if (secs < 60)  return _ar() ? 'الآن' : 'just now';
            const mins = Math.round(secs / 60);
            if (mins < 60)  return mins + (_ar() ? ' د' : ' min ago');
            const hrs = Math.round(mins / 60);
            if (hrs < 24)   return hrs + (_ar() ? ' س' : ' h ago');
            return Math.round(hrs / 24) + (_ar() ? ' ي' : ' d ago');
        }

        async function fetchCloudStatus() {
            try { return await fetch('/api/cloud/status').then(r => r.json()); }
            catch (_) { return null; }
        }

        function renderCloudBadge(st) {
            const badge = document.getElementById('cloud-sync-badge');
            if (!badge) return;
            if (!st || st.cloud_mode) { badge.style.display = 'none'; return; }
            badge.style.display = '';
            badge.style.color = 'var(--muted)';
            if (!st.configured) {
                badge.textContent = _ar() ? '☁️ المزامنة السحابية: غير مفعّلة' : '☁️ Cloud sync: off';
                return;
            }
            const res = String(st.last_sync_result || '');
            if (res === 'ok') {
                badge.textContent = (_ar() ? '☁️ تمت المزامنة ' : '☁️ Synced ') + _relativeTime(st.last_sync_at);
            } else if (res.indexOf('error') === 0) {
                badge.textContent = _ar() ? '⚠️ فشل المزامنة السحابية' : '⚠️ Cloud sync error';
                badge.style.color = '#c0392b';
            } else {
                badge.textContent = _ar() ? '☁️ بانتظار المزامنة' : '☁️ Cloud sync pending';
            }
        }

        async function refreshCloudBadge() { renderCloudBadge(await fetchCloudStatus()); }

        async function loadCloudSyncSettings() {
            const st = await fetchCloudStatus();
            renderCloudBadge(st);
            const line = document.getElementById('cloud-status-line');
            const pairForm = document.getElementById('cloud-pair-form');
            const pairedActions = document.getElementById('cloud-paired-actions');
            if (!line) return;
            const show = (el, on) => { if (el) el.style.display = on ? '' : 'none'; };
            if (!st) { line.textContent = ''; show(pairForm, false); show(pairedActions, false); return; }
            if (st.cloud_mode) {
                line.innerHTML = '<em>' + (_ar() ? 'هذا هو الخادم السحابي.' : 'This is the cloud node.') + '</em>';
                show(pairForm, false); show(pairedActions, false);
                return;
            }
            if (st.configured) {
                show(pairForm, false); show(pairedActions, true);
                const parts = [];
                parts.push((_ar() ? 'مرتبط بـ ' : 'Paired with ') + '<strong>' + (st.cloud_url || '') + '</strong>');
                if (st.clinic_id) parts.push((_ar() ? 'معرّف العيادة: ' : 'Clinic ID: ') + st.clinic_id);
                if (st.last_sync_at) {
                    const ok = String(st.last_sync_result) === 'ok';
                    parts.push((_ar() ? 'آخر مزامنة: ' : 'Last sync: ') + _relativeTime(st.last_sync_at)
                               + (ok ? ' ✓' : ' — ' + (st.last_sync_result || '')));
                } else {
                    parts.push(_ar() ? 'لم تتم أي مزامنة بعد' : 'No sync yet');
                }
                parts.push((_ar() ? 'كل ' : 'every ') + (st.sync_interval_minutes || 15) + (_ar() ? ' دقيقة' : ' min'));
                line.innerHTML = parts.join('<br>');
            } else {
                show(pairForm, true); show(pairedActions, false);
                line.innerHTML = '<em>' + (_ar() ? 'غير مرتبط بالسحابة بعد.' : 'Not paired with the cloud yet.') + '</em>';
            }
        }

        async function cloudPair(btn) {
            const url = (document.getElementById('cloud-url-input')?.value || '').trim();
            const serial = (document.getElementById('cloud-serial-input')?.value || '').trim();
            if (!url || serial.length < 8) {
                alert(_ar() ? 'أدخل رابط الخادم السحابي والرقم التسلسلي (٨ خانات على الأقل).'
                            : 'Enter the cloud server URL and a serial number (at least 8 characters).');
                return;
            }
            if (btn) btn.disabled = true;
            try {
                const resp = await fetch('/api/cloud/pair', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ cloud_url: url, serial_number: serial })
                });
                const payload = await resp.json().catch(() => ({}));
                if (!resp.ok) { alert(payload.error || (_ar() ? 'فشل الربط' : 'Pairing failed')); return; }
                const si = document.getElementById('cloud-serial-input'); if (si) si.value = '';
                const fs = payload.first_sync || {};
                alert((_ar() ? 'تم الربط بالسحابة. ' : 'Paired with the cloud. ')
                      + (fs.ok ? `↓${fs.pulled || 0} ↑${fs.pushed || 0}` : (fs.error ? ('— ' + fs.error) : '')));
                await loadCloudSyncSettings();
            } catch (_) {
                alert(_ar() ? 'تعذّر الوصول إلى الخادم.' : 'Could not reach the server.');
            } finally { if (btn) btn.disabled = false; }
        }

        async function cloudSyncNow(btn) {
            if (btn) btn.disabled = true;
            try {
                const resp = await fetch('/api/cloud/sync-now', { method: 'POST' });
                const payload = await resp.json().catch(() => ({}));
                if (!resp.ok) {
                    alert(payload.error || (_ar() ? 'فشل المزامنة' : 'Sync failed'));
                } else if (payload.ok) {
                    alert((_ar() ? 'تمت المزامنة. ' : 'Synced. ') + `↓${payload.pulled || 0} ↑${payload.pushed || 0}`);
                } else {
                    alert((_ar() ? 'لم تكتمل المزامنة: ' : 'Sync did not complete: ') + (payload.error || ''));
                }
            } catch (_) {
                alert(_ar() ? 'تعذّر الوصول إلى الخادم.' : 'Could not reach the server.');
            } finally { if (btn) btn.disabled = false; await loadCloudSyncSettings(); }
        }

        async function cloudUnpair() {
            if (!confirm(_ar() ? 'إلغاء ربط هذه العيادة بالسحابة؟' : 'Unpair this clinic from the cloud?')) return;
            try {
                await fetch('/api/cloud/unpair', { method: 'POST' });
                alert(_ar() ? 'تم إلغاء الربط.' : 'Unpaired from the cloud.');
            } catch (_) {}
            await loadCloudSyncSettings();
        }

        // Reveal the phone-pairing QR. The image src points at the authed
        // /api/cloud/pairing-qr endpoint; a ts cache-buster forces a fresh
        // render each click so a stale (e.g. post-unpair) image never lingers.
        function cloudShowPairingQr() {
            const wrap = document.getElementById('cloud-pairing-qr');
            const img = document.getElementById('cloud-pairing-qr-img');
            if (!wrap || !img) return;
            img.src = '/api/cloud/pairing-qr?ts=' + Date.now();
            wrap.style.display = '';
        }

        // ── Bluetooth Sync (Settings → Bluetooth Sync) ────────────────────────

        function _friendlyBtDesktopError(raw) {
          // Map the server-side last_error string to plain language. Server
          // errors we currently emit: "no bluetooth port available",
          // "serial: …", "WSAError=…", "OSError: …". Everything else falls
          // through to a friendly catch-all.
          const r = (raw || '').toString().toLowerCase();
          const ar = _ar();
          if (r.includes('no bluetooth port') || r.includes('af_bth') || r.includes('wsaerror')) {
            return ar
              ? 'تعذّر بدء البلوتوث — تحقق من تشغيل البلوتوث في هذا الحاسوب.'
              : "Bluetooth couldn't start — is this PC's Bluetooth turned on?";
          }
          if (r.includes('serial:')) {
            return ar
              ? 'تعذّر فتح منفذ البلوتوث.'
              : "Couldn't open the Bluetooth port.";
          }
          return ar ? 'حدث خطأ في مزامنة البلوتوث.' : 'Bluetooth sync hit an error.';
        }

        function _showBtTransientError() {
          // On fetch failure / non-OK status, keep the toggle visible (so the
          // user can still try) and surface a one-line "temporarily unavailable"
          // message in the existing error line. Don't hide the whole card —
          // a transient blip should not make controls disappear.
          const errLine = document.getElementById('bt-error-line');
          if (!errLine) return;
          errLine.textContent = _ar()
            ? 'حالة البلوتوث غير متاحة مؤقتًا.'
            : 'Bluetooth status temporarily unavailable.';
          errLine.style.display = '';
        }

        async function loadBluetoothSyncSettings() {
          // Re-uses the original entry point name so loadSupportSection() still
          // wires up the BT card.
          try {
            const r = await fetch('/api/bt/status', {credentials: 'same-origin'});
            if (!r.ok) {
              console.warn('[bt-sync] /api/bt/status', r.status);
              _showBtTransientError();
              return;
            }
            const s = await r.json();
            const toggle = document.getElementById('bt-enabled');
            if (toggle) toggle.checked = !!s.enabled;
            const errLine = document.getElementById('bt-error-line');
            if (errLine) {
              if (s.enabled && s.last_error) {
                errLine.textContent = _friendlyBtDesktopError(s.last_error);
                errLine.style.display = '';
              } else {
                errLine.textContent = '';
                errLine.style.display = 'none';
              }
            }
          } catch (e) {
            console.warn('[bt-sync] /api/bt/status', e);
            _showBtTransientError();
          }
        }

        async function _btConfigure(enabled) {
          // Single network call. Returns the parsed JSON or null on failure.
          // com_port is no longer sent — the native listener doesn't need one;
          // the COM-port fallback uses the server-side default picker.
          try {
            const r = await fetch('/api/bt/configure', {
              method: 'POST', credentials: 'same-origin',
              headers: {'Content-Type': 'application/json'},
              body: JSON.stringify({enabled}),
            });
            if (!r.ok) {
              console.warn('[bt-sync] /api/bt/configure', r.status);
              return null;
            }
            return await r.json();
          } catch (e) {
            console.warn('[bt-sync] /api/bt/configure', e);
            return null;
          }
        }

        async function bluetoothToggleEnabled(enabled) {
          // Disable the input while the round-trip is in flight so spam-clicks
          // can't race parallel POSTs (the perceived final state would otherwise
          // be whichever request resolves last, not the user's last click).
          const toggle = document.getElementById('bt-enabled');
          if (toggle) toggle.disabled = true;
          try {
            const res = await _btConfigure(!!enabled);
            if (!res) {
              alert(_ar() ? 'فشل الحفظ' : 'Save failed');
            }
            await loadBluetoothSyncSettings();
          } finally {
            if (toggle) toggle.disabled = false;
          }
        }

        function bindBluetoothSyncControls() {
          // Kept as a no-op stub so loadSupportSection's existing call site
          // doesn't error. The toggle's change handler is wired inline via the
          // onchange="" attribute, so no further binding is needed.
        }

        function switchProfileTab(tabName, btn) {
            const modal = document.getElementById('patient-profile-modal');
            modal.querySelectorAll('.profile-tab').forEach(b => b.classList.remove('active'));
            modal.querySelectorAll('.profile-tab-content').forEach(p => p.classList.remove('active'));
            if (btn) btn.classList.add('active');
            const panel = modal.querySelector(`#profile-tab-${tabName}`);
            if (panel) panel.classList.add('active');
        }

        async function viewPatientProfile(patientId) {
            if (!treatmentProceduresCache.length) {
                await loadTreatmentProcedures();
            }
            const profile = await fetch(`/api/patients/${patientId}/full-profile`).then(r => r.json());
            const patient = profile.patient;
            currentProfilePatient = patient;
            patientProfileCache[patientId] = patient;
            const content = document.getElementById('patient-profile-content');
            const followups = profile.followups || [];
            followupsCache[patientId] = followups;
            const followupTotals = followups.reduce((acc, item) => {
                acc.totalToPay += parseCurrency(item.price || 0);
                acc.totalDiscount += parseCurrency(item.discount || 0);
                acc.totalPaid += parseCurrency(item.payment || 0);
                return acc;
            }, { totalToPay: 0, totalDiscount: 0, totalPaid: 0 });
            const totalToPay = Math.max(0, followupTotals.totalToPay);
            const totalDiscount = Math.max(0, followupTotals.totalDiscount);
            const totalPaid = Math.max(0, followupTotals.totalPaid);
            const totalLeft = Math.max(0, totalToPay - totalDiscount - totalPaid);
            currentFollowupBalance = totalLeft;
            content.innerHTML = `
                <div class="profile-stats">
                    <div class="stat-card stat-card-teal">
                        <h3 style="font-size:1.3rem;white-space:normal;">${patient.first_name} ${patient.last_name}</h3>
                        <p>📞 ${patient.phone || t('no_phone', 'No phone')}</p>
                        ${profile.age != null ? `<p>🎂 ${profile.age} ${currentLanguage==='ar'?'سنة':'yrs'}${profile.birth_date_display ? ' · ' + profile.birth_date_display : ''}</p>` : ''}
                    </div>
                    <div class="stat-card stat-card-blue">
                        <h3>${profile.appointments.length}</h3>
                        <p>${t('appointments', 'Appointments')}</p>
                    </div>
                    <div class="stat-card stat-card-green">
                        <h3>${followups.length}</h3>
                        <p>${t('followups_count', 'Follow-ups')}</p>
                    </div>
                    <div class="stat-card stat-card-amber">
                        <h3>₪${currentFollowupBalance.toFixed(2)}</h3>
                        <p>${t('current_balance', 'Balance Due')}</p>
                        <p style="font-size:0.8rem;opacity:0.88;"><span style="white-space:nowrap;">↑ ₪${totalToPay.toFixed(2)}</span> &nbsp;<span style="white-space:nowrap;">✓ ₪${totalPaid.toFixed(2)}</span></p>
                    </div>
                    <div class="stat-card">
                        <h3>₪${(profile.credit_balance||0).toFixed(2)}</h3>
                        <p>${t('credit_balance','Credit Balance')}</p>
                    </div>
                </div>

                <nav class="profile-tabs">
                    <button class="profile-tab active" onclick="switchProfileTab('overview', this)">${t('overview','Overview')}</button>
                    <button class="profile-tab" onclick="switchProfileTab('followups', this)">${t('followup_sheet','Follow-ups')} (${followups.length})</button>
                    <button class="profile-tab" onclick="switchProfileTab('images', this)">${t('medical_images','Images')} (${profile.medical_images.length})</button>
                </nav>

                <div id="profile-tab-overview" class="profile-tab-content active">
                    <div class="toolbar-row" style="margin-top:0; margin-bottom:16px; flex-wrap:wrap;">
                        <button class="btn btn-primary" type="button" onclick="openAppointmentFromProfile(${patient.id})">+ ${t('book_for_patient', 'Book Appointment')}</button>
                        <div style="display:flex;align-items:center;gap:6px;">
                            <select id="profile-invoice-lang" style="height:38px;padding:4px 10px;border-radius:8px;border:1.5px solid var(--border);background:var(--card);color:var(--text);font-size:0.9rem;" title="${t('print_language','Print Language')}">
                                <option value="current">${t('print_language_current','App Language')}</option>
                                <option value="ar">${t('print_language_arabic','Arabic')}</option>
                                <option value="en">${t('print_language_english','English')}</option>
                            </select>
                            <button class="btn btn-success" type="button" onclick="printPatientInvoiceByIdWithLang(${patient.id})">${t('print_invoice', 'Print Invoice')}</button>
                        </div>
                        <button class="btn btn-warning" type="button" onclick="openCalendarView()">${t('open_calendar', 'Calendar')}</button>
                        <button class="btn btn-primary" type="button" onclick="showEditPatientModalById(${patient.id})">${t('edit_personal_data','Edit Info')}</button>
                    </div>
                    <div class="section-card">
                        <div class="section-card-title">${t('patient_info','Patient Information')}</div>
                        <div class="info-grid">
                            <div class="info-field"><label>${t('patient_name','Name')}</label><span>${patient.first_name} ${patient.last_name}</span></div>
                            <div class="info-field"><label>${t('phone','Phone')}</label><span>${patient.phone || '—'}</span></div>
                            ${profile.birth_date_display ? `<div class="info-field"><label>${t('date_of_birth','Date of Birth')}</label><span>${profile.birth_date_display}</span></div>` : ''}
                            ${patient.gender ? `<div class="info-field"><label>${t('gender','Gender')}</label><span>${patient.gender}</span></div>` : ''}
                            ${patient.address ? `<div class="info-field"><label>${t('address','Address')}</label><span>${patient.address}</span></div>` : ''}
                        </div>
                        ${patient.medical_history ? `<div style="margin-top:14px;"><div class="info-field"><label>${t('medical_history','Medical History')}</label><span style="display:block;white-space:pre-wrap;font-weight:400;line-height:1.6;">${patient.medical_history}</span></div></div>` : ''}
                        ${patient.notes ? `<div style="margin-top:10px;"><div class="info-field"><label>${t('notes','Notes')}</label><span style="display:block;white-space:pre-wrap;font-weight:400;line-height:1.6;">${patient.notes}</span></div></div>` : ''}
                    </div>
                </div>

                <div id="profile-tab-followups" class="profile-tab-content">
                    <section class="card odontogram-card" id="odontogram-card" style="display:none;">
                      <h3 data-i18n="odontogram">${t('odontogram','Tooth chart')}</h3>
                      <div id="odontogram-arch"></div>
                      <div class="tooth-legend" id="odontogram-legend"></div>
                    </section>
                    <details class="form-panel" open>
                        <summary>➕ ${t('add_entry','Add New Entry')}</summary>
                        <div class="form-panel-body">
                        <form id="patient-followup-form">
                            <div class="form-row">
                                <div class="form-group"><label>${t('date','Date')}</label>
                                    <input type="hidden" name="followup_date" id="followup-date">
                                    <div style="display:flex;gap:6px;">
                                        <select id="followup-date-day" style="flex:1;" onchange="syncDobHidden('followup-date-day','followup-date-month','followup-date-year','followup-date')"><option value="">Day</option></select>
                                        <select id="followup-date-month" style="flex:2;" onchange="syncDobHidden('followup-date-day','followup-date-month','followup-date-year','followup-date')"><option value="">Month</option></select>
                                        <select id="followup-date-year" style="flex:1.5;" onchange="syncDobHidden('followup-date-day','followup-date-month','followup-date-year','followup-date')"><option value="">Year</option></select>
                                    </div>
                                </div>
                                <div class="form-group">
                                    <label>${t('select_procedure','Select Procedure')}</label>
                                    <select name="procedure_id" id="followup-procedure-id">
                                        <option value="">${t('other','Other / Custom')}</option>
                                        ${treatmentProceduresCache.map(item => `<option value="${item.id}">${item.name}</option>`).join('')}
                                    </select>
                                </div>
                                <div class="form-group" id="followup-custom-procedure-wrap">
                                    <label>${t('custom_procedure_name','Procedure Name')}</label>
                                    <input type="text" name="treatment_procedure" id="followup-custom-procedure" placeholder="${t('custom_procedure_placeholder','Type procedure name')}">
                                </div>
                                <div class="form-group">
                                    <label>${t('tooth_no','Tooth No.')}</label>
                                    <input type="text" name="tooth_no" id="followup-tooth-no" placeholder="e.g. 16" maxlength="10" autocomplete="off">
                                </div>
                            </div>
                            <div class="form-row-3">
                                <div class="form-group"><label>${t('price','Price')} <small style="font-weight:400;color:var(--muted);">(${t('or_expression','or expression')})</small></label><input type="text" inputmode="decimal" name="price" id="followup-price" value="0" class="calc-input" data-calc-field="1" placeholder="0" autocomplete="off" required></div>
                                <div class="form-group"><label>${t('discount','Discount')} <small style="font-weight:400;color:var(--muted);">(${t('or_expression','or expression')}, ${t('or_percent','or % e.g. 20%')})</small></label><input type="text" inputmode="decimal" name="discount" id="followup-discount" value="0" class="calc-input" data-calc-field="1" data-percent-base="followup-price" placeholder="0" autocomplete="off"></div>
                                <div class="form-group"><label>${t('lab_expense','Lab Expense')} <small style="font-weight:400;color:var(--muted);">(${t('or_expression','or expression')})</small></label><input type="text" inputmode="decimal" name="lab_expense" id="followup-lab-expense" value="0" class="calc-input" data-calc-field="1" placeholder="0" autocomplete="off"></div>
                                <div class="form-group"><label>${t('payment','Payment')} <small style="font-weight:400;color:var(--muted);">(${t('or_expression','or expression')})</small></label><input type="text" inputmode="decimal" name="payment" id="followup-payment" value="0" class="calc-input" data-calc-field="1" placeholder="0" autocomplete="off" required></div>
                            </div>
                            <div class="form-group">
                                <label>${t('notes','Notes')}</label>
                                <textarea name="notes" placeholder="${t('optional_note','Optional note')}" style="min-height:60px;"></textarea>
                            </div>
                            <input type="hidden" name="requires_lab" id="followup-requires-lab" value="0">
                            <input type="hidden" name="patient_id" value="${patient.id}">
                            <button class="btn btn-primary" type="submit">${t('add_entry','Add Entry')}</button>
                        </form>
                        </div>
                    </details>
                    <div class="table-container">
                        <table>
                            <thead>
                                <tr>
                                    <th>${t('date','Date')}</th>
                                    <th>${t('treatment_procedure','Procedure')}</th>
                                    <th class="numeric-cell">${t('price','Price')}</th>
                                    <th class="numeric-cell">${t('discount','Discount')}</th>
                                    <th class="numeric-cell">${t('lab_expense','Lab')}</th>
                                    <th class="numeric-cell">${t('clinic_profit','Profit')}</th>
                                    <th class="numeric-cell">${t('payment','Payment')}</th>
                                    <th class="numeric-cell">${t('balance','Balance')}</th>
                                    <th>${t('notes','Notes')}</th>
                                    <th>${t('actions','Actions')}</th>
                                </tr>
                            </thead>
                            <tbody id="patient-followups-body">${renderFollowupsRows(followups)}</tbody>
                        </table>
                    </div>
                </div>

                <div id="profile-tab-images" class="profile-tab-content">
                    <details class="form-panel" open>
                        <summary>📤 ${t('upload_image','Upload Image')}</summary>
                        <div class="form-panel-body">
                        <form id="upload-image-form" enctype="multipart/form-data">
                            <input type="hidden" name="patient_id" value="${patient.id}">
                            <div class="form-row">
                                <div class="form-group"><label>${t('file','File')}</label><input type="file" name="image" accept="image/*" required></div>
                                <div class="form-group"><label>${t('notes','Notes')}</label><input type="text" name="notes" placeholder="${t('image_notes','Image notes')}"></div>
                            </div>
                            <button class="btn btn-primary" type="submit">${t('upload_image','Upload')}</button>
                        </form>
                        </div>
                    </details>
                    <div class="table-container" style="margin-top:12px;">
                        <table>
                            <thead><tr><th>${t('file','File')}</th><th>${t('uploaded','Uploaded')}</th><th>${t('notes','Notes')}</th></tr></thead>
                            <tbody>${profile.medical_images.map(img => `<tr><td>${img.file_name}</td><td>${img.uploaded_at}</td><td>${img.notes || ''}</td></tr>`).join('') || `<tr><td colspan="3">${t('no_data','No images yet')}</td></tr>`}</tbody>
                        </table>
                    </div>
                </div>
            `;
            document.getElementById('patient-profile-modal').classList.add('active');
            // Wire date pickers and calc inputs inside dynamically rendered modal
            const profileModal = document.getElementById('patient-profile-modal');
            attachDatePickerButtons(profileModal);
            wireCalcInputs(profileModal);
            // Add-entry date picker: day / month / year dropdowns, defaulting to today
            initDobDropdowns('followup-date-day', 'followup-date-month', 'followup-date-year');
            (function () {
                const now = new Date();
                const setVal = (id, v) => { const el = document.getElementById(id); if (el) el.value = v; };
                setVal('followup-date-day', String(now.getDate()).padStart(2, '0'));
                setVal('followup-date-month', String(now.getMonth() + 1).padStart(2, '0'));
                setVal('followup-date-year', String(now.getFullYear()));
                syncDobHidden('followup-date-day', 'followup-date-month', 'followup-date-year', 'followup-date');
            })();
            const followupProcedureSelect = document.getElementById('followup-procedure-id');
            if (followupProcedureSelect) {
                followupProcedureSelect.addEventListener('change', updateFollowupProcedureUi);
                updateFollowupProcedureUi();
            }
            document.getElementById('patient-followup-form').addEventListener('submit', async (e) => {
                e.preventDefault();
                const data = Object.fromEntries(new FormData(e.target));
                data.price_expr = calcExprOf(document.getElementById('followup-price'));
                data.discount_expr = calcExprOf(document.getElementById('followup-discount'));
                data.lab_expense_expr = calcExprOf(document.getElementById('followup-lab-expense'));
                data.payment_expr = calcExprOf(document.getElementById('followup-payment'));
                if (!data.followup_date) {
                    alert(t('date_required', 'Please pick a date (day, month, and year).'));
                    return;
                }
                if (!data.procedure_id && !String(data.treatment_procedure || '').trim()) {
                    alert(t('procedure_required', 'Please select a procedure or enter a custom procedure name.'));
                    return;
                }
                const response = await fetch(`/api/patients/${patient.id}/followups`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(data)
                });
                if (!response.ok) {
                    const payload = await response.json().catch(() => ({}));
                    alert(payload.error || t('unable_save_followup', 'Unable to save follow-up.'));
                    return;
                }
                await viewPatientProfile(patientId);
                const followupsBtn = document.querySelector('#patient-profile-modal .profile-tab:nth-child(2)');
                if (followupsBtn) switchProfileTab('followups', followupsBtn);
            });
            document.getElementById('upload-image-form').addEventListener('submit', async (e) => {
                e.preventDefault();
                const formData = new FormData(e.target);
                await fetch('/api/medical-images', {method:'POST', body: formData});
                await viewPatientProfile(patientId);
                const imagesBtn = document.querySelector('#patient-profile-modal .profile-tab:nth-child(3)');
                if (imagesBtn) switchProfileTab('images', imagesBtn);
            });
            // Render odontogram chart for this patient
            renderOdontogram(patientId);
        }

        function formatDateDisplay(dateStr) {
            if (!dateStr) return '';
            const parts = String(dateStr).substring(0, 10).split('-');
            if (parts.length === 3) return `${parts[2]}/${parts[1]}/${parts[0]}`;
            return dateStr;
        }

        function formatApptDate(dateStr) {
            if (!dateStr) return '';
            try {
                const d = new Date(String(dateStr).replace(' ', 'T'));
                if (isNaN(d.getTime())) return dateStr;
                const day = String(d.getDate()).padStart(2,'0');
                const mon = String(d.getMonth()+1).padStart(2,'0');
                const yr = d.getFullYear();
                const hr = String(d.getHours()).padStart(2,'0');
                const mn = String(d.getMinutes()).padStart(2,'0');
                return `${day}/${mon}/${yr} ${hr}:${mn}`;
            } catch(_) { return dateStr; }
        }

        // Show a verbatim expression ("20+20") when one was entered, otherwise the formatted amount.
        function fmtAmount(num, expr) {
            const n = parseFloat(num || 0) || 0;
            const e = String(expr || '').trim();
            return e ? `<span title="₪${n.toFixed(2)}">${e}</span>` : `₪${n.toFixed(2)}`;
        }

        // ── Odontogram helpers ──────────────────────────────────────────────────
        // FDI permanent dentition, clinician's view (patient's right on the left).
        const FDI_UPPER = ['18','17','16','15','14','13','12','11','21','22','23','24','25','26','27','28'];
        const FDI_LOWER = ['48','47','46','45','44','43','42','41','31','32','33','34','35','36','37','38'];

        // Tooth class by FDI position (2nd digit): 1-2 incisor, 3 canine, 4-5 premolar, 6-8 molar.
        function fdiToothClass(fdi) {
          const n = parseInt(fdi[1], 10);
          if (n <= 2) return 'incisor';
          if (n === 3) return 'canine';
          if (n <= 5) return 'premolar';
          return 'molar';
        }

        function isValidFdi(s) { return /^[1-4][1-8]$/.test(String(s || '')); }

        // Tooth silhouettes in a 40x56 cell (crown on top, root tapering down).
        // Distinct per class; refine visually in Task 9's review.
        const TOOTH_PATHS = {
          molar:    'M6,10 Q8,4 12,8 Q16,3 20,8 Q24,3 28,8 Q32,4 34,10 Q38,16 34,26 Q34,40 28,52 Q24,56 20,52 Q16,56 12,52 Q6,40 6,26 Q2,16 6,10 Z',
          premolar: 'M9,10 Q14,3 20,8 Q26,3 31,10 Q35,18 31,28 Q31,42 26,52 Q20,57 14,52 Q9,42 9,28 Q5,18 9,10 Z',
          canine:   'M20,3 Q27,9 30,18 Q33,30 28,44 Q24,56 20,53 Q16,56 12,44 Q7,30 10,18 Q13,9 20,3 Z',
          incisor:  'M11,5 Q20,2 29,5 Q33,14 30,26 Q29,42 24,52 Q20,57 16,52 Q11,42 10,26 Q7,14 11,5 Z',
        };

        // Build one row of teeth as inline SVG. `chart` is the {teeth:{}} map from the API.
        function buildToothRowSvg(fdiList, chart, isLower) {
          const cellW = 44, cellH = 64, pad = 4;
          let cells = '';
          fdiList.forEach((fdi, i) => {
            const x = i * cellW + pad;
            const entry = (chart.teeth || {})[fdi];
            const fill = entry && entry.color ? entry.color
                       : entry ? '#cbd5e1'          // legacy/unknown tint
                       : 'transparent';             // healthy = outline only
            const stroke = entry ? '#334155' : '#94a3b8';
            const dot = entry && entry.has_plan
              ? `<circle cx="${x+34}" cy="6" r="4" fill="#7c3aed"><title>${t('has_plan','Has plan')}</title></circle>` : '';
            const warn = entry && entry.unpaid_balance > 0
              ? `<circle cx="${x+34}" cy="${cellH-8}" r="4" fill="#f59e0b"><title>${t('unpaid','Unpaid')}: ₪ ${entry.unpaid_balance.toFixed(2)}</title></circle>` : '';
            const label = `<text x="${x+20}" y="${isLower ? cellH-1 : 10}" text-anchor="middle" class="tooth-num">${fdi}</text>`;
            const path = `<path d="${TOOTH_PATHS[fdiToothClass(fdi)]}" transform="translate(${x},${isLower ? 6 : 14}) ${isLower ? 'rotate(180 20 28)' : ''}" fill="${fill}" stroke="${stroke}" stroke-width="1.5"/>`;
            cells += `<g class="tooth" data-fdi="${fdi}" tabindex="0" role="button" aria-label="${t('tooth','Tooth')} ${fdi}">${path}${label}${dot}${warn}</g>`;
          });
          const w = fdiList.length * cellW + pad * 2;
          return `<svg viewBox="0 0 ${w} ${cellH}" width="100%" preserveAspectRatio="xMidYMid meet" class="tooth-row">${cells}</svg>`;
        }

        function buildToothArchSvg(chart) {
          return `<div class="arch arch-upper">${buildToothRowSvg(FDI_UPPER, chart, false)}</div>`
               + `<div class="arch arch-lower">${buildToothRowSvg(FDI_LOWER, chart, true)}</div>`;
        }

        let currentChartConditions = [];

        async function renderOdontogram(patientId) {
          const card = document.getElementById('odontogram-card');
          if (!card) return;
          try {
            const resp = await fetch(`/api/patients/${patientId}/tooth-chart`);
            const chart = await resp.json();
            currentChartConditions = chart.conditions || [];
            document.getElementById('odontogram-arch').innerHTML = buildToothArchSvg(chart);
            document.getElementById('odontogram-legend').innerHTML = (chart.conditions || [])
              .map(c => `<span><i style="background:${c.color}"></i>${(currentLanguage==='ar' && c.name_ar) ? c.name_ar : c.name}</span>`)
              .join('');
            card.style.display = '';
            document.querySelectorAll('#odontogram-arch .tooth').forEach(el => {
              el.addEventListener('click', () => openToothPopup(patientId, el.dataset.fdi, chart));
              el.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openToothPopup(patientId, el.dataset.fdi, chart); } });
            });
          } catch (e) {
            card.style.display = 'none';  // backend not present / older server — degrade silently
          }
        }

        function openFollowupFormPrefilledTooth(patientId, fdi) {
          // Switch to the followups tab
          const followupsBtn = document.querySelector('#patient-profile-modal .profile-tab:nth-child(2)');
          if (followupsBtn) switchProfileTab('followups', followupsBtn);
          // Pre-fill the tooth field
          const el = document.getElementById('followup-tooth-no');
          if (el) el.value = fdi;
          // Move focus to the procedure picker
          const proc = document.getElementById('followup-procedure-id');
          if (proc) proc.focus();
        }
        async function addToothToPlan(patientId, fdi) {
          const plans = (await (await fetch('/api/treatment-plans')).json())
            .filter(p => p.patient_id === patientId);
          let choice = '';
          if (plans.length) {
            const menu = plans.map((p, i) => `${i + 1}. ${p.plan_name} [${(p.teeth || []).join(', ')}]`).join('\\n');
            choice = prompt(`${t('add_to_plan','+ Add to plan')} — ${t('tooth','Tooth')} ${fdi}\n\n${menu}\n\n${t('plan_pick_hint','Enter a number, or a new plan name:')}`);
          } else {
            choice = prompt(`${t('plan_new_name','New plan name:')}`, `${t('plan','Plan')} ${fdi}`);
          }
          if (!choice) return;

          const asIndex = parseInt(choice, 10);
          if (plans.length && asIndex >= 1 && asIndex <= plans.length && String(asIndex) === choice.trim()) {
            const plan = plans[asIndex - 1];
            const teeth = Array.from(new Set([...(plan.teeth || []), fdi]));
            await fetch(`/api/treatment-plans/${plan.id}`, {
              method: 'PUT', headers: {'Content-Type': 'application/json'},
              body: JSON.stringify({ plan_name: plan.plan_name, goals: plan.goals, estimated_cost: plan.estimated_cost,
                                     status: plan.status, start_date: plan.start_date, end_date: plan.end_date,
                                     notes: plan.notes, teeth }),
            });
          } else {
            await fetch('/api/treatment-plans', {
              method: 'POST', headers: {'Content-Type': 'application/json'},
              body: JSON.stringify({ patient_id: patientId, plan_name: choice.trim(), teeth: [fdi] }),
            });
          }
          renderOdontogram(patientId);
          if (typeof renderTreatmentPlans === 'function') renderTreatmentPlans(patientId);  // refresh plans tab if present
        }

        let _popupPatientId = null, _popupFdi = null;

        function openToothPopup(patientId, fdi, chart) {
          _popupPatientId = patientId; _popupFdi = fdi;
          const entry = (chart.teeth || {})[fdi] || {};
          document.getElementById('tooth-popup-title').textContent = `${t('tooth','Tooth')} ${fdi}`;
          const sel = document.getElementById('tooth-popup-condition');
          // First option = Healthy/clear (sends null).
          sel.innerHTML = `<option value="">${t('healthy','Healthy')}</option>` +
            currentChartConditions
              .filter(c => c.name !== 'Healthy')
              .map(c => `<option value="${c.id}">${(currentLanguage==='ar' && c.name_ar) ? c.name_ar : c.name}</option>`)
              .join('');
          sel.value = entry.condition_id ? String(entry.condition_id) : '';
          document.getElementById('tooth-popup-note').value = entry.note || '';
          document.getElementById('tooth-popup').style.display = 'flex';
        }

        function closeToothPopup() { document.getElementById('tooth-popup').style.display = 'none'; }

        document.getElementById('tooth-popup-close').addEventListener('click', closeToothPopup);

        document.getElementById('tooth-popup-save').addEventListener('click', async () => {
          const condVal = document.getElementById('tooth-popup-condition').value;
          await fetch(`/api/patients/${_popupPatientId}/tooth-chart`, {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
              tooth_no: _popupFdi,
              condition_id: condVal ? parseInt(condVal, 10) : null,   // '' → null = clear to healthy
              note: document.getElementById('tooth-popup-note').value || null,
            }),
          });
          closeToothPopup();
          renderOdontogram(_popupPatientId);
        });

        document.getElementById('tooth-popup-log').addEventListener('click', () => {
          closeToothPopup();
          openFollowupFormPrefilledTooth(_popupPatientId, _popupFdi);   // Task 5
        });

        document.getElementById('tooth-popup-plan').addEventListener('click', () => {
          closeToothPopup();
          addToothToPlan(_popupPatientId, _popupFdi);                    // Task 6
        });

        function renderFollowupsRows(followups) {
            if (!followups || !followups.length) {
                return `<tr><td colspan="10">${t('no_entries_yet', 'No entries yet')}</td></tr>`;
            }
            return followups.map(item => `
                <tr>
                    <td>${formatDateDisplay(item.followup_date) || ''}</td>
                    <td>${item.treatment_procedure || t('no_data', 'No data')}${item.tooth_no ? ` <small style="opacity:0.7;">#${item.tooth_no}</small>` : ''}</td>
                    <td class="numeric-cell">${fmtAmount(item.price, item.price_expr)}</td>
                    <td class="numeric-cell">${(parseFloat(item.discount || 0) > 0 || item.discount_expr) ? fmtAmount(item.discount, item.discount_expr) : '—'}</td>
                    <td class="numeric-cell">${fmtAmount(item.lab_expense, item.lab_expense_expr)}</td>
                    <td class="numeric-cell">₪${(parseFloat(item.price || 0) - parseFloat(item.discount || 0) - parseFloat(item.lab_expense || 0)).toFixed(2)}</td>
                    <td class="numeric-cell">${fmtAmount(item.payment, item.payment_expr)}</td>
                    <td class="numeric-cell">₪${parseFloat(item.remaining_amount || 0).toFixed(2)}</td>
                    <td>${item.notes || ''}</td>
                    <td>
                        <button class="btn btn-warning btn-icon" onclick="deleteFollowup(${item.patient_id},${item.id})">🗑</button>
                        <button class="btn btn-primary btn-icon" onclick="editFollowupById(${item.patient_id},${item.id})">✏</button>
                    </td>
                </tr>
            `).join('');
        }

        async function deleteFollowup(patientId, followupId) {
            if (!confirm(t('confirm_delete', 'Are you sure you want to delete?'))) return;
            const resp = await fetch(`/api/patients/${patientId}/followups/${followupId}`, {method:'DELETE'});
            if (!resp.ok) {
                alert('Delete failed');
                return;
            }
            viewPatientProfile(patientId);
        }

        let currentEditFollowup = null;
        function editFollowup(item) {
            currentEditFollowup = item;
            document.getElementById('ef-patient-id').value = item.patient_id || '';
            document.getElementById('ef-followup-id').value = item.id || '';
            document.getElementById('ef-date').value = formatDateDisplay(item.followup_date) || '';
            document.getElementById('ef-procedure').value = item.treatment_procedure || '';
            document.getElementById('ef-tooth-no').value = item.tooth_no || '';
            const setAmt = (id, num, expr) => {
                const el = document.getElementById(id);
                if (!el) return;
                if (expr) { el.value = String(expr); el.dataset.expr = String(expr); }
                else { el.value = parseFloat(num || 0).toFixed(2); delete el.dataset.expr; }
            };
            setAmt('ef-price', item.price, item.price_expr);
            setAmt('ef-discount', item.discount, item.discount_expr);
            setAmt('ef-lab-expense', item.lab_expense, item.lab_expense_expr);
            setAmt('ef-payment', item.payment, item.payment_expr);
            document.getElementById('ef-notes').value = item.notes || '';
            // Close the patient profile window first, then open the edit window on its own.
            closeModal('patient-profile-modal');
            const editModal = document.getElementById('edit-followup-modal');
            attachDatePickerButtons(editModal);
            wireCalcInputs(editModal);
            editModal.classList.add('active');
        }

        function editFollowupById(patientId, followupId) {
            const list = followupsCache[patientId] || [];
            const item = list.find(f => Number(f.id) === Number(followupId));
            if (!item) { alert(t('no_entry_found', 'Entry not found')); return; }
            editFollowup(item);
        }

        // Close the edit-entry window and return to the patient profile.
        function closeEditFollowup() {
            closeModal('edit-followup-modal');
            const pid = parseInt(document.getElementById('ef-patient-id')?.value || '', 10);
            if (pid) { viewPatientProfile(pid); }
        }

        function showEditPatientModal(patientId, patient) {
            // Close the profile preview first so we have a clean single modal
            closeModal('patient-profile-modal');
            document.getElementById('edit-patient-id').value = patientId;
            document.getElementById('edit-first-name').value = patient.first_name || '';
            document.getElementById('edit-last-name').value = patient.last_name || '';
            document.getElementById('edit-phone').value = patient.phone || '';
            document.getElementById('edit-gender').value = patient.gender || '';
            document.getElementById('edit-address').value = patient.address || '';
            document.getElementById('edit-notes').value = patient.notes || '';
            // Populate DOB dropdowns (same pattern as add-patient form)
            initDobDropdowns('edit-dob-day', 'edit-dob-month', 'edit-dob-year');
            const dob = patient.date_of_birth ? String(patient.date_of_birth).substring(0, 10) : '';
            if (dob && /^\\d{4}-\\d{2}-\\d{2}$/.test(dob)) {
                const [yr, mo, dy] = dob.split('-');
                document.getElementById('edit-dob-day').value = dy;
                document.getElementById('edit-dob-month').value = mo;
                document.getElementById('edit-dob-year').value = yr;
                syncDobHidden('edit-dob-day', 'edit-dob-month', 'edit-dob-year', 'edit-dob');
            } else {
                document.getElementById('edit-dob-day').value = '';
                document.getElementById('edit-dob-month').value = '';
                document.getElementById('edit-dob-year').value = '';
                document.getElementById('edit-dob').value = '';
            }
            document.getElementById('edit-patient-modal').classList.add('active');
        }

        function showEditPatientModalById(patientId) {
            const patient = patientProfileCache[patientId];
            if (!patient) { alert('Patient data not loaded'); return; }
            showEditPatientModal(patientId, patient);
        }

        document.addEventListener('DOMContentLoaded', function() {
            const editForm = document.getElementById('edit-patient-form');
            if (editForm) {
                editForm.addEventListener('submit', async function(e) {
                    e.preventDefault();
                    const data = Object.fromEntries(new FormData(e.target));
                    const patientId = data.patient_id;
                    delete data.patient_id;
                    const resp = await fetch(`/api/patients/${patientId}`, {
                        method: 'PUT',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify(data)
                    });
                    if (resp.ok) {
                        closeModal('edit-patient-modal');
                        viewPatientProfile(parseInt(patientId));
                        loadPatients();
                    } else {
                        alert(t('save_failed', 'Save failed'));
                    }
                });
            }
            const editFollowupForm = document.getElementById('edit-followup-form');
            if (editFollowupForm) {
                editFollowupForm.addEventListener('submit', async function(e) {
                    e.preventDefault();
                    const patientId = document.getElementById('ef-patient-id').value;
                    const followupId = document.getElementById('ef-followup-id').value;
                    const payload = {
                        ...currentEditFollowup,
                        followup_date: document.getElementById('ef-date').value,
                        treatment_procedure: document.getElementById('ef-procedure').value,
                        tooth_no: document.getElementById('ef-tooth-no').value,
                        price: parseCurrency(document.getElementById('ef-price').value || 0),
                        discount: parseCurrency(document.getElementById('ef-discount').value || 0),
                        lab_expense: parseCurrency(document.getElementById('ef-lab-expense').value || 0),
                        payment: parseCurrency(document.getElementById('ef-payment').value || 0),
                        price_expr: calcExprOf(document.getElementById('ef-price')),
                        discount_expr: calcExprOf(document.getElementById('ef-discount')),
                        lab_expense_expr: calcExprOf(document.getElementById('ef-lab-expense')),
                        payment_expr: calcExprOf(document.getElementById('ef-payment')),
                        notes: document.getElementById('ef-notes').value
                    };
                    const resp = await fetch(`/api/patients/${patientId}/followups/${followupId}`, {
                        method: 'PUT',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify(payload)
                    });
                    if (resp.ok) {
                        closeModal('edit-followup-modal');
                        viewPatientProfile(parseInt(patientId));
                    } else {
                        alert(t('save_failed', 'Save failed'));
                    }
                });
            }
        });

        async function openAppointmentFromProfile(patientId) {
            closeModal('patient-profile-modal');
            switchTab('appointments');
            await showAddAppointmentModal(patientId);
        }
        
        // Form submissions
        async function checkAddPatientDuplicate() {
            const fn   = (document.getElementById('ap-first-name')?.value || '').trim();
            const ln   = (document.getElementById('ap-last-name')?.value  || '').trim();
            const ph   = (document.getElementById('ap-phone')?.value      || '').trim();
            const warn = document.getElementById('add-patient-dup-warning');
            if (!warn) return;
            if (!fn && !ln && !ph) { warn.style.display = 'none'; return; }
            try {
                const params = new URLSearchParams();
                if (fn) params.set('first_name', fn);
                if (ln) params.set('last_name', ln);
                if (ph) params.set('phone', ph);
                const r = await fetch('/api/patients/check-duplicate?' + params.toString());
                if (!r.ok) { warn.style.display = 'none'; return; }
                const data = await r.json();
                const esc = s => String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
                const msgs = [];
                if (data.name_matches && data.name_matches.length > 0) {
                    const names = data.name_matches.map(p => esc(p.first_name + ' ' + p.last_name)).join(', ');
                    msgs.push(t('dup_name_warning','⚠️ A patient with this name already exists:') + ' <strong>' + names + '</strong>');
                }
                if (data.phone_matches && data.phone_matches.length > 0) {
                    const names = data.phone_matches.map(p => esc(p.first_name + ' ' + p.last_name)).join(', ');
                    msgs.push(t('dup_phone_warning','⚠️ This phone number is registered to:') + ' <strong>' + names + '</strong>');
                }
                if (msgs.length > 0) {
                    warn.innerHTML = msgs.join('<br>') + '<br><small style="opacity:0.8">' + t('dup_proceed','You can still add the patient.') + '</small>';
                    warn.style.display = 'block';
                } else {
                    warn.style.display = 'none';
                }
            } catch(_) { warn.style.display = 'none'; }
        }

        document.getElementById('add-patient-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            const formData = new FormData(e.target);
            const data = Object.fromEntries(formData);
            const resp = await fetch('/api/patients', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(data)
            });
            if (!resp.ok) {
                const err = await resp.json().catch(() => ({}));
                alert(err.error || t('save_failed', 'Save failed'));
                return;
            }
            closeModal('add-patient-modal');
            e.target.reset();
            const w = document.getElementById('add-patient-dup-warning');
            if (w) w.style.display = 'none';
            loadPatients();
        });

        ['ap-first-name','ap-last-name','ap-phone'].forEach(id => {
            const el = document.getElementById(id);
            if (el) el.addEventListener('blur', checkAddPatientDuplicate);
        });
        
        document.getElementById('add-appointment-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            const form = e.target;
            const formData = Object.fromEntries(new FormData(form));
            // clear previous inline errors
            form.querySelectorAll('.field-error').forEach(el => el.textContent = '');

            let hasError = false;
            const setErr = (field, msg) => {
                const el = form.querySelector(`.field-error[data-for="${field}"]`);
                if (el) el.textContent = msg;
                hasError = true;
            };

            if (!safeDisplayText(formData.patient_id, '')) {
                setErr('patient_id', t('patient_required', 'Patient is required.'));
            }
            if (!safeDisplayText(formData.appointment_date, '')) {
                setErr('appointment_date', t('appointment_date_required', 'Appointment Date *'));
            } else if (!hasDateAndTimeValue(formData.appointment_date)) {
                setErr('appointment_date', t('appointment_time_required', 'Appointment Time *'));
            }
            if (formData.appointment_date && isFridayDateTimeValue(formData.appointment_date)) {
                setErr('appointment_date', 'Friday is a permanent holiday.');
            }

            if (hasError) {
                const first = form.querySelector('.field-error:not(:empty)');
                if (first) first.scrollIntoView({behavior: 'smooth', block: 'center'});
                return;
            }

            const submitBtn = document.getElementById('add-appointment-submit');
            const toast = document.getElementById('add-appointment-toast');
            if (submitBtn) submitBtn.disabled = true;
            if (toast) { toast.style.display = 'none'; toast.className = 'toast'; }

            try {
                const response = await fetch('/api/appointments', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(formData)
                });
                const payload = await response.json().catch(() => ({}));
                if (!response.ok) {
                    const msg = payload.error || t('unable_schedule_appointment', 'Unable to schedule appointment.');
                    if (toast) { toast.textContent = msg; toast.classList.add('error'); toast.style.display = 'block'; }
                    if (submitBtn) submitBtn.disabled = false;
                    return;
                }

                // success
                if (toast) { toast.textContent = t('appointment_saved', 'Appointment saved'); toast.classList.add('success'); toast.style.display = 'block'; }
                // reset and close after a short delay so user sees success
                setTimeout(() => {
                    closeModal('add-appointment-modal');
                }, 900);
                form.reset();
                // refresh calendar and lists
                await loadAppointments();
                await loadDashboard();
            } catch (err) {
                if (toast) { toast.textContent = t('save_failed', 'Save failed'); toast.classList.add('error'); toast.style.display = 'block'; }
            } finally {
                if (submitBtn) submitBtn.disabled = false;
            }
        });

        document.getElementById('add-appointment-clear').addEventListener('click', () => {
            const form = document.getElementById('add-appointment-form');
            form.reset();
            form.querySelectorAll('.field-error').forEach(el => el.textContent = '');
            const toast = document.getElementById('add-appointment-toast');
            if (toast) { toast.style.display = 'none'; toast.className = 'toast'; }
            const statusSel = document.getElementById('appointment-status-select');
            if (statusSel) statusSel.value = 'scheduled';
            const durInput = document.getElementById('appointment-duration-input');
            if (durInput) durInput.value = '30';
            const dateInput = document.getElementById('appointment-date-input');
            if (dateInput) {
                const d = new Date(Date.now() + 3600000);
                if (d.getDay() === 5) d.setDate(d.getDate() + 1);
                dateInput.value = toDatetimeLocalValue(d);
            }
        });

        document.getElementById('expense-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            const data = Object.fromEntries(new FormData(e.target));
            const response = await fetch('/api/expenses', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(data)
            });
            if (!response.ok) {
                alert(t('unable_add_expense', 'Unable to add expense.'));
                return;
            }
            e.target.reset();
            const expenseDateInput = document.getElementById('expense-date');
            if (expenseDateInput) {
                const today = new Date();
                const day = String(today.getDate()).padStart(2, '0');
                const month = String(today.getMonth() + 1).padStart(2, '0');
                const year = today.getFullYear();
                expenseDateInput.value = `${day}/${month}/${year}`;
            }
            loadExpenses();
            loadReports();
            loadDashboard();
        });

        const billingForm = document.getElementById('billing-form');
        if (billingForm) {
            billingForm.addEventListener('submit', async (e) => {
                e.preventDefault();
                const data = Object.fromEntries(new FormData(e.target));
                // Capture verbatim expressions (e.g. "20+20") before they're resolved to numbers.
                data.subtotal_expr = calcExprOf(e.target.querySelector('[name="subtotal"]'));
                data.discount_expr = calcExprOf(e.target.querySelector('[name="discount"]'));
                data.paid_amount_expr = calcExprOf(e.target.querySelector('[name="paid_amount"]'));
                // Resolve any arithmetic expressions in numeric fields
                ['subtotal', 'discount', 'credit_used', 'paid_amount'].forEach(field => {
                    if (data[field] !== undefined) data[field] = parseCurrency(data[field]);
                });
                const response = await fetch('/api/billing', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(data)
                });

                if (!response.ok) {
                    const payload = await response.json().catch(() => ({}));
                    alert(payload.error || t('unable_add_billing', 'Unable to create invoice.'));
                    return;
                }

                e.target.reset();
                const billingDateInput = document.getElementById('billing-date');
                if (billingDateInput) {
                    const today = new Date();
                    const day = String(today.getDate()).padStart(2, '0');
                    const month = String(today.getMonth() + 1).padStart(2, '0');
                    const year = today.getFullYear();
                    billingDateInput.value = `${day}/${month}/${year}`;
                }
                loadBilling();
                loadReceivables();
                loadAuditLogs();
            });
        }

        const procedureForm = document.getElementById('procedure-form');
        if (procedureForm) {
            procedureForm.addEventListener('submit', async (e) => {
                e.preventDefault();
                const idValue = (document.getElementById('procedure-id')?.value || '').trim();
                const payload = {
                    name: (document.getElementById('procedure-name')?.value || '').trim(),
                    default_price: parseCurrency(document.getElementById('procedure-default-price')?.value || 0),
                    default_lab_expense: parseCurrency(document.getElementById('procedure-default-lab-expense')?.value || 0),
                    requires_lab: document.getElementById('procedure-requires-lab')?.checked ? 1 : 0,
                    active: document.getElementById('procedure-active')?.checked ? 1 : 0,
                };

                const isEdit = Boolean(idValue);
                const url = isEdit ? `/api/treatment-procedures/${idValue}` : '/api/treatment-procedures';
                const method = isEdit ? 'PUT' : 'POST';
                const response = await fetch(url, {
                    method,
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(payload)
                });

                if (!response.ok) {
                    const payloadError = await response.json().catch(() => ({}));
                    alert(payloadError.error || t('unable_save_procedure', 'Unable to save procedure.'));
                    return;
                }

                resetProcedureForm();
                await loadProcedureCatalog();
                await loadTreatmentProcedures();
                alert(t('procedure_saved', 'Procedure saved successfully.'));
            });
        }

        const holidayForm = document.getElementById('holiday-form');
        if (holidayForm) {
            holidayForm.addEventListener('submit', async (e) => {
                e.preventDefault();
                const data = Object.fromEntries(new FormData(e.target));
                const response = await fetch('/api/holidays', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(data)
                });
                if (!response.ok) {
                    alert(t('unable_add_holiday', 'Unable to add holiday.'));
                    return;
                }
                e.target.reset();
                await loadAppointments();
            });
        }

        const languageToggleBtn = document.getElementById('language-toggle');
        if (languageToggleBtn) {
            languageToggleBtn.addEventListener('click', toggleLanguage);
        }

        const themeToggleBtn = document.getElementById('theme-toggle');
        if (themeToggleBtn) {
            themeToggleBtn.addEventListener('click', toggleTheme);
        }

        // Delete functions
        async function deletePatient(id) {
            if (!confirm(t('confirm_delete_patient', 'Are you sure you want to delete this patient?'))) return;
            const resp = await fetch(`/api/patients/${id}`, {method: 'DELETE'});
            if (!resp.ok) {
                const p = await resp.json().catch(() => ({}));
                alert(p.error || 'Delete failed');
                return;
            }
            loadPatients();
        }
        
        async function updateAppointmentStatus(id, status) {
            await fetch(`/api/appointments/${id}/status`, {
                method: 'PUT',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({status})
            });
            loadAppointments();
            loadDashboard();
        }

        async function startVisitFromAppointment(appointmentId) {
            const response = await fetch(`/api/visits/from-appointment/${appointmentId}`, {
                method: 'POST'
            });
            if (!response.ok) {
                const payload = await response.json().catch(() => ({}));
                alert(payload.message || payload.error || t('unable_start_visit', 'Unable to start visit.'));
                return;
            }
            alert(t('visit_started', 'Visit started from appointment successfully.'));
            loadAppointments();
            loadDashboard();
        }

        // ── Math expression evaluator for price fields ──────────────────────────
        function evalArithmeticExpr(expr) {
            const cleaned = String(expr || '').trim();
            if (!cleaned) return null;
            if (!/^[0-9\\s+\\-*/(). ]+$/.test(cleaned)) return null;
            if (/(\\*\\*|\\/\\/)/.test(cleaned)) return null;
            try {
                // eslint-disable-next-line no-new-func
                const result = Function('"use strict"; return (' + cleaned + ')')();
                if (typeof result !== 'number' || !isFinite(result) || isNaN(result)) return null;
                return Math.max(0, result);
            } catch (_) {
                return null;
            }
        }

        function parsePercent(raw) {
            const s = String(raw || '').trim();
            if ((s.match(/%/g) || []).length !== 1) return null;
            if (!s.startsWith('%') && !s.endsWith('%')) return null;
            const core = s.replace('%', '').trim();
            if (!/^\\d+(\\.\\d+)?$/.test(core)) return null;
            return parseFloat(core);
        }

        function formatPercent(pct) {
            return String(pct) + '%';   // parseFloat already trimmed trailing zeros
        }

        function evalCalcField(el) {
            const raw = el.value.trim();
            if (!raw) { delete el.dataset.expr; return; }
            if (/^[\\d]*\\.?[\\d]*$/.test(raw)) {
                const n = parseFloat(raw);
                if (!isNaN(n)) {
                    el.value = n.toFixed(2);
                    delete el.dataset.expr;   // a plain number — nothing to preserve
                    el.classList.remove('calc-error');
                    el.classList.add('calc-ok');
                    setTimeout(() => el.classList.remove('calc-ok'), 1200);
                }
                return;
            }
            const pct = parsePercent(raw);
            if (pct !== null) {
                const baseEl = el.dataset.percentBase ? document.getElementById(el.dataset.percentBase) : null;
                if (!baseEl) {
                    // Percent only means something against a base (discount fields only).
                    el.classList.add('calc-error');
                    el.classList.remove('calc-ok');
                    return;
                }
                const base = parseCurrency(baseEl.value);
                const amount = Math.max(0, base * pct / 100);
                el.value = amount.toFixed(2);
                el.dataset.expr = formatPercent(pct);   // normalized "20%" for sheet / invoice
                el.classList.remove('calc-error');
                el.classList.add('calc-ok');
                setTimeout(() => el.classList.remove('calc-ok'), 1200);
                return;
            }
            const result = evalArithmeticExpr(raw);
            if (result !== null) {
                // Keep the verbatim expression so it can be shown on the invoice / sheet.
                el.dataset.expr = raw;
                el.value = result.toFixed(2);
                el.classList.remove('calc-error');
                el.classList.add('calc-ok');
                setTimeout(() => el.classList.remove('calc-ok'), 1200);
            } else {
                el.classList.add('calc-error');
                el.classList.remove('calc-ok');
            }
        }

        // Read the verbatim expression a calc field captured (set by evalCalcField on blur/Enter),
        // re-deriving it from the live value if needed (covers Enter-then-submit timing).
        function calcExprOf(el) {
            if (!el) return '';
            const raw = String(el.value || '').trim();
            if (raw && !/^-?[\\d]*\\.?[\\d]*$/.test(raw)) return raw;   // user left an un-evaluated expression
            return el.dataset.expr || '';
        }

        function wireCalcInputs(root) {
            root = root || document;
            root.querySelectorAll('[data-calc-field="1"]').forEach(el => {
                if (el.dataset.calcWired) return;
                el.dataset.calcWired = '1';
                el.addEventListener('blur', () => evalCalcField(el));
                el.addEventListener('keydown', e => {
                    if (e.key === 'Enter') {
                        e.preventDefault();
                        evalCalcField(el);
                        const form = el.closest('form');
                        if (form) {
                            const fields = Array.from(form.querySelectorAll('input:not([type=hidden]),select,textarea,button'));
                            const idx = fields.indexOf(el);
                            if (idx >= 0 && idx < fields.length - 1) fields[idx + 1].focus();
                        }
                    }
                });
            });
        }

        document.addEventListener('DOMContentLoaded', () => wireCalcInputs(document));

        // ── Universal date-picker button wiring ─────────────────────────────────
        function attachDatePickerButtons(root) {
            root = root || document;
            root.querySelectorAll('[data-date-field="1"]').forEach(input => {
                if (input.dataset.pickerAttached) return;
                input.dataset.pickerAttached = '1';

                const wrap = input.closest('.date-input-wrap');
                if (wrap) {
                    const btn = wrap.querySelector('.date-picker-btn');
                    if (btn && !btn.dataset.pickerWired) {
                        btn.dataset.pickerWired = '1';
                        const showPicker = () => showCalendarPickerModal(dateStr => { input.value = dateStr; });
                        btn.addEventListener('click', showPicker);
                        input.addEventListener('click', showPicker);
                    }
                    return;
                }

                const wrapper = document.createElement('div');
                wrapper.className = 'date-input-wrap';
                input.parentNode.insertBefore(wrapper, input);
                wrapper.appendChild(input);

                const btn = document.createElement('button');
                btn.type = 'button';
                btn.className = 'date-picker-btn';
                btn.title = 'Pick date';
                btn.setAttribute('aria-label', 'Pick date');
                btn.textContent = '📅';
                btn.dataset.pickerWired = '1';
                const showPickerDynamic = () => showCalendarPickerModal(dateStr => { input.value = dateStr; });
                btn.addEventListener('click', showPickerDynamic);
                input.addEventListener('click', showPickerDynamic);
                wrapper.appendChild(btn);
            });
        }

        document.addEventListener('DOMContentLoaded', () => attachDatePickerButtons(document));

        // ── Global form-submit interceptor: resolve any unevaluated calc fields ─
        document.addEventListener('submit', function(e) {
            const form = e.target;
            if (!form || form.tagName !== 'FORM') return;
            form.querySelectorAll('[data-calc-field="1"]').forEach(el => {
                const raw = el.value.trim();
                if (raw && !/^[\\d]*\\.?[\\d]*$/.test(raw)) {
                    evalCalcField(el);
                }
            });
        }, true);

        // ── Catalog tab (Procedure Catalog) ──
        function switchCatalogSubTab(tabName, clickedBtn, loadData = true) {
            if (loadData) loadProcedureCatalog();
        }

        function switchAdminSubTab(tabName, clickedBtn) {
            switchCatalogSubTab(tabName, clickedBtn);
        }

        // ── Appointments tab sub-tab switcher (List / Calendar) ────────────────
        function switchAppointmentsSubTab(tabName, clickedBtn) {
            const container = document.getElementById('appointments');
            if (!container) return;

            container.querySelectorAll('#appointments-sub-tabs .sub-tab').forEach(btn => btn.classList.remove('active'));
            if (clickedBtn) {
                clickedBtn.classList.add('active');
            } else {
                const fallback = container.querySelector(`#appt-tab-btn-${tabName}`);
                if (fallback) fallback.classList.add('active');
            }

            container.querySelectorAll('.sub-tab-content[id^="appointments-subtab-"]').forEach(panel => panel.classList.remove('active'));
            const activePanel = document.getElementById(`appointments-subtab-${tabName}`);
            if (activePanel) activePanel.classList.add('active');

            if (tabName === 'calendar') {
                renderAppointmentsCalendar(appointmentsCache);
                attachDatePickerButtons(container);
            }
        }

        // Initial content
        loadSupportSection();
        loadTreatmentProcedures();
        const expenseDateInput = document.getElementById('expense-date');
        const billingDateInput = document.getElementById('billing-date');
        const today = new Date();
        const day = String(today.getDate()).padStart(2, '0');
        const month = String(today.getMonth() + 1).padStart(2, '0');
        const year = today.getFullYear();
        const todayStr = `${day}/${month}/${year}`;
        if (expenseDateInput) expenseDateInput.value = todayStr;
        if (billingDateInput) billingDateInput.value = todayStr;
        applyTheme();
        applyLanguage();

        // Load dashboard on page load
        loadDashboard();

        // License gate functions
        async function applyLicenseGate() {
            try {
                const res = await fetch('/api/license/gate');
                const g = await res.json();
                const state = g.state || 'active';
                const overlay = document.getElementById('license-gate-overlay');
                const renew = document.getElementById('license-renew-banner');
                const vo = document.getElementById('license-viewonly-banner');
                document.body.classList.toggle('view-only', state === 'view_only');
                overlay.classList.toggle('hidden', state !== 'unlicensed');
                vo.classList.toggle('hidden', state !== 'view_only');
                if (state === 'grace') {
                    document.getElementById('license-renew-text').textContent =
                        'Subscription expired — in grace period until ' + (g.grace_until || '') + '. Renew to avoid interruption.';
                    renew.classList.remove('hidden');
                } else {
                    renew.classList.add('hidden');
                }
            } catch (e) { /* offline: leave the app usable, never gate on a fetch error */ }
        }
        function openLicenseActivation() {
            document.getElementById('license-gate-overlay').classList.remove('hidden');
        }
        function dismissRenewBanner() {
            document.getElementById('license-renew-banner').classList.add('hidden');
        }
        async function submitLicenseActivation() {
            const token = (document.getElementById('license-gate-token').value || '').trim();
            const status = document.getElementById('license-gate-status');
            if (!token) { status.textContent = 'Please paste your serial token.'; return; }
            status.textContent = 'Activating...';
            try {
                const res = await fetch('/api/license/activate', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ serial_token: token })
                });
                const body = await res.json();
                if (!res.ok) { status.textContent = body.error || 'Activation failed.'; return; }
                window.__activeSerial = (body.serial_number || '');
                showCloudLinkPanel();
            } catch (e) { status.textContent = 'Network error during activation.'; }
        }
        function showCloudLinkPanel() {
            document.querySelector('#license-gate-overlay h2').classList.add('hidden');
            document.getElementById('license-gate-token').classList.add('hidden');
            document.getElementById('license-gate-status').textContent = '';
            document.getElementById('license-link-panel').classList.remove('hidden');
        }
        async function linkCloud() {
            const status = document.getElementById('license-link-status');
            status.textContent = 'Linking...';
            try {
                const res = await fetch('/api/onboarding/state');
                const st = await res.json();
                const serial = st.serial_number || (window.__activeSerial || '');
                const res2 = await fetch('/api/cloud/pair', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ serial_number: serial })
                });
                const body = await res2.json();
                if (!res2.ok) { status.textContent = body.error || 'Could not reach the cloud — you can enable backup later in Settings.'; return; }
                window.location.reload();
            } catch (e) { status.textContent = 'Could not reach the cloud — you can enable backup later in Settings.'; }
        }
        async function skipCloudLink() {
            try {
                await fetch('/api/onboarding/dismiss-cloud-link', { method: 'POST' });
            } catch (e) { /* best-effort */ }
            window.location.reload();
        }
        document.addEventListener('DOMContentLoaded', applyLicenseGate);
    </script>

    <!-- Doctor name edit popover: direct body child to escape backdrop-filter containment -->
    <div class="doctor-edit-popover" id="doctor-edit-popover" onclick="event.stopPropagation()">
        <div class="doctor-edit-popover-title" data-i18n="edit_doctor_name">Edit Doctor Name</div>
        <div class="doctor-edit-field">
            <label>English</label>
            <input type="text" id="doctor-name-en-input" placeholder="Dr. First Last">
        </div>
        <div class="doctor-edit-field">
            <label>العربية</label>
            <input type="text" id="doctor-name-ar-input" dir="rtl" placeholder="د. الاسم">
        </div>
        <div class="doctor-edit-actions">
            <button class="doctor-edit-save" onclick="saveDoctorName()" data-i18n="save">Save</button>
            <button class="doctor-edit-cancel" onclick="toggleDoctorEditPopover()" data-i18n="cancel">Cancel</button>
        </div>
    </div>
</body>
</html>
'''

MOBILE_PORTAL_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Clinic Mobile Downloads</title>
    <style>
        :root {
            --bg-1: #f1f7f8;
            --bg-2: #e7f0ff;
            --panel: #ffffff;
            --line: #dbe4ef;
            --text: #11243a;
            --brand: #0f6d7b;
            --brand-2: #1d7fb7;
            --muted: #627386;
        }
        * { box-sizing: border-box; }
        body {
            margin: 0;
            font-family: 'Segoe UI', Tahoma, sans-serif;
            color: var(--text);
            background:
                radial-gradient(1200px 500px at 100% -30%, #cfe7ff 0%, transparent 60%),
                radial-gradient(1000px 500px at -10% 0%, #cff3ec 0%, transparent 58%),
                linear-gradient(160deg, var(--bg-1), var(--bg-2));
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 16px;
        }
        .card {
            width: min(680px, 100%);
            background: rgba(255,255,255,0.94);
            border: 1px solid #e2ebf5;
            border-radius: 18px;
            box-shadow: 0 14px 36px rgba(19, 39, 66, 0.12);
            overflow: hidden;
        }
        .header {
            padding: 18px 18px 14px;
            color: #fff;
            background: linear-gradient(140deg, var(--brand) 0%, var(--brand-2) 100%);
        }
        .header h1 {
            margin: 0;
            font-size: 1.15rem;
        }
        .header p {
            margin: 8px 0 0;
            opacity: 0.9;
            font-size: 0.92rem;
        }
        .body { padding: 16px; }
        .field { margin-bottom: 12px; }
        .field label {
            display: block;
            margin-bottom: 6px;
            font-weight: 700;
            font-size: 0.9rem;
        }
        input {
            width: 100%;
            border: 1px solid var(--line);
            border-radius: 10px;
            padding: 11px 12px;
            font-size: 0.98rem;
        }
        .actions {
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
            margin-top: 6px;
        }
        button, a.btn {
            border: none;
            border-radius: 10px;
            padding: 10px 14px;
            font-weight: 700;
            cursor: pointer;
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            justify-content: center;
        }
        button.primary, a.primary {
            color: #fff;
            background: linear-gradient(140deg, var(--brand) 0%, var(--brand-2) 100%);
        }
        button.secondary {
            color: var(--text);
            background: #eef4fb;
        }
        button:disabled, a.disabled {
            opacity: 0.5;
            pointer-events: none;
        }
        .hidden { display: none; }
        .meta {
            margin-top: 12px;
            font-size: 0.9rem;
            color: var(--muted);
        }
        .platform-grid {
            margin-top: 14px;
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 10px;
        }
        .platform {
            border: 1px solid var(--line);
            border-radius: 12px;
            padding: 12px;
            background: #fff;
        }
        .platform h3 { margin: 0 0 8px; }
        .platform p {
            margin: 0 0 10px;
            color: var(--muted);
            font-size: 0.9rem;
            min-height: 36px;
        }
        .status {
            margin-top: 12px;
            font-size: 0.9rem;
            min-height: 20px;
        }
    </style>
</head>
<body>
    <div class="card">
        <div class="header">
            <h1>Clinic Mobile Downloads</h1>
            <p>Login with your serial number and choose Android or iOS.</p>
        </div>
        <div class="body">
            <div id="login-box">
                <div class="field">
                    <label for="serial-input">Serial Number</label>
                    <input id="serial-input" placeholder="DENTAL-123456" />
                </div>
                <div class="actions">
                    <button class="primary" onclick="loginWithSerial()">Login</button>
                </div>
            </div>

            <div id="download-box" class="hidden">
                <div class="meta" id="license-meta"></div>
                <div class="platform-grid">
                    <div class="platform">
                        <h3>Android</h3>
                        <p>Download and install the Android clinic companion app.</p>
                        <a id="android-btn" class="btn primary" href="#" target="_blank" rel="noopener">Download Android</a>
                    </div>
                    <div class="platform">
                        <h3>iOS</h3>
                        <p>Download the iOS build/TestFlight link for clinic users.</p>
                        <a id="ios-btn" class="btn primary" href="#" target="_blank" rel="noopener">Download iOS</a>
                    </div>
                </div>
                <div class="actions">
                    <button class="secondary" onclick="resetPortal()">Use another serial</button>
                </div>
            </div>

            <div id="status" class="status"></div>
        </div>
    </div>

    <script>
        const OFFLINE_LICENSE_KEY = 'clinic_offline_license_token';

        function setStatus(message, isError = false) {
            const status = document.getElementById('status');
            status.textContent = message || '';
            status.style.color = isError ? '#c7254e' : '#2d6a4f';
        }

        function setDownloadButton(anchorId, option) {
            const btn = document.getElementById(anchorId);
            if (!option || !option.available || !option.url) {
                btn.classList.add('disabled');
                btn.removeAttribute('href');
                return;
            }
            btn.classList.remove('disabled');
            btn.href = option.url;
        }

        function renderLicense(payload) {
            document.getElementById('login-box').classList.add('hidden');
            document.getElementById('download-box').classList.remove('hidden');
            const meta = `Clinic: ${payload.clinic_name || '-'} | Plan: ${payload.plan_name || '-'} | Expires: ${payload.expires_at || '-'}`;
            document.getElementById('license-meta').textContent = meta;
            setStatus('License ready.');
        }

        async function restoreOfflineLicense() {
            const savedToken = localStorage.getItem(OFFLINE_LICENSE_KEY);
            if (!savedToken) {
                return;
            }

            try {
                const response = await fetch('/api/license/offline-verify', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({offline_license_token: savedToken})
                });
                const payload = await response.json();
                if (!response.ok) {
                    localStorage.removeItem(OFFLINE_LICENSE_KEY);
                    return;
                }

                renderLicense(payload.offline_license || {});
                const downloads = payload.downloads || {};
                if (downloads.android) {
                    setDownloadButton('android-btn', downloads.android);
                }
                if (downloads.ios) {
                    setDownloadButton('ios-btn', downloads.ios);
                }
            } catch (_) {
                // Silent by design: offline restore should not bother the user.
            }
        }

        async function loginWithSerial() {
            const serial = document.getElementById('serial-input').value.trim().toUpperCase();
            if (!serial) {
                setStatus('Please enter your serial number.', true);
                return;
            }

            setStatus('Checking serial...');
            try {
                const response = await fetch('/api/license/login', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({serial_number: serial})
                });
                const payload = await response.json();
                if (!response.ok) {
                    setStatus(payload.error || 'Login failed.', true);
                    return;
                }

                if (payload.offline_license_token) {
                    localStorage.setItem(OFFLINE_LICENSE_KEY, payload.offline_license_token);
                }

                renderLicense(payload);

                setDownloadButton('android-btn', payload.downloads?.android);
                setDownloadButton('ios-btn', payload.downloads?.ios);
                setStatus('Login successful.');
            } catch (error) {
                setStatus('Network error while validating serial.', true);
            }
        }

        function resetPortal() {
            localStorage.removeItem(OFFLINE_LICENSE_KEY);
            document.getElementById('download-box').classList.add('hidden');
            document.getElementById('login-box').classList.remove('hidden');
            document.getElementById('serial-input').value = '';
            setStatus('');
        }

        document.addEventListener('DOMContentLoaded', restoreOfflineLicense);
    </script>
</body>
</html>
'''

LOGIN_TEMPLATE = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sign in — DentaCare</title>
<style>
  * { box-sizing: border-box; }
  body { margin:0; min-height:100vh; display:flex; align-items:center; justify-content:center;
         font-family: 'Segoe UI', Arial, sans-serif; background: linear-gradient(135deg,#1e88e5 0%,#0d47a1 100%); }
  .card { background:#fff; border-radius:14px; box-shadow:0 18px 50px rgba(0,0,0,0.25);
          padding:34px 32px; width:100%; max-width:360px; }
  .brand { text-align:center; margin-bottom:20px; }
  .brand img { height:64px; width:auto; }
  .brand h1 { font-size:20px; margin:10px 0 2px; color:#1a237e; }
  .brand p { margin:0; color:#607d8b; font-size:13px; }
  label { display:block; font-size:13px; color:#37474f; margin:14px 0 6px; }
  input { width:100%; padding:11px 12px; border:1px solid #cfd8dc; border-radius:8px; font-size:15px; }
  input:focus { outline:none; border-color:#1e88e5; box-shadow:0 0 0 3px rgba(30,136,229,0.15); }
  button { width:100%; margin-top:22px; padding:12px; border:none; border-radius:8px; cursor:pointer;
           background:#1e88e5; color:#fff; font-size:15px; font-weight:600; }
  button:hover { background:#1565c0; }
  .error { margin-top:16px; background:#ffebee; border:1px solid #ef9a9a; color:#b71c1c;
           border-radius:8px; padding:9px 12px; font-size:13px; }
</style>
</head>
<body>
  <form class="card" method="POST" action="/login">
    <div class="brand">
      <img src="/logo" alt="DentaCare">
      <h1>DentaCare</h1>
      <p>Dental Management System</p>
    </div>
    {% if error %}<div class="error">{{ error }}</div>{% endif %}
    <input type="hidden" name="next" value="{{ next_url }}">
    <label for="username">Username</label>
    <input type="text" id="username" name="username" autocomplete="username" autofocus required>
    <label for="password">Password</label>
    <input type="password" id="password" name="password" autocomplete="current-password" required>
    <button type="submit">Sign in</button>
  </form>
</body>
</html>'''
