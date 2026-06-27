/**
 * WoW Commander unit icon composer — Konva canvas, client-side PNG export.
 */

const ASSETS_BASE = 'assets/';
const MANIFEST_URL = `${ASSETS_BASE}icon_manifest.json`;

const CATEGORY_LABELS = {
  shapes: 'Shapes',
  identifiers: 'Identifiers',
  addons: 'Add-ons',
  custom_features: 'Custom',
  classes: 'WoW class',
  pptx_curated: 'Briefing',
};

/** @type {Record<string, HTMLImageElement>} */
const imageCache = {};

let manifest = null;
let stage = null;
let previewBgLayer = null;
let layerGroup = null;
let transformer = null;
/** @type {Array<{uid: string, meta: object, node: Konva.Image, tintable?: boolean, imageUrl?: string}>} */
let layers = [];
let selectedUid = null;
let fillColor = '#80ffff';
let borderColor = '#000000';
let activeCategory = 'shapes';
let pickerMode = 'list';
let activeDrawTool = 'select';
let curveBend = 0.35;
let drawColor = '#000000';
let drawStrokePt = 2;
/** @type {{ tool: string, start: {x:number,y:number}, preview: Konva.Node | null } | null} */
let drawingSession = null;

const PT_TO_PX = 96 / 72;
const HISTORY_KEY = 'wowc_icon_builder_history';
const HISTORY_MAX = 5;

function ptToPx(pt) {
  return pt * PT_TO_PX;
}

async function loadManifest() {
  const res = await fetch(MANIFEST_URL);
  if (!res.ok) throw new Error('Failed to load icon manifest');
  manifest = await res.json();
}

function loadImage(url) {
  if (imageCache[url]) return Promise.resolve(imageCache[url]);
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = () => {
      imageCache[url] = img;
      resolve(img);
    };
    img.onerror = () => reject(new Error(`Failed to load ${url}`));
    img.src = url;
  });
}

function hexToRgb(hex) {
  const h = hex.replace('#', '');
  const full = h.length === 3 ? h.split('').map((c) => c + c).join('') : h;
  const n = parseInt(full, 16);
  return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 };
}

function findInteriorSeed(data, w, h) {
  let minX = w;
  let minY = h;
  let maxX = 0;
  let maxY = 0;
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      if (data[(y * w + x) * 4 + 3] > 128) {
        minX = Math.min(minX, x);
        maxX = Math.max(maxX, x);
        minY = Math.min(minY, y);
        maxY = Math.max(maxY, y);
      }
    }
  }
  const cx = Math.floor((minX + maxX) / 2);
  const cy = Math.floor((minY + maxY) / 2);
  const candidates = [
    [cx, cy],
    [cx, cy - 8],
    [cx, cy + 8],
    [cx - 8, cy],
    [cx + 8, cy],
  ];
  for (const [x, y] of candidates) {
    if (x < 0 || x >= w || y < 0 || y >= h) continue;
    if (data[(y * w + x) * 4 + 3] < 20) return [x, y];
  }
  for (let y = minY; y <= maxY; y++) {
    for (let x = minX; x <= maxX; x++) {
      if (data[(y * w + x) * 4 + 3] < 20) return [x, y];
    }
  }
  return [cx, cy];
}

function floodFillInterior(ctx, w, h, color) {
  const imageData = ctx.getImageData(0, 0, w, h);
  const data = imageData.data;
  const [seedX, seedY] = findInteriorSeed(data, w, h);
  const fill = hexToRgb(color);
  const stack = [[seedX, seedY]];
  const visited = new Uint8Array(w * h);

  while (stack.length) {
    const [x, y] = stack.pop();
    if (x < 0 || x >= w || y < 0 || y >= h) continue;
    const i = y * w + x;
    if (visited[i]) continue;
    const p = i * 4;
    if (data[p + 3] > 20) continue;
    visited[i] = 1;
    data[p] = fill.r;
    data[p + 1] = fill.g;
    data[p + 2] = fill.b;
    data[p + 3] = 255;
    stack.push([x + 1, y], [x - 1, y], [x, y + 1], [x, y - 1]);
  }
  ctx.putImageData(imageData, 0, 0);
}

/** Fill every transparent pocket fully enclosed by opaque pixels (banner ruffles, etc.). */
function floodFillEnclosedRegions(ctx, w, h, color) {
  const imageData = ctx.getImageData(0, 0, w, h);
  const data = imageData.data;
  const fill = hexToRgb(color);
  const exterior = new Uint8Array(w * h);

  const isEmpty = (x, y) => data[(y * w + x) * 4 + 3] < 20;

  const stack = [];
  for (let x = 0; x < w; x++) {
    for (const y of [0, h - 1]) {
      const i = y * w + x;
      if (isEmpty(x, y) && !exterior[i]) {
        exterior[i] = 1;
        stack.push([x, y]);
      }
    }
  }
  for (let y = 0; y < h; y++) {
    for (const x of [0, w - 1]) {
      const i = y * w + x;
      if (isEmpty(x, y) && !exterior[i]) {
        exterior[i] = 1;
        stack.push([x, y]);
      }
    }
  }

  while (stack.length) {
    const [x, y] = stack.pop();
    for (const [nx, ny] of [
      [x + 1, y],
      [x - 1, y],
      [x, y + 1],
      [x, y - 1],
    ]) {
      if (nx < 0 || nx >= w || ny < 0 || ny >= h) continue;
      const i = ny * w + nx;
      if (!isEmpty(nx, ny) || exterior[i]) continue;
      exterior[i] = 1;
      stack.push([nx, ny]);
    }
  }

  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const i = y * w + x;
      if (!isEmpty(x, y) || exterior[i]) continue;
      const p = i * 4;
      data[p] = fill.r;
      data[p + 1] = fill.g;
      data[p + 2] = fill.b;
      data[p + 3] = 255;
    }
  }
  ctx.putImageData(imageData, 0, 0);
}

/** Tint a white-or-dark alpha mask with a solid color. */
function tintSolid(img, color) {
  const w = img.width;
  const h = img.height;
  const canvas = document.createElement('canvas');
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext('2d');
  ctx.drawImage(img, 0, 0);
  ctx.globalCompositeOperation = 'source-in';
  ctx.fillStyle = color;
  ctx.fillRect(0, 0, w, h);
  return canvas;
}

function composeShapePreserveWhite(img, fill, border) {
  const w = img.width;
  const h = img.height;
  const out = composeShapeCanvas(img, fill, border);
  const octx = out.getContext('2d');
  const src = document.createElement('canvas');
  src.width = w;
  src.height = h;
  const sctx = src.getContext('2d');
  sctx.drawImage(img, 0, 0);
  const srcData = sctx.getImageData(0, 0, w, h).data;
  const outImage = octx.getImageData(0, 0, w, h);
  const outData = outImage.data;
  for (let i = 0; i < srcData.length; i += 4) {
    if (srcData[i] > 200 && srcData[i + 1] > 200 && srcData[i + 2] > 200 && srcData[i + 3] > 128) {
      outData[i] = 255;
      outData[i + 1] = 255;
      outData[i + 2] = 255;
      outData[i + 3] = srcData[i + 3];
    }
  }
  octx.putImageData(outImage, 0, 0);
  return out;
}

