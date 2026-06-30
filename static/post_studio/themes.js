// themes.js — pure theme tokens for Post Studio. Single source of truth for
// background + per-role typography + card/badge/divider styling. render.js reads
// bg/card/badge/divider; composition.applyTheme stamps the per-role typography
// onto elements. Font family names match fonts.js FONT_OPTIONS[].family.

export const THEME_OPTIONS = [
  { id: 'dark_premium', label: 'Dark Premium', label_ar: 'فاخر داكن' },
  { id: 'light_luxury', label: 'Light Luxury', label_ar: 'فاخر فاتح' },
  { id: 'clinical_premium', label: 'Clinical Premium', label_ar: 'طبي فاخر' },
  { id: 'bold_editorial', label: 'Bold Editorial', label_ar: 'جريء تحريري' },
];

export const THEMES = {
  // The reference (Navy & Gold / go.png): navy radial glow, white Poppins headline,
  // gold subline + doctor, gold-rim portrait panels, number-in-pill labels, tooth
  // divider, 3-layer gold sine wave footer.
  dark_premium: {
    bg: 'radial-gradient(circle at 50% 44%, #0C1E3A 0%, #040E20 100%)',
    headline: { font: 'Poppins', size: 78, weight: 700, color: '#F5F5F0', letterSpacing: 0 },
    subline: { font: 'Poppins', size: 58, weight: 700, color: '#C6A274', letterSpacing: 0 },
    label: { font: 'Poppins', size: 20, weight: 400, color: '#F5F5F0', letterSpacing: 0, style: 'pill' },
    doctor: { font: 'Poppins', size: 52, weight: 700, color: '#C6A274', letterSpacing: 2 },
    card: {
      borderRadius: 14, aspect: '250 / 320',
      border: '1px solid rgba(198,162,116,.92)',
      boxShadow: 'none', background: '#08162C',
    },
    badge: { shape: 'circle', background: 'transparent', color: '#F5F5F0', border: '2px solid rgba(198,162,116,.86)' },
    pill: {
      border: '2px solid rgba(198,162,116,.86)',
      circleBorder: '2px solid rgba(198,162,116,.86)',
      color: '#F5F5F0',
    },
    // thickness/lineWidth/lineOpacity override the render defaults; lineOpacity '1'
    // lets the color's own .86 alpha carry the spec's "86%" (matches the tooth icon).
    divider: { enabled: true, color: 'rgba(198,162,116,.86)', icon: 'tooth', thickness: '2px', lineWidth: '32%', lineOpacity: '1' },
    waveFooter: {
      enabled: true, color: '#C6A274',
      layers: [
        { amp: 14, freq: 0.012, opacity: 0.15 },
        { amp: 18, freq: 0.009, opacity: 0.12 },
        { amp: 11, freq: 0.015, opacity: 0.086 },
      ],
    },
    accent: '#C6A274',
  },
  // Warm cream, ink + gold, serif headline, soft-shadow white cards, thin gold badges.
  light_luxury: {
    bg: '#f6f1e7',
    headline: { font: 'Playfair Display', size: 84, weight: 700, color: '#2a2620', letterSpacing: 0 },
    subline: { font: 'Manrope', size: 46, weight: 600, color: '#b08d3c', letterSpacing: 0 },
    label: { font: 'Manrope', size: 28, weight: 600, color: '#6b6256', letterSpacing: 0 },
    doctor: { font: 'Manrope', size: 36, weight: 700, color: '#b08d3c', letterSpacing: 5 },
    card: {
      borderRadius: 20, border: '1px solid rgba(0,0,0,.08)',
      boxShadow: '0 18px 40px rgba(0,0,0,.12)', background: '#ffffff',
    },
    badge: { shape: 'circle', background: 'transparent', color: '#b08d3c', border: '1px solid #b08d3c' },
    divider: { enabled: true, color: '#c2a25a', icon: 'tooth' },
    accent: '#b08d3c',
  },
  // Crisp white, DentaCare blue, airy bold sans, filled blue badges, clean cards.
  clinical_premium: {
    bg: '#ffffff',
    headline: { font: 'Manrope', size: 80, weight: 800, color: '#0f2a3f', letterSpacing: 0 },
    subline: { font: 'Manrope', size: 46, weight: 600, color: '#0ea5e9', letterSpacing: 0 },
    label: { font: 'Manrope', size: 28, weight: 600, color: '#33506a', letterSpacing: 0 },
    doctor: { font: 'Manrope', size: 34, weight: 700, color: '#0ea5e9', letterSpacing: 4 },
    card: {
      borderRadius: 16, border: '1px solid #d7e3ee',
      boxShadow: '0 10px 28px rgba(14,165,233,.10)', background: '#f4f9fc',
    },
    badge: { shape: 'circle', background: '#0ea5e9', color: '#ffffff', border: 'none' },
    divider: { enabled: false, color: '#0ea5e9', icon: 'tooth' },
    accent: '#0ea5e9',
  },
  // High-contrast dark, oversized type, punchy accent, solid square badges, square cards.
  bold_editorial: {
    bg: '#121212',
    headline: { font: 'Manrope', size: 100, weight: 800, color: '#ffffff', letterSpacing: 0 },
    subline: { font: 'Manrope', size: 52, weight: 700, color: '#ff5a3c', letterSpacing: 0 },
    label: { font: 'Manrope', size: 30, weight: 700, color: '#ffffff', letterSpacing: 0 },
    doctor: { font: 'Manrope', size: 38, weight: 800, color: '#ffffff', letterSpacing: 4 },
    card: {
      borderRadius: 4, border: '4px solid #ffffff',
      boxShadow: 'none', background: '#1f1f1f',
    },
    badge: { shape: 'square', background: '#ff5a3c', color: '#ffffff', border: 'none' },
    divider: { enabled: false, color: '#ff5a3c', icon: 'tooth' },
    accent: '#ff5a3c',
  },
};

export function themeTokens(name) {
  return THEMES[name] || THEMES.dark_premium;
}
