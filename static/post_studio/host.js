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
          out.push({ id: `${f.name}:${f.size}`, dataUrl: await fileToDataUrl(f) });
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