function applyTintToImage(img, tintMode) {
  if (tintMode === 'shape') return composeShapeCanvas(img, fillColor, borderColor);
  if (tintMode === 'shape_preserve_white') return composeShapePreserveWhite(img, fillColor, borderColor);
  if (tintMode === 'fill') return tintSolid(img, fillColor);
  if (tintMode === 'border') return tintSolid(img, borderColor);
  return img;
}

/** Compose fill + border for colorless outline PNGs. */
function composeShapeCanvas(img, fill, border) {
  const w = img.width;
  const h = img.height;

  const fillCanvas = document.createElement('canvas');
  fillCanvas.width = w;
  fillCanvas.height = h;
  const fctx = fillCanvas.getContext('2d');
  fctx.drawImage(img, 0, 0);
  floodFillEnclosedRegions(fctx, w, h, fill);

  const borderCanvas = document.createElement('canvas');
  borderCanvas.width = w;
  borderCanvas.height = h;
  const bctx = borderCanvas.getContext('2d');
  bctx.drawImage(img, 0, 0);
  bctx.globalCompositeOperation = 'source-in';
  bctx.fillStyle = border;
  bctx.fillRect(0, 0, w, h);

  const out = document.createElement('canvas');
  out.width = w;
  out.height = h;
  const octx = out.getContext('2d');
  octx.drawImage(fillCanvas, 0, 0);
  octx.drawImage(borderCanvas, 0, 0);
  return out;
}

