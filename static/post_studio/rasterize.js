// rasterize.js — client-side PNG export via SVG <foreignObject> -> canvas.
// Technique validated by the P2a spike (decision: PASS — see
// docs/superpowers/notes/2026-06-27-rasterizer-spike-decision.md). The node's
// visual styles MUST be inline (the SVG render context cannot reach external
// stylesheets), which render.js guarantees.

export async function rasterizeToPngBlob(node, scale = 2) {
  if (document.fonts && document.fonts.ready) {
    await document.fonts.ready;
  }
  const rect = node.getBoundingClientRect();
  const w = Math.round(node.offsetWidth || rect.width);
  const h = Math.round(node.offsetHeight || rect.height);
  const xhtml = new XMLSerializer().serializeToString(node);
  const svg =
    '<svg xmlns="http://www.w3.org/2000/svg" width="' + w + '" height="' + h + '">' +
      '<foreignObject x="0" y="0" width="100%" height="100%">' +
        '<div xmlns="http://www.w3.org/1999/xhtml">' + xhtml + '</div>' +
      '</foreignObject>' +
    '</svg>';
  const svgUrl = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
  const img = new Image();
  await new Promise((resolve, reject) => {
    img.onload = resolve;
    img.onerror = () => reject(new Error('SVG render failed'));
    img.src = svgUrl;
  });
  const canvas = document.createElement('canvas');
  canvas.width = Math.round(w * scale);
  canvas.height = Math.round(h * scale);
  const ctx = canvas.getContext('2d');
  ctx.scale(scale, scale);
  ctx.drawImage(img, 0, 0);
  return await new Promise((resolve, reject) => {
    canvas.toBlob((blob) => {
      // A tainted canvas yields a null blob (or throws SecurityError above).
      if (blob) resolve(blob);
      else reject(new Error('Canvas export blocked (tainted or empty)'));
    }, 'image/png');
  });
}
