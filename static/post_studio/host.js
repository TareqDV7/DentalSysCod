// host.js — host adapter. The desktop host talks to Flask via fetch; the page's
// CSRF interceptor (templates.py) adds X-CSRFToken to same-origin unsafe methods,
// so no manual token handling. The mobile host (P6) implements the same shape
// over a Dart<->JS bridge. DOM/network are only touched inside method bodies, so
// this module imports cleanly under `node --test`.

/**
 * @typedef {Object} PostStudioHost
 * @property {() => Promise<{id:string, dataUrl:string}[]>} pickPhotos
 * @property {(png:Blob, templateJson:string, meta:{theme?:string,size?:string,title?:string}) => Promise<{id:number}>} savePost
 * @property {() => Promise<Object[]>} listPosts
 * @property {(id:number) => Promise<Object>} getPost
 * @property {(id:number) => Promise<void>} deletePost
 */

function fileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    const fr = new FileReader();
    fr.onload = () => resolve(fr.result);
    fr.onerror = () => reject(new Error('read failed'));
    fr.readAsDataURL(file);
  });
}

// A picked photo is stored as a source data URL directly in template_json
// (P4a decision) — unbounded, an unresized phone photo can be several MB,
// multiplied by up to MAX_BLOCKS per post. Downscale to a bounded longest
// edge before it ever reaches composition state; the export canvas is at
// most 1080px, so this leaves generous headroom for on-canvas cropping
// without storing multi-megapixel originals.
export const MAX_PHOTO_DIM = 1600;

export function downscaleDataUrl(dataUrl, maxDim) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      const scale = Math.min(1, maxDim / Math.max(img.naturalWidth, img.naturalHeight));
      if (scale >= 1) { resolve(dataUrl); return; }
      const canvas = document.createElement('canvas');
      canvas.width = Math.round(img.naturalWidth * scale);
      canvas.height = Math.round(img.naturalHeight * scale);
      canvas.getContext('2d').drawImage(img, 0, 0, canvas.width, canvas.height);
      resolve(canvas.toDataURL('image/jpeg', 0.85));
    };
    img.onerror = () => reject(new Error('image decode failed'));
    img.src = dataUrl;
  });
}

/** @returns {PostStudioHost} */
export function createDesktopHost() {
  function pickPhotos() {
    return new Promise((resolve) => {
      const input = document.createElement('input');
      input.type = 'file';
      input.accept = 'image/*';
      input.multiple = true;
      input.style.display = 'none';
      document.body.appendChild(input);
      input.addEventListener('change', async () => {
        const files = Array.from(input.files || []);
        const out = [];
        for (const f of files) {
          const raw = await fileToDataUrl(f);
          out.push({ id: `${f.name}:${f.size}`, dataUrl: await downscaleDataUrl(raw, MAX_PHOTO_DIM) });
        }
        input.remove();
        resolve(out);
      }, { once: true });
      input.click();
    });
  }

  async function savePost(png, templateJson, meta) {
    const fd = new FormData();
    fd.append('image', png, 'export.png');
    fd.append('template_json', templateJson);
    fd.append('theme', (meta && meta.theme) || '');
    fd.append('size', (meta && meta.size) || '');
    fd.append('title', (meta && meta.title) || '');
    const r = await fetch('/api/posts', { method: 'POST', body: fd });
    if (!r.ok) throw new Error(`save failed: ${r.status}`);
    return await r.json();
  }

  async function listPosts() {
    const r = await fetch('/api/posts');
    if (!r.ok) throw new Error(`list failed: ${r.status}`);
    return await r.json();
  }

  async function getPost(id) {
    const r = await fetch(`/api/posts/${id}`);
    if (!r.ok) throw new Error(`get failed: ${r.status}`);
    return await r.json();
  }

  async function deletePost(id) {
    const r = await fetch(`/api/posts/${id}`, { method: 'DELETE' });
    if (!r.ok) throw new Error(`delete failed: ${r.status}`);
  }

  return { pickPhotos, savePost, listPosts, getPost, deletePost };
}

/**
 * @param {{postMessage: (json:string) => void}} [bridge] Injected for testing;
 * defaults to the Dart-injected `window.PostStudioBridge` JavaScriptChannel.
 * @returns {PostStudioHost}
 */
export function createMobileHost(bridge = globalThis.PostStudioBridge) {
  let seq = 0;
  const pending = new Map();

  globalThis.__psResolve = (id, resultJson) => {
    const p = pending.get(id);
    if (!p) return;
    pending.delete(id);
    p.resolve(resultJson == null ? undefined : JSON.parse(resultJson));
  };
  globalThis.__psReject = (id, message) => {
    const p = pending.get(id);
    if (!p) return;
    pending.delete(id);
    p.reject(new Error(message));
  };

  function call(method, args) {
    return new Promise((resolve, reject) => {
      const id = String(++seq);
      pending.set(id, { resolve, reject });
      bridge.postMessage(JSON.stringify({ id, method, args }));
    });
  }

  async function pickPhotos() {
    const picked = (await call('pickPhotos', null)) || [];
    const out = [];
    for (const item of picked) {
      out.push({ id: item.id, dataUrl: await downscaleDataUrl(item.dataUrl, MAX_PHOTO_DIM) });
    }
    return out;
  }

  async function savePost(png, templateJson, meta) {
    const dataUrl = await fileToDataUrl(png);
    const pngB64 = dataUrl.slice(dataUrl.indexOf(',') + 1);
    return call('savePost', { pngB64, templateJson, meta: meta || {} });
  }

  function listPosts() {
    return call('listPosts', null).then((r) => r || []);
  }

  function getPost(id) {
    return call('getPost', { id });
  }

  function deletePost(id) {
    return call('deletePost', { id });
  }

  return { pickPhotos, savePost, listPosts, getPost, deletePost };
}