function uid() {
  return `layer-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
}

function getShapeLayer() {
  return layers.find((l) => l.meta.category === 'shapes');
}

let resizeMode = 'proportional';

function layerSupportsFreeResize(layer) {
  if (!layer || layer.gluedAddon) return false;
  const cat = layer.meta.category;
  return (
    cat === 'identifiers' ||
    cat === 'classes' ||
    cat === 'custom_features' ||
    cat === 'pptx_curated' ||
    cat === 'drawing'
  );
}

const FREE_RESIZE_ANCHORS = [
  'top-left',
  'top-right',
  'bottom-left',
  'bottom-right',
  'top-center',
  'bottom-center',
  'middle-left',
  'middle-right',
];
const PROPORTIONAL_ANCHORS = ['top-left', 'top-right', 'bottom-left', 'bottom-right'];

function applyTransformerToLayer(layer) {
  if (!transformer) return;
  if (!layer || layer.gluedAddon) {
    transformer.nodes([]);
    transformer.getLayer()?.batchDraw();
    return;
  }
  const free = layerSupportsFreeResize(layer) && resizeMode === 'free';
  transformer.nodes([]);
  transformer.keepRatio(!free);
  transformer.enabledAnchors(free ? FREE_RESIZE_ANCHORS : PROPORTIONAL_ANCHORS);
  transformer.nodes([layer.node]);
  transformer.forceUpdate();
  transformer.getLayer()?.batchDraw();
}

function updateResizeModeControls(layer) {
  const panel = document.getElementById('resize-mode-controls');
  const hint = document.getElementById('resize-mode-hint');
  if (!panel) return;
  const show = layerSupportsFreeResize(layer);
  panel.classList.toggle('hidden', !show);
  hint?.classList.toggle('hidden', !show);
  if (!show) return;
  panel.querySelectorAll('[data-resize-mode]').forEach((btn) => {
    btn.classList.toggle('active', btn.dataset.resizeMode === resizeMode);
  });
}

const ADDON_SIZE_RATIO = 0.25;
const HQ_FLAG_SIZE_RATIO = ADDON_SIZE_RATIO * 1.25 * 0.75;
const BANNER_BUFFER_RATIO = 0.06;

function getShapeFrame(shapeLayer) {
  const node = shapeLayer.node;
  const w = shapeLayer.meta.width * Math.abs(node.scaleX());
  const h = shapeLayer.meta.height * Math.abs(node.scaleY());
  const cx = node.x();
  const cy = node.y();
  return {
    cx,
    cy,
    w,
    h,
    rotation: node.rotation(),
    left: cx - w / 2,
    right: cx + w / 2,
    top: cy - h / 2,
    bottom: cy + h / 2,
  };
}

/** Fixed add-on placement (Warsworn HQ reference: flag on right, banner above). */
function getGluedAddonPlacement(asset, shapeLayerOrFrame) {
  const frame = shapeLayerOrFrame?.node ? getShapeFrame(shapeLayerOrFrame) : shapeLayerOrFrame;
  const gap = 6;

  if (asset.text_editable || asset.id === 'text_banner_add_on') {
    const scale = Math.min((frame.w * 0.92) / asset.width, (frame.h * 0.4) / asset.height);
    const buffer = Math.max(8, frame.h * BANNER_BUFFER_RATIO);
    const bh = asset.height * scale;
    return {
      x: frame.cx,
      y: frame.top - buffer - bh / 2,
      scaleX: scale,
      scaleY: scale,
      rotation: frame.rotation,
    };
  }

  if (asset.id === 'hq_flag_add_on') {
    const addonScale = Math.min(
      (frame.w * HQ_FLAG_SIZE_RATIO) / asset.width,
      (frame.h * HQ_FLAG_SIZE_RATIO) / asset.height,
    );
    const aw = asset.width * addonScale;
    const ah = asset.height * addonScale;
    return {
      x: frame.right + gap + aw * 0.28,
      y: frame.top + ah * 0.38,
      scaleX: addonScale,
      scaleY: addonScale,
      rotation: frame.rotation,
    };
  }

  const addonScale = Math.min(
    (frame.w * ADDON_SIZE_RATIO) / asset.width,
    (frame.h * ADDON_SIZE_RATIO) / asset.height,
  );
  const aw = asset.width * addonScale;
  const ah = asset.height * addonScale;

  if (asset.id === 'mercenary') {
    return {
      x: frame.left - gap - aw / 2,
      y: frame.top + ah * 0.42,
      scaleX: addonScale,
      scaleY: addonScale,
      rotation: frame.rotation,
    };
  }

  return {
    x: frame.right + gap + aw / 2,
    y: frame.top + ah * 0.42,
    scaleX: addonScale,
    scaleY: addonScale,
    rotation: frame.rotation,
  };
}

async function buildExportCanvas(exportSize) {
  const artboard = manifest.artboard || 512;
  const pixelRatio = exportSize / artboard;

  transformer.nodes([]);
  previewBgLayer.visible(false);
  layerGroup.draw();
  const out = stage.toCanvas({ pixelRatio });
  previewBgLayer.visible(true);
  stage.draw();
  if (selectedUid) {
    const hit = layers.find((l) => l.uid === selectedUid);
    if (hit) applyTransformerToLayer(hit);
  }

  return out;
}

async function buildExportDataUrl(exportSize) {
  const canvas = await buildExportCanvas(exportSize);
  return canvas.toDataURL('image/png');
}

function repositionGluedAddons() {
  const shape = getShapeLayer();
  if (!shape) return;
  layers
    .filter((l) => l.gluedAddon)
    .forEach((layer) => {
      applyTransform(layer.node, getGluedAddonPlacement(layer.meta, shape));
    });
  layerGroup.draw();
}

function bindShapeTransformListeners(shapeEntry) {
  const node = shapeEntry.node;
  const onChange = () => repositionGluedAddons();
  node.on('dragmove dragend', onChange);
  node.on('transform transformend', onChange);
}

/** Place identifiers at manifest defaults (as authored in source PNGs). */
function getIdentifierPlacement(asset) {
  const def = asset.default || {};
  const scale = def.scale ?? 1;
  return {
    x: def.x ?? manifest.artboard / 2,
    y: def.y ?? manifest.artboard / 2,
    scaleX: scale,
    scaleY: scale,
    rotation: def.rotation ?? 0,
  };
}

function initStage() {
  const size = manifest.artboard || 512;
  const container = document.getElementById('stage-container');
  container.style.width = `${size}px`;
  container.style.height = `${size}px`;
  stage = new Konva.Stage({ container: 'stage-container', width: size, height: size });

  previewBgLayer = new Konva.Layer({ name: 'preview-bg' });
  previewBgLayer.add(
    new Konva.Rect({
      x: 0,
      y: 0,
      width: size,
      height: size,
      fill: '#ffffff',
      listening: false,
    }),
  );
  stage.add(previewBgLayer);

  layerGroup = new Konva.Layer();
  stage.add(layerGroup);

  const trLayer = new Konva.Layer();
  transformer = new Konva.Transformer({
    rotateEnabled: true,
    keepRatio: true,
    enabledAnchors: PROPORTIONAL_ANCHORS,
    boundBoxFunc: (oldBox, newBox) => {
      if (Math.abs(newBox.width) < 12 || Math.abs(newBox.height) < 12) return oldBox;
      return newBox;
    },
  });
  trLayer.add(transformer);
  stage.add(trLayer);

  stage.on('click tap', (e) => {
    if (activeDrawTool !== 'select') return;
    const hit = findLayerByNode(e.target);
    if (hit) selectLayer(hit.uid);
    else if (isCanvasBackground(e.target)) selectLayer(null);
  });

  initDrawingHandlers();
}

function isCanvasBackground(target) {
  return target === stage || target === layerGroup;
}

function findLayerByNode(node) {
  if (!node || node === stage) return null;
  for (const layer of layers) {
    if (layer.node === node) return layer;
    if (layer.layerType === 'text_banner') {
      if (node === layer.imageNode || node === layer.textNode) return layer;
      let parent = node.getParent?.();
      while (parent) {
        if (parent === layer.node) return layer;
        parent = parent.getParent?.();
      }
    }
  }
  return null;
}

function selectLayer(layerUid) {
  selectedUid = layerUid;
  const hit = layers.find((l) => l.uid === layerUid);
  applyTransformerToLayer(hit);
  renderLayerList();
  highlightActiveAsset();
  updateBannerControls(hit);
  updateDrawControls(hit);
  updateResizeModeControls(hit);
}

function updateBannerControls(layer) {
  const panel = document.getElementById('banner-controls');
  const isBanner = layer?.layerType === 'text_banner';
  panel.classList.toggle('hidden', !isBanner);
  if (!isBanner) return;
  document.getElementById('banner-text').value = layer.bannerText || '';
  document.getElementById('banner-font-size').value = String(layer.bannerFontSize || 28);
  document.getElementById('banner-bold').checked = !!layer.bannerBold;
}

function updateDrawControls(layer) {
  const ptSelect = document.getElementById('draw-stroke-pt');
  if (layer?.layerType === 'drawing' && layer.strokePt) {
    ptSelect.value = String(layer.strokePt);
    drawStrokePt = layer.strokePt;
  }
}

function preserveTransform(node) {
  if (!node) return null;
  return {
    x: node.x(),
    y: node.y(),
    scaleX: node.scaleX(),
    scaleY: node.scaleY(),
    rotation: node.rotation(),
  };
}

function applyTransform(node, t) {
  if (!t) return;
  node.x(t.x);
  node.y(t.y);
  node.scaleX(t.scaleX);
  node.scaleY(t.scaleY);
  node.rotation(t.rotation);
}

async function addAssetLayer(asset, category) {
  if (category === 'shapes') {
    const existing = getShapeLayer();
    const preserved = existing ? preserveTransform(existing.node) : null;
    if (existing) removeLayer(existing.uid, { skipSelect: true });
    await createLayer(asset, category, preserved);
    repositionGluedAddons();
    return;
  }

  if (category === 'addons') {
    const shape = getShapeLayer();
    const placement = shape ? getGluedAddonPlacement(asset, shape) : null;
    await createLayer(asset, category, placement);
    const layer = layers[layers.length - 1];
    layer.gluedAddon = true;
    layer.node.draggable(false);
    return;
  }

  await createLayer(asset, category, null);
}

async function createLayer(asset, category, preservedTransform) {
  if (asset.text_editable) {
    await createTextBannerLayer(asset, category, preservedTransform);
    return;
  }

  const url = ASSETS_BASE + asset.file;
  const img = await loadImage(url);
  const tintMode = asset.tint_mode || (asset.tintable ? 'shape' : null);
  const def = asset.default || {};
  let imageSource = img;
  if (asset.tintable && tintMode) {
    imageSource = applyTintToImage(img, tintMode);
  }
  const iw = imageSource.width;
  const ih = imageSource.height;
  const identPlacement =
    category === 'identifiers' && !preservedTransform ? getIdentifierPlacement(asset) : null;

  const node = new Konva.Image({
    image: imageSource,
    x: preservedTransform?.x ?? identPlacement?.x ?? def.x ?? manifest.artboard / 2,
    y: preservedTransform?.y ?? identPlacement?.y ?? def.y ?? manifest.artboard / 2,
    offsetX: iw / 2,
    offsetY: ih / 2,
    scaleX: preservedTransform?.scaleX ?? identPlacement?.scaleX ?? def.scale ?? 1,
    scaleY: preservedTransform?.scaleY ?? identPlacement?.scaleY ?? def.scale ?? 1,
    rotation: preservedTransform?.rotation ?? identPlacement?.rotation ?? def.rotation ?? 0,
    draggable: true,
    name: asset.id,
  });

  if (category === 'shapes') {
    layerGroup.add(node);
    node.moveToBottom();
  } else {
    layerGroup.add(node);
  }
  layerGroup.draw();

  const entry = {
    uid: uid(),
    meta: { ...asset, category, tint_mode: tintMode },
    node,
    tintable: !!asset.tintable,
    tintMode,
    imageUrl: url,
    layerType: 'image',
    gluedAddon: category === 'addons',
  };
  if (category === 'addons') node.draggable(false);
  layers.push(entry);
  if (category === 'shapes') bindShapeTransformListeners(entry);
  selectLayer(entry.uid);
  renderLayerList();
  highlightActiveAsset();
}

async function createTextBannerLayer(asset, category, preservedTransform) {
  const url = ASSETS_BASE + asset.file;
  const img = await loadImage(url);
  const tintMode = asset.tint_mode || 'shape';
  const canvas = applyTintToImage(img, tintMode);
  const def = asset.default || {};
  const iw = canvas.width;
  const ih = canvas.height;
  const bannerText = 'TEXT';
  const bannerFontSize = 28;
  const bannerBold = false;

  const imageNode = new Konva.Image({
    image: canvas,
    width: iw,
    height: ih,
    offsetX: iw / 2,
    offsetY: ih / 2,
  });
  const textNode = new Konva.Text({
    text: bannerText,
    fontFamily: 'Georgia, serif',
    fontSize: bannerFontSize,
    fontStyle: bannerBold ? 'bold' : 'normal',
    fill: borderColor,
    width: iw,
    height: ih,
    align: 'center',
    verticalAlign: 'middle',
    offsetX: iw / 2,
    offsetY: ih / 2,
    listening: true,
  });

  const shape = getShapeLayer();
  const gluedPlacement =
    !preservedTransform && shape ? getGluedAddonPlacement(asset, shape) : null;

  const group = new Konva.Group({
    x: preservedTransform?.x ?? gluedPlacement?.x ?? def.x ?? manifest.artboard / 2,
    y: preservedTransform?.y ?? gluedPlacement?.y ?? def.y ?? manifest.artboard / 2,
    scaleX: preservedTransform?.scaleX ?? gluedPlacement?.scaleX ?? def.scale ?? 1,
    scaleY: preservedTransform?.scaleY ?? gluedPlacement?.scaleY ?? def.scale ?? 1,
    rotation: preservedTransform?.rotation ?? gluedPlacement?.rotation ?? def.rotation ?? 0,
    draggable: false,
    name: asset.id,
  });
  group.add(imageNode);
  group.add(textNode);
  layerGroup.add(group);
  layerGroup.draw();

  const entry = {
    uid: uid(),
    meta: { ...asset, category, tint_mode: tintMode },
    node: group,
    imageNode,
    textNode,
    tintable: true,
    tintMode,
    imageUrl: url,
    layerType: 'text_banner',
    bannerText,
    bannerFontSize,
    bannerBold,
    gluedAddon: true,
  };
  layers.push(entry);
  selectLayer(entry.uid);
  renderLayerList();
  highlightActiveAsset();
}

function updateTextBannerLayer(layer) {
  if (layer.layerType !== 'text_banner') return;
  layer.textNode.text(layer.bannerText || '');
  layer.textNode.fontSize(layer.bannerFontSize || 28);
  layer.textNode.fontStyle(layer.bannerBold ? 'bold' : 'normal');
  layer.textNode.fill(borderColor);
  layerGroup.draw();
}

async function refreshTextBannerImage(layer) {
  const img = await loadImage(layer.imageUrl);
  const canvas = applyTintToImage(img, layer.tintMode);
  layer.imageNode.image(canvas);
  layer.textNode.fill(borderColor);
}

function removeLayer(layerUid, opts = {}) {
  const idx = layers.findIndex((l) => l.uid === layerUid);
  if (idx < 0) return;
  layers[idx].node.destroy();
  layers.splice(idx, 1);
  if (!opts.skipSelect && selectedUid === layerUid) selectLayer(null);
  layerGroup.draw();
  renderLayerList();
  highlightActiveAsset();
}

function renderLayerList() {
  const el = document.getElementById('layer-list');
  el.innerHTML = '';
  [...layers].reverse().forEach((layer) => {
    const div = document.createElement('div');
    const isShape = layer.meta.category === 'shapes';
    div.className =
      'layer-item' +
      (layer.uid === selectedUid ? ' selected' : '') +
      (isShape ? ' shape-layer' : '');
    let label = layer.meta.label;
    if (isShape) label += ' (shape)';
    else if (layer.layerType === 'text_banner' && layer.bannerText) label += `: ${layer.bannerText}`;
    else if (layer.layerType === 'drawing') label = layer.meta.label;
    div.innerHTML = `<span>${label}</span>`;
    if (!isShape) {
      const del = document.createElement('button');
      del.type = 'button';
      del.textContent = '×';
      del.title = 'Remove layer';
      del.onclick = (e) => {
        e.stopPropagation();
        removeLayer(layer.uid);
      };
      div.appendChild(del);
    }
    div.onclick = () => selectLayer(layer.uid);
    el.appendChild(div);
  });
}

function highlightActiveAsset() {
  const shape = getShapeLayer();
  const activeId =
    activeCategory === 'shapes' && shape ? shape.meta.id : selectedUid ? layers.find((l) => l.uid === selectedUid)?.meta.id : null;

  document.querySelectorAll('.asset-row').forEach((row) => {
    row.classList.toggle('active', row.dataset.assetId === activeId);
  });
}

function buildCategoryTabs() {
  const tabs = document.getElementById('cat-tabs');
  tabs.innerHTML = '';
  const order = ['shapes', 'identifiers', 'classes', 'addons', 'custom_features', 'pptx_curated'];

  order.forEach((cat) => {
    if (!manifest[cat]?.length) return;
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'cat-tab' + (cat === activeCategory ? ' active' : '');
    btn.textContent = CATEGORY_LABELS[cat] || cat;
    btn.dataset.cat = cat;
    btn.onclick = () => {
      activeCategory = cat;
      tabs.querySelectorAll('.cat-tab').forEach((b) => b.classList.toggle('active', b.dataset.cat === cat));
      renderAssetPicker(cat);
    };
    tabs.appendChild(btn);
  });
  renderAssetPicker(activeCategory);
}

function renderAssetPicker(category) {
  const picker = document.getElementById('asset-picker');
  picker.innerHTML = '';
  picker.classList.toggle('list-mode', pickerMode === 'list');
  picker.classList.toggle('gallery-mode', pickerMode === 'gallery');

  (manifest[category] || []).forEach((asset) => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'asset-row';
    btn.dataset.assetId = asset.id;
    btn.title = asset.label;

    const name = document.createElement('span');
    name.className = 'asset-name';
    name.textContent = asset.label;

    const thumb = document.createElement('span');
    thumb.className = 'asset-thumb';
    const img = document.createElement('img');
    img.src = ASSETS_BASE + asset.file;
    img.alt = asset.label;
    thumb.appendChild(img);

    btn.append(name, thumb);
    btn.onclick = () => addAssetLayer(asset, category);
    picker.appendChild(btn);
  });
  highlightActiveAsset();
}

async function refreshAllLayerColors() {
  const tinted = layers.filter((l) => l.tintable && l.tintMode);
  const drawings = layers.filter((l) => l.layerType === 'drawing');
  if (!tinted.length && !drawings.length) return;

  await Promise.all(
    tinted.map(async (layer) => {
      if (layer.layerType === 'text_banner') {
        await refreshTextBannerImage(layer);
        return;
      }
      const img = await loadImage(layer.imageUrl);
      const canvas = applyTintToImage(img, layer.tintMode);
      layer.node.image(canvas);
      layer.node.offsetX(canvas.width / 2);
      layer.node.offsetY(canvas.height / 2);
    }),
  );

  drawings.forEach((layer) => applyDrawingStyle(layer.node, layer));
  layerGroup.draw();
}

function applyDrawingStyle(node, layer) {
  const color = drawColor;
  const strokeW = ptToPx(layer?.strokePt ?? drawStrokePt);
  if (node instanceof Konva.Line) {
    node.stroke(color);
    node.strokeWidth(strokeW);
    node.strokeScaleEnabled(false);
    if (node.closed()) node.fill(color);
  } else if (node instanceof Konva.Path) {
    node.stroke(color);
    node.strokeWidth(strokeW);
    node.strokeScaleEnabled(false);
  } else if (node instanceof Konva.Circle) {
    node.stroke(color);
    node.strokeWidth(strokeW);
    node.strokeScaleEnabled(false);
    node.fill(color);
  } else if (node instanceof Konva.RegularPolygon) {
    node.stroke(color);
    node.strokeWidth(strokeW);
    node.strokeScaleEnabled(false);
    node.fill(color);
  }
}

function curveControlPoint(x1, y1, x2, y2, bend) {
  const mx = (x1 + x2) / 2;
  const my = (y1 + y2) / 2;
  const dx = x2 - x1;
  const dy = y2 - y1;
  const len = Math.hypot(dx, dy) || 1;
  return {
    cx: mx - (dy / len) * len * bend * 0.5,
    cy: my + (dx / len) * len * bend * 0.5,
  };
}

function buildCurvePath(x1, y1, x2, y2, bend) {
  const { cx, cy } = curveControlPoint(x1, y1, x2, y2, bend);
  return `M ${x1} ${y1} Q ${cx} ${cy} ${x2} ${y2}`;
}

function getDrawPointer() {
  const pos = stage.getPointerPosition();
  return pos ? { x: pos.x, y: pos.y } : null;
}

function snapDrawEnd(start, end, shiftKey) {
  if (!shiftKey) return end;
  const dx = end.x - start.x;
  const dy = end.y - start.y;
  if (Math.abs(dx) >= Math.abs(dy)) return { x: end.x, y: start.y };
  return { x: start.x, y: end.y };
}

function createDrawingPreview(tool, start, end, strokePt = drawStrokePt) {
  const strokeW = ptToPx(strokePt);
  const strokeOpts = {
    stroke: drawColor,
    strokeWidth: strokeW,
    strokeScaleEnabled: false,
    perfectDrawEnabled: false,
    lineCap: 'butt',
    lineJoin: 'miter',
    listening: false,
  };
  if (tool === 'line') {
    return new Konva.Line({
      points: [start.x, start.y, end.x, end.y],
      ...strokeOpts,
    });
  }
  if (tool === 'curve') {
    return new Konva.Path({
      data: buildCurvePath(start.x, start.y, end.x, end.y, curveBend),
      ...strokeOpts,
      lineCap: 'round',
    });
  }
  if (tool === 'circle') {
    const rx = end.x - start.x;
    const ry = end.y - start.y;
    const radius = Math.max(4, Math.hypot(rx, ry));
    return new Konva.Circle({
      x: start.x,
      y: start.y,
      radius,
      ...strokeOpts,
      fill: drawColor,
    });
  }
  if (tool === 'triangle') {
    const left = Math.min(start.x, end.x);
    const right = Math.max(start.x, end.x);
    const top = Math.min(start.y, end.y);
    const bottom = Math.max(start.y, end.y);
    const apexX = (left + right) / 2;
    return new Konva.Line({
      points: [apexX, top, right, bottom, left, bottom],
      ...strokeOpts,
      fill: drawColor,
      closed: true,
    });
  }
  return null;
}

function finalizeDrawingNode(tool, start, end) {
  if (Math.hypot(end.x - start.x, end.y - start.y) < 6) return null;
  const preview = createDrawingPreview(tool, start, end);
  if (!preview) return null;
  preview.listening(true);
  preview.draggable(true);
  preview.name(`draw-${tool}`);
  return preview;
}

function addDrawingLayer(node, tool) {
  const labels = {
    line: 'Line',
    curve: 'Curved line',
    circle: 'Circle',
    triangle: 'Triangle',
  };
  layerGroup.add(node);
  const entry = {
    uid: uid(),
    meta: { id: `draw-${tool}`, label: labels[tool] || 'Drawing', category: 'drawing' },
    node,
    tintable: true,
    tintMode: 'border',
    layerType: 'drawing',
    strokePt: drawStrokePt,
  };
  applyDrawingStyle(node, entry);
  layers.push(entry);
  layerGroup.draw();
  selectLayer(entry.uid);
}

function initDrawingHandlers() {
  stage.on('mousedown touchstart', (e) => {
    if (activeDrawTool === 'select') return;
    if (!isCanvasBackground(e.target)) return;
    const pos = getDrawPointer();
    if (!pos) return;
    drawingSession = { tool: activeDrawTool, start: { x: pos.x, y: pos.y }, preview: null };
    e.evt.preventDefault();
  });

  stage.on('mousemove touchmove', (e) => {
    if (!drawingSession) return;
    const raw = getDrawPointer();
    if (!raw) return;
    const pos = snapDrawEnd(drawingSession.start, raw, e.evt?.shiftKey);
    drawingSession.preview?.destroy();
    const preview = createDrawingPreview(drawingSession.tool, drawingSession.start, pos);
    if (preview) {
      layerGroup.add(preview);
      drawingSession.preview = preview;
      layerGroup.draw();
    }
  });

  stage.on('mouseup touchend', (e) => {
    if (!drawingSession) return;
    const raw = getDrawPointer() || drawingSession.start;
    const pos = snapDrawEnd(drawingSession.start, raw, e.evt?.shiftKey);
    drawingSession.preview?.destroy();
    const node = finalizeDrawingNode(drawingSession.tool, drawingSession.start, pos);
    if (node) addDrawingLayer(node, drawingSession.tool);
    drawingSession = null;
    layerGroup.draw();
  });
}

function setActiveDrawTool(tool) {
  activeDrawTool = tool;
  document.querySelectorAll('.draw-tool').forEach((btn) => {
    btn.classList.toggle('active', btn.dataset.drawTool === tool);
  });
  document.getElementById('curve-control').classList.toggle('hidden', tool !== 'curve');
  if (tool !== 'select') selectLayer(null);
}

function initDrawToolbox() {
  document.querySelectorAll('.draw-tool').forEach((btn) => {
    btn.addEventListener('click', () => setActiveDrawTool(btn.dataset.drawTool));
  });
  document.getElementById('curve-bend').addEventListener('input', (e) => {
    curveBend = parseInt(e.target.value, 10) / 100;
  });
  document.getElementById('draw-color').addEventListener('input', (e) => {
    drawColor = e.target.value;
    refreshAllLayerColors();
  });
  document.getElementById('draw-stroke-pt').addEventListener('change', (e) => {
    drawStrokePt = parseFloat(e.target.value) || 2;
    const layer = layers.find((l) => l.uid === selectedUid);
    if (layer?.layerType === 'drawing') {
      layer.strokePt = drawStrokePt;
      applyDrawingStyle(layer.node, layer);
      layerGroup.draw();
    }
  });
}

function initResizeModeControls() {
  const panel = document.getElementById('resize-mode-controls');
  if (!panel) return;
  panel.querySelectorAll('[data-resize-mode]').forEach((btn) => {
    btn.addEventListener('click', () => {
      resizeMode = btn.dataset.resizeMode === 'free' ? 'free' : 'proportional';
      panel.querySelectorAll('[data-resize-mode]').forEach((b) => {
        b.classList.toggle('active', b.dataset.resizeMode === resizeMode);
      });
      const hit = layers.find((l) => l.uid === selectedUid);
      if (hit) applyTransformerToLayer(hit);
    });
  });
}

function initBannerControls() {
  const textInput = document.getElementById('banner-text');
  const sizeInput = document.getElementById('banner-font-size');

  const applyBannerEdits = () => {
    const layer = layers.find((l) => l.uid === selectedUid);
    if (layer?.layerType !== 'text_banner') return;
    layer.bannerText = textInput.value;
    layer.bannerFontSize = Math.min(120, Math.max(8, parseInt(sizeInput.value, 10) || 28));
    sizeInput.value = String(layer.bannerFontSize);
    updateTextBannerLayer(layer);
    renderLayerList();
  };

  textInput.addEventListener('input', applyBannerEdits);
  sizeInput.addEventListener('input', applyBannerEdits);
  document.getElementById('banner-bold').addEventListener('change', () => {
    const layer = layers.find((l) => l.uid === selectedUid);
    if (layer?.layerType !== 'text_banner') return;
    layer.bannerBold = document.getElementById('banner-bold').checked;
    updateTextBannerLayer(layer);
  });
}

function findManifestAsset(category, assetId) {
  return (manifest[category] || []).find((a) => a.id === assetId) || null;
}

function serializeLayerState(layer) {
  const t = preserveTransform(layer.node);
  const base = {
    category: layer.meta.category,
    assetId: layer.meta.id,
    layerType: layer.layerType || 'image',
    transform: t,
  };
  if (layer.layerType === 'text_banner') {
    base.bannerText = layer.bannerText || '';
    base.bannerFontSize = layer.bannerFontSize || 28;
    base.bannerBold = !!layer.bannerBold;
  }
  if (layer.gluedAddon) base.gluedAddon = true;
  if (layer.layerType === 'drawing') {
    base.drawTool = layer.meta.id.replace(/^draw-/, '');
    base.strokePt = layer.strokePt ?? drawStrokePt;
    const node = layer.node;
    if (node instanceof Konva.Line) {
      base.points = node.points();
      base.closed = node.closed();
    } else if (node instanceof Konva.Path) {
      base.pathData = node.data();
    } else if (node instanceof Konva.Circle) {
      base.circle = { x: node.x(), y: node.y(), radius: node.radius() };
    }
  }
  return base;
}

function serializeCanvasState() {
  return {
    fillColor,
    borderColor,
    drawColor,
    drawStrokePt,
    exportName: document.getElementById('export-name').value.trim() || 'unit-icon',
    layers: layers.map(serializeLayerState),
  };
}

function readIconHistory() {
  try {
    const raw = localStorage.getItem(HISTORY_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function writeIconHistory(entries) {
  localStorage.setItem(HISTORY_KEY, JSON.stringify(entries.slice(0, HISTORY_MAX)));
}

function formatHistoryTime(ts) {
  try {
    return new Date(ts).toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    });
  } catch {
    return '';
  }
}

function renderHistoryList() {
  const el = document.getElementById('history-list');
  if (!el) return;
  const entries = readIconHistory();
  el.innerHTML = '';
  if (!entries.length) {
    const empty = document.createElement('p');
    empty.className = 'hint';
    empty.style.padding = '0 0.75rem';
    empty.textContent = 'No exports yet — download a PNG to save one here.';
    el.appendChild(empty);
    return;
  }
  entries.forEach((entry) => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'history-item';
    btn.title = 'Restore this icon';
    const img = document.createElement('img');
    img.className = 'history-thumb';
    img.src = entry.thumbnail || '';
    img.alt = entry.name || 'Recent icon';
    const meta = document.createElement('span');
    meta.className = 'history-meta';
    const name = document.createElement('span');
    name.className = 'history-name';
    name.textContent = entry.name || 'unit-icon';
    const time = document.createElement('span');
    time.className = 'history-time';
    time.textContent = formatHistoryTime(entry.savedAt);
    meta.append(name, time);
    btn.append(img, meta);
    btn.onclick = () => restoreFromHistory(entry);
    el.appendChild(btn);
  });
}

async function saveToHistory(exportDataUrl, safeName) {
  const thumbnail =
    exportDataUrl || (await buildExportDataUrl(64));

  const entry = {
    id: `hist-${Date.now()}`,
    name: safeName,
    savedAt: Date.now(),
    thumbnail,
    state: serializeCanvasState(),
  };
  const next = [entry, ...readIconHistory().filter((h) => h.id !== entry.id)].slice(0, HISTORY_MAX);
  writeIconHistory(next);
  renderHistoryList();
}

async function restoreDrawingLayer(saved) {
  const strokePt = saved.strokePt ?? drawStrokePt;
  let node = null;
  if (saved.drawTool === 'line' || saved.drawTool === 'triangle') {
    node = new Konva.Line({
      points: saved.points || [],
      closed: !!saved.closed,
      draggable: true,
      name: `draw-${saved.drawTool}`,
    });
  } else if (saved.drawTool === 'curve') {
    node = new Konva.Path({
      data: saved.pathData || '',
      draggable: true,
      name: 'draw-curve',
      lineCap: 'round',
    });
  } else if (saved.drawTool === 'circle' && saved.circle) {
    node = new Konva.Circle({
      x: saved.circle.x,
      y: saved.circle.y,
      radius: saved.circle.radius,
      draggable: true,
      name: 'draw-circle',
    });
  }
  if (!node) return;

  const labels = {
    line: 'Line',
    curve: 'Curved line',
    circle: 'Circle',
    triangle: 'Triangle',
  };
  layerGroup.add(node);
  const entry = {
    uid: uid(),
    meta: { id: `draw-${saved.drawTool}`, label: labels[saved.drawTool] || 'Drawing', category: 'drawing' },
    node,
    tintable: true,
    tintMode: 'border',
    layerType: 'drawing',
    strokePt,
  };
  applyDrawingStyle(node, entry);
  if (saved.transform) applyTransform(node, saved.transform);
  layers.push(entry);
}

async function restoreAssetLayer(saved) {
  const asset = findManifestAsset(saved.category, saved.assetId);
  if (!asset) return;
  if (saved.gluedAddon && saved.category === 'addons') {
    const shape = getShapeLayer();
    const placement = shape ? getGluedAddonPlacement(asset, shape) : saved.transform;
    await createLayer(asset, saved.category, placement);
    const layer = layers[layers.length - 1];
    layer.gluedAddon = true;
    layer.node.draggable(false);
    return;
  }
  if (asset.text_editable) {
    await createTextBannerLayer(asset, saved.category, saved.transform);
    const layer = layers[layers.length - 1];
    if (layer?.layerType === 'text_banner') {
      layer.gluedAddon = true;
      layer.node.draggable(false);
      layer.bannerText = saved.bannerText ?? layer.bannerText;
      layer.bannerFontSize = saved.bannerFontSize ?? layer.bannerFontSize;
      layer.bannerBold = !!saved.bannerBold;
      updateTextBannerLayer(layer);
      if (!saved.transform) {
        const shape = getShapeLayer();
        if (shape) applyTransform(layer.node, getGluedAddonPlacement(asset, shape));
      }
    }
    return;
  }
  await createLayer(asset, saved.category, saved.transform);
}

async function restoreFromHistory(entry) {
  if (!entry?.state) return;
  const { state } = entry;
  clearCanvas();
  fillColor = state.fillColor || fillColor;
  borderColor = state.borderColor || borderColor;
  drawColor = state.drawColor || drawColor;
  drawStrokePt = state.drawStrokePt ?? drawStrokePt;
  document.getElementById('fill-color').value = fillColor;
  document.getElementById('border-color').value = borderColor;
  document.getElementById('draw-color').value = drawColor;
  document.getElementById('draw-stroke-pt').value = String(drawStrokePt);
  if (state.exportName) document.getElementById('export-name').value = state.exportName;

  const shapeLayers = (state.layers || []).filter((l) => l.category === 'shapes');
  const otherLayers = (state.layers || []).filter((l) => l.category !== 'shapes');

  for (const saved of shapeLayers) await restoreAssetLayer(saved);
  for (const saved of otherLayers) {
    if (saved.layerType === 'drawing') await restoreDrawingLayer(saved);
    else await restoreAssetLayer(saved);
  }

  selectLayer(null);
  layerGroup.draw();
  renderLayerList();
  highlightActiveAsset();
}

async function exportPng() {
  const size = parseInt(document.getElementById('export-size').value, 10) || 128;
  const nameInput = document.getElementById('export-name').value.trim() || 'unit-icon';
  const safeName = nameInput.replace(/[^a-zA-Z0-9._-]+/g, '-').replace(/^-+|-+$/g, '') || 'unit-icon';

  const dataUrl = await buildExportDataUrl(size);
  await saveToHistory(dataUrl, safeName);

  const a = document.createElement('a');
  a.href = dataUrl;
  a.download = `${safeName}.png`;
  a.click();
}

function clearCanvas() {
  layers.forEach((l) => l.node.destroy());
  layers = [];
  drawingSession = null;
  selectLayer(null);
  layerGroup.draw();
  highlightActiveAsset();
}

function applyDefaultColors() {
  const defs = manifest?.defaults || {};
  fillColor = defs.fill || '#80ffff';
  borderColor = defs.border || '#000000';
  document.getElementById('fill-color').value = fillColor;
  document.getElementById('border-color').value = borderColor;
}

async function seedDefault() {
  applyDefaultColors();
  const defs = manifest?.defaults || {};
  const shape =
    manifest.shapes?.find((s) => s.id === defs.shape_id) ||
    manifest.shapes?.find((s) => s.id === 'friendly_generic_rectangle');
  const ident =
    manifest.identifiers?.find((s) => s.id === defs.identifier_id) ||
    manifest.identifiers?.find((s) => s.id === 'infantry');
  if (shape) await addAssetLayer(shape, 'shapes');
  if (ident) await addAssetLayer(ident, 'identifiers');
}

function buildTacticalGrid() {
  const grid = document.getElementById('tactical-grid');
  grid.innerHTML = '';
  (manifest.tactical_ops || []).forEach((asset) => {
    const card = document.createElement('div');
    card.className = 'tactical-card';
    const thumbWrap = document.createElement('div');
    thumbWrap.className = 'tactical-thumb';
    const img = document.createElement('img');
    img.src = ASSETS_BASE + asset.file;
    img.alt = asset.label;
    thumbWrap.appendChild(img);
    const p = document.createElement('p');
    p.textContent = asset.label;
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'btn btn-primary';
    btn.textContent = 'Download PNG';
    btn.onclick = async () => {
      const im = await loadImage(ASSETS_BASE + asset.file);
      const canvas = document.createElement('canvas');
      canvas.width = im.width;
      canvas.height = im.height;
      canvas.getContext('2d').drawImage(im, 0, 0);
      const a = document.createElement('a');
      a.href = canvas.toDataURL('image/png');
      a.download = `${asset.id}.png`;
      a.click();
    };
    card.append(thumbWrap, p, btn);
    grid.appendChild(card);
  });
}

let massShapeId = 'friendly_generic_rectangle';
let massFillColor = '#80ffff';
let massBorderColor = '#000000';

function canvasAtExportSize(sourceCanvas, exportSize) {
  const artboard = manifest.artboard || 512;
  const out = document.createElement('canvas');
  out.width = exportSize;
  out.height = exportSize;
  const ctx = out.getContext('2d');
  const scale = exportSize / artboard;
  ctx.scale(scale, scale);
  ctx.drawImage(sourceCanvas, 0, 0);
  return out;
}

function getMassShapeAsset() {
  return (
    manifest.shapes?.find((s) => s.id === massShapeId) ||
    manifest.shapes?.find((s) => s.id === 'friendly_generic_rectangle')
  );
}

async function renderComposedIcon({
  shapeAsset,
  identifierAsset = null,
  classAsset = null,
  addonAsset = null,
  fill = massFillColor,
  border = massBorderColor,
  artboard = null,
}) {
  const board = artboard || manifest.artboard || 512;
  const canvas = document.createElement('canvas');
  canvas.width = board;
  canvas.height = board;
  const ctx = canvas.getContext('2d');
  const def = shapeAsset.default || {};
  const shapeScale = def.scale ?? 0.75;
  const cx = def.x ?? board / 2;
  const cy = def.y ?? board / 2 + 20;
  const sw = shapeAsset.width * shapeScale;
  const sh = shapeAsset.height * shapeScale;
  const shapeX = cx - sw / 2;
  const shapeY = cy - sh / 2;

  const shapeImg = await loadImage(ASSETS_BASE + shapeAsset.file);
  const composedShape = composeShapeCanvas(shapeImg, fill, border);
  ctx.drawImage(composedShape, shapeX, shapeY, sw, sh);

  if (identifierAsset) {
    const idImg = await loadImage(ASSETS_BASE + identifierAsset.file);
    const idTinted = tintSolid(idImg, border);
    const idDef = identifierAsset.default || {};
    const idScale = idDef.scale ?? 0.75;
    const idW = identifierAsset.width * idScale;
    const idH = identifierAsset.height * idScale;
    const idX = (idDef.x ?? cx) - idW / 2;
    const idY = (idDef.y ?? cy) - idH / 2;
    ctx.drawImage(idTinted, idX, idY, idW, idH);
  }

  if (classAsset) {
    const classImg = await loadImage(ASSETS_BASE + classAsset.file);
    const classTinted = tintSolid(classImg, border);
    const classDef = classAsset.default || {};
    const classScale = classDef.scale ?? 0.55;
    const classW = classAsset.width * classScale;
    const classH = classAsset.height * classScale;
    const classX = (classDef.x ?? cx) - classW / 2;
    const classY = (classDef.y ?? cy) - classH / 2;
    ctx.drawImage(classTinted, classX, classY, classW, classH);
  }

  if (addonAsset) {
    const addonImg = await loadImage(ASSETS_BASE + addonAsset.file);
    let addonSource = addonImg;
    if (addonAsset.tint_mode === 'shape_preserve_white') {
      addonSource = composeShapePreserveWhite(addonImg, fill, border);
    } else if (addonAsset.tint_mode === 'shape') {
      addonSource = composeShapeCanvas(addonImg, fill, border);
    } else if (addonAsset.tintable) {
      addonSource = tintSolid(addonImg, addonAsset.tint_mode === 'fill' ? fill : border);
    }
    const frame = {
      cx,
      cy,
      w: sw,
      h: sh,
      rotation: 0,
      left: shapeX,
      right: shapeX + sw,
      top: shapeY,
      bottom: shapeY + sh,
    };
    const placement = getGluedAddonPlacement(addonAsset, frame);
    const aw = addonAsset.width * placement.scaleX;
    const ah = addonAsset.height * placement.scaleY;
    ctx.drawImage(addonSource, placement.x - aw / 2, placement.y - ah / 2, aw, ah);
  }

  return canvas;
}

async function refreshMassPreview() {
  const preview = document.getElementById('mass-preview');
  const status = document.getElementById('mass-export-status');
  if (!preview) return;
  const shapeAsset = getMassShapeAsset();
  const identAsset =
    manifest.identifiers?.find((i) => i.id === 'infantry') || manifest.identifiers?.[0];
  if (!shapeAsset || !identAsset) return;
  const canvas = await renderComposedIcon({ shapeAsset, identifierAsset: identAsset });
  preview.src = canvas.toDataURL('image/png');
  if (status) status.textContent = '';
}

function buildMassShapePicker() {
  const sel = document.getElementById('mass-shape');
  if (!sel) return;
  sel.innerHTML = '';
  (manifest.shapes || []).forEach((shape) => {
    const opt = document.createElement('option');
    opt.value = shape.id;
    opt.textContent = shape.label;
    sel.appendChild(opt);
  });
  sel.value = massShapeId;
}

async function exportMassPackage() {
  const btn = document.getElementById('btn-mass-export');
  const status = document.getElementById('mass-export-status');
  if (!window.JSZip) {
    if (status) status.textContent = 'ZIP library failed to load.';
    return;
  }
  const shapeAsset = getMassShapeAsset();
  if (!shapeAsset) return;

  const exportSize = parseInt(document.getElementById('mass-export-size')?.value, 10) || 128;
  btn.disabled = true;
  if (status) status.textContent = 'Building package…';

  try {
    const zip = new JSZip();
    const icons = zip.folder('icons');
    const tactical = zip.folder('tactical_ops');
    const total =
      (manifest.identifiers?.length || 0) +
      2 +
      (manifest.classes?.length || 0) +
      (manifest.tactical_ops?.length || 0);
    let done = 0;

    const addPng = (folder, name, canvas) => {
      const scaled = canvasAtExportSize(canvas, exportSize);
      const data = scaled.toDataURL('image/png').split(',')[1];
      folder.file(name, data, { base64: true });
      done++;
      if (status) status.textContent = `Building package… ${done}/${total}`;
    };

    for (const ident of manifest.identifiers || []) {
      const canvas = await renderComposedIcon({ shapeAsset, identifierAsset: ident });
      addPng(icons, `${ident.id}.png`, canvas);
    }

    for (const addonId of ['mercenary', 'hq_flag_add_on']) {
      const addon = manifest.addons?.find((a) => a.id === addonId);
      if (!addon) continue;
      const canvas = await renderComposedIcon({ shapeAsset, addonAsset: addon });
      addPng(icons, `${addon.id}.png`, canvas);
    }

    for (const cls of manifest.classes || []) {
      const canvas = await renderComposedIcon({ shapeAsset, classAsset: cls });
      addPng(icons, `${cls.id}.png`, canvas);
    }

    for (const tac of manifest.tactical_ops || []) {
      const im = await loadImage(ASSETS_BASE + tac.file);
      const c = document.createElement('canvas');
      c.width = im.width;
      c.height = im.height;
      c.getContext('2d').drawImage(im, 0, 0);
      const data = c.toDataURL('image/png').split(',')[1];
      tactical.file(`${tac.id}.png`, data, { base64: true });
      done++;
      if (status) status.textContent = `Building package… ${done}/${total}`;
    }

    const blob = await zip.generateAsync({ type: 'blob' });
    const slug = shapeAsset.id.replace(/[^a-z0-9._-]+/gi, '-');
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `icon-package-${slug}.zip`;
    a.click();
    URL.revokeObjectURL(a.href);
    if (status) status.textContent = `Exported ${total} files.`;
  } catch (err) {
    if (status) status.textContent = `Export failed: ${err.message}`;
  } finally {
    btn.disabled = false;
  }
}

function initMassBuilder() {
  const defs = manifest?.defaults || {};
  massShapeId = defs.shape_id || massShapeId;
  massFillColor = defs.fill || massFillColor;
  massBorderColor = defs.border || massBorderColor;

  buildMassShapePicker();
  const shapeSel = document.getElementById('mass-shape');
  const fillInput = document.getElementById('mass-fill-color');
  const borderInput = document.getElementById('mass-border-color');
  if (fillInput) fillInput.value = massFillColor;
  if (borderInput) borderInput.value = massBorderColor;

  shapeSel?.addEventListener('change', () => {
    massShapeId = shapeSel.value;
    refreshMassPreview();
  });
  fillInput?.addEventListener('input', () => {
    massFillColor = fillInput.value;
    refreshMassPreview();
  });
  borderInput?.addEventListener('input', () => {
    massBorderColor = borderInput.value;
    refreshMassPreview();
  });
  document.getElementById('btn-mass-export')?.addEventListener('click', exportMassPackage);
  refreshMassPreview();
}

function initViewTabs() {
  document.querySelectorAll('.topbar .tab').forEach((tab) => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('.topbar .tab').forEach((t) => t.classList.remove('active'));
      tab.classList.add('active');
      const view = tab.dataset.view;
      document.getElementById('compose-view').classList.toggle('hidden', view !== 'compose');
      document.getElementById('mass-view').classList.toggle('hidden', view !== 'mass');
      document.getElementById('tactical-view').classList.toggle('active', view === 'tactical');
      if (view === 'mass') refreshMassPreview();
    });
  });
}

function initPickerToggle() {
  const listBtn = document.getElementById('view-list');
  const galleryBtn = document.getElementById('view-gallery');
  listBtn.addEventListener('click', () => {
    pickerMode = 'list';
    listBtn.classList.add('active');
    galleryBtn.classList.remove('active');
    renderAssetPicker(activeCategory);
  });
  galleryBtn.addEventListener('click', () => {
    pickerMode = 'gallery';
    galleryBtn.classList.add('active');
    listBtn.classList.remove('active');
    renderAssetPicker(activeCategory);
  });
}

async function init() {
  await loadManifest();
  initStage();
  buildCategoryTabs();
  buildTacticalGrid();
  initViewTabs();
  initMassBuilder();
  initPickerToggle();
  initDrawToolbox();
  initBannerControls();
  initResizeModeControls();

  document.getElementById('fill-color').addEventListener('input', (e) => {
    fillColor = e.target.value;
    refreshAllLayerColors();
  });
  document.getElementById('border-color').addEventListener('input', (e) => {
    borderColor = e.target.value;
    refreshAllLayerColors();
  });
  document.getElementById('draw-color').value = drawColor;
  document.getElementById('btn-export').addEventListener('click', exportPng);
  document.getElementById('btn-clear').addEventListener('click', clearCanvas);
  renderHistoryList();

  await seedDefault();
}

init().catch((err) => {
  document.body.innerHTML = `<p style="color:#f87171;padding:2rem">Icon builder failed to load: ${err.message}</p>`;
});