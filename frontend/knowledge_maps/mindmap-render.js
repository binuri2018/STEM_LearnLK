/**
 * Radial mind-map renderer (browser only — needs `window.d3` + `window.MindMapModel`).
 *
 * Pure graph/layout maths live in `mindmap-model.js` so they can be unit-tested
 * under Node; this file is the d3 drawing layer and is only exercised in a real
 * browser. It still `require()`s cleanly (every entry point guards `d3`), so a
 * headless smoke test can assert the public API shape.
 *
 * window.MindMapRender = {
 *   render(data, opts), showLoading(opts), showError(opts, message),
 *   fit(id?), zoomBy(f, id?), zoomReset(id?), collapseAll(id?), expandAll(id?),
 *   exportSVG(id?), exportPNG(id?), exportJSON(id?), destroy(id?)
 * }
 * opts = { svgId, container?, onConceptClick?, onZoom?(pct), onRendered?(info) }
 */
(function mindMapRenderModule(root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.MindMapRender = api;
})(typeof window !== "undefined" ? window : globalThis, function buildMindMapRender() {
  "use strict";

  const d3 = (typeof window !== "undefined" && window.d3) || null;
  const DOC = typeof document !== "undefined" ? document : null;
  const model = () => (typeof window !== "undefined" && window.MindMapModel) || null;

  const SVG_NS = "http://www.w3.org/2000/svg";
  const CHIP_H = 26;
  const ROOT_CHIP_H = 34;
  const MAX_LABEL = 26;
  const ZOOM_MIN = 0.3;
  const ZOOM_MAX = 2.5;

  const instances = new Map(); // svgId -> instance
  let lastId = null;

  /* ── small DOM helpers ─────────────────────────────────────────────────── */

  function containerOf(opts) {
    if (opts.container) return opts.container;
    if (!DOC) return null;
    const svg = DOC.getElementById(opts.svgId);
    return svg ? svg.parentElement : null;
  }

  function placeholderIn(container) {
    let ph = container.querySelector(".mindmap-placeholder");
    if (!ph) {
      ph = document.createElement("div");
      ph.className = "mindmap-placeholder";
      container.appendChild(ph);
    }
    return ph;
  }

  function setState(container, kind, iconHtml, message) {
    if (!container || !DOC) return;
    const ph = placeholderIn(container);
    ph.className = "mindmap-placeholder mindmap-placeholder--" + kind;
    ph.style.display = "flex";
    ph.innerHTML =
      (kind === "loading"
        ? '<span class="spinner" aria-hidden="true"></span>'
        : '<span aria-hidden="true">' + iconHtml + "</span>") +
      "<p>" + message + "</p>";
  }

  function hideState(container) {
    const ph = container.querySelector(".mindmap-placeholder");
    if (ph) ph.style.display = "none";
  }

  function truncate(label) {
    const s = String(label || "");
    return s.length > MAX_LABEL ? s.slice(0, MAX_LABEL - 1).trimEnd() + "…" : s;
  }

  function chipWidth(label, isRoot) {
    const est = truncate(label).length * (isRoot ? 8.4 : 7) + (isRoot ? 34 : 24);
    return Math.max(isRoot ? 90 : 54, Math.min(isRoot ? 240 : 190, Math.round(est)));
  }

  function saveBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 0);
  }

  function resolve(id) {
    return instances.get(id || lastId) || null;
  }

  /* ── collapse state ───────────────────────────────────────────────────── */

  function collapse(d) {
    if (d.children) {
      d._children = d.children;
      d._children.forEach(collapse);
      d.children = null;
    }
  }
  function expand(d) {
    if (d._children) {
      d.children = d._children;
      d._children = null;
    }
    (d.children || []).forEach(expand);
  }
  function toggle(d) {
    if (d.children) { d._children = d.children; d.children = null; }
    else if (d._children) { d.children = d._children; d._children = null; }
  }

  /* ── layout ───────────────────────────────────────────────────────────── */

  function layout(inst) {
    const { hierarchy } = inst;
    // Fixed ring spacing (not viewport-derived) so chips never crowd the centre;
    // fit() zooms the finished map to the container afterwards.
    const maxDepth = Math.max(1, ...hierarchy.descendants().map((d) => d.depth));
    const RING = Math.max(115, 192 - maxDepth * 18); // tighter rings as the tree deepens
    const ROT = Math.PI / 7; // straddle the vertical so no branch runs dead up/down
    d3.tree()
      .size([2 * Math.PI, RING * maxDepth])
      .separation((a, b) => {
        const base = a.parent === b.parent ? 1 : 1.7;
        return (base * (a.depth <= 1 ? 2.4 : 1.4)) / a.depth;
      })(hierarchy);

    inst.pos = new Map();
    hierarchy.each((d) => {
      let [x, y] = d3.pointRadial(d.depth === 0 ? 0 : d.x + ROT, d.y);
      // shove each chip outward along its ray by half its own width so the
      // chip body clears the parent instead of sitting on top of it
      if (d.depth > 0) {
        const r = Math.hypot(x, y) || 1;
        const push = chipWidth(d.data.label, false) / 2 + 6;
        x += (x / r) * push;
        y += (y / r) * push;
      }
      d._px = x;
      d._py = y;
      inst.pos.set(d.data.id, [x, y]);
    });
  }

  /* ── draw ─────────────────────────────────────────────────────────────── */

  function draw(inst) {
    layout(inst);
    const { gEl, hierarchy, colors, crossLinks, opts } = inst;
    const nodes = hierarchy.descendants();
    const links = hierarchy.links();
    const colorOf = (id) => colors.get(id) || "#6b7b8c";
    // All attributes are applied synchronously — a mind map that has not
    // finished a transition is still a correct mind map.

    // backbone links — gentle curve between the (offset) parent and child chips
    gEl.select(".mm-links")
      .selectAll("path")
      .data(links, (d) => d.target.data.id)
      .join("path")
      .attr("class", "mm-link")
      .attr("d", (d) => {
        const p = inst.pos.get(d.source.data.id);
        const c = inst.pos.get(d.target.data.id);
        const mx = ((p[0] + c[0]) / 2) * 0.86;
        const my = ((p[1] + c[1]) / 2) * 0.86;
        return `M${p[0]},${p[1]} Q${mx},${my} ${c[0]},${c[1]}`;
      })
      .attr("stroke", (d) => colorOf(d.target.data.id))
      .attr("stroke-width", (d) => Math.max(1.2, 3 - d.target.depth * 0.6));

    // cross-links (dashed, between rendered positions)
    const visible = new Set(nodes.map((n) => n.data.id));
    const xdata = crossLinks.filter((e) => visible.has(e.source) && visible.has(e.target));
    // bow cross-links *outward* (away from the root) so their labels don't pile
    // up over the centre
    const bow = (e, i) => ((inst.pos.get(e.source)[i] + inst.pos.get(e.target)[i]) / 2) * 1.28;
    gEl.select(".mm-xlinks")
      .selectAll("path")
      .data(xdata, (e) => e.source + "|" + e.target)
      .join("path")
      .attr("class", "mm-xlink")
      .attr("d", (e) => {
        const [x1, y1] = inst.pos.get(e.source);
        const [x2, y2] = inst.pos.get(e.target);
        return `M${x1},${y1} Q${bow(e, 0)},${bow(e, 1)} ${x2},${y2}`;
      });
    gEl.select(".mm-xlabels")
      .selectAll("text")
      .data(xdata, (e) => e.source + "|" + e.target)
      .join("text")
      .attr("class", "mm-xlink-label")
      .attr("text-anchor", "middle")
      .attr("x", (e) => bow(e, 0) * 0.94)
      .attr("y", (e) => bow(e, 1) * 0.94)
      .text((e) => e.relation || "related");

    // node chips
    const chip = gEl.select(".mm-nodes")
      .selectAll("g.mm-chip")
      .data(nodes, (d) => d.data.id)
      .join((enter) => {
        const g = enter.append("g").attr("class", "mm-chip");
        g.append("rect").attr("class", "mm-chip-box");
        g.append("text").attr("class", "mm-chip-label").attr("text-anchor", "middle").attr("dy", "0.32em");
        g.append("title");
        const nub = g.append("g").attr("class", "mm-nub");
        nub.append("circle").attr("r", 7);
        nub.append("text").attr("class", "mm-nub-sign").attr("text-anchor", "middle").attr("dy", "0.32em");
        return g;
      });

    chip
      .classed("mm-chip--root", (d) => d.depth === 0)
      .attr("data-id", (d) => d.data.id)
      .attr("transform", (d) => `translate(${d._px},${d._py})`)
      .on("mouseenter", (event, d) => highlightPath(inst, d))
      .on("mouseleave", () => clearHighlight(inst))
      .on("click", (event, d) => {
        if (event.defaultPrevented) return;
        opts.onConceptClick && opts.onConceptClick(d.data.label, d.data);
      });

    chip.each(function (d) {
      const isRoot = d.depth === 0;
      const w = chipWidth(d.data.label, isRoot);
      const h = isRoot ? ROOT_CHIP_H : CHIP_H;
      const g = d3.select(this);
      const fill = colorOf(d.data.id);
      g.select("rect.mm-chip-box")
        .attr("x", -w / 2).attr("y", -h / 2)
        .attr("width", w).attr("height", h)
        .attr("rx", isRoot ? 10 : 8)
        .attr("fill", fill)
        .attr("fill-opacity", isRoot ? 0.3 : 0.22)
        .attr("stroke", fill)
        .attr("stroke-width", isRoot ? 2 : 1.4);
      g.select("text.mm-chip-label")
        .attr("font-weight", isRoot ? 700 : 500)
        .text(truncate(d.data.label));
      g.select("title").text(d.data.label);

      const hasKids = !!(d.children || d._children);
      g.select(".mm-nub")
        .attr("transform", `translate(${w / 2},0)`)
        .style("display", hasKids ? null : "none");
      g.select(".mm-nub circle").attr("fill", fill);
      g.select(".mm-nub-sign").text(d._children ? "+" : "−");
      g.select(".mm-nub").on("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        toggle(d);
        draw(inst);
        applyFit(inst);
      });
    });

    if (opts.onRendered) {
      const branches = (inst.hierarchy.data.children || []).map((b) => ({
        label: b.label,
        color: inst.colors.get(b.id),
      }));
      opts.onRendered({
        svgId: inst.svgId,
        root: inst.graph.root,
        nodeCount: nodes.length,
        hasCrossLinks: inst.crossLinks.length > 0,
        legend: branches,
      });
    }
  }

  /* ── hover highlight (path to root) ───────────────────────────────────── */

  function highlightPath(inst, d) {
    const chain = new Set();
    let cur = d;
    while (cur) { chain.add(cur.data.id); cur = cur.parent; }
    inst.gEl.selectAll("g.mm-chip").classed("mm-dim", (n) => !chain.has(n.data.id));
    inst.gEl.selectAll("path.mm-link").classed("mm-dim", (l) => !chain.has(l.target.data.id));
  }
  function clearHighlight(inst) {
    inst.gEl.selectAll(".mm-dim").classed("mm-dim", false);
  }

  /* ── zoom / fit ──────────────────────────────────────────────────────── */

  function currentViewport(inst) {
    const m = model();
    return m
      ? m.resolveViewport(inst.container, { width: 900, height: 560 })
      : { width: inst.container.clientWidth || 900, height: inst.container.clientHeight || 560 };
  }

  function applyFit(inst) {
    let bbox;
    try { bbox = inst.gEl.node().getBBox(); } catch (_) { return; }
    if (!bbox || !bbox.width || !bbox.height) return;
    const m = model();
    const vp = currentViewport(inst);
    inst.svg.attr("width", vp.width).attr("height", vp.height);
    const t = m
      ? m.computeFitTransform(bbox, vp, 30)
      : { x: vp.width / 2, y: vp.height / 2, k: 1 };
    // Applied directly (no transition) so a fit is always exact.
    inst.svg.call(inst.zoom.transform, d3.zoomIdentity.translate(t.x, t.y).scale(t.k));
  }

  /* ── public: render ─────────────────────────────────────────────────── */

  function render(data, opts) {
    opts = opts || {};
    if (!DOC) return null;
    const svgId = opts.svgId;
    const svgEl = DOC.getElementById(svgId);
    const container = containerOf(opts);
    if (!svgEl || !container) return null;
    if (!d3 || !model()) {
      setState(container, "error", "⚠", "Mind-map engine failed to load.");
      return null;
    }

    destroy(svgId);

    const graph = model().normalizeGraph(data);
    if (graph.warnings.length) console.warn("[mindmap]", ...graph.warnings);
    if (!graph.ok) {
      setState(
        container, "empty", "\u{1F578}",
        "Not enough distinct concepts to build a mind map. Try longer or more detailed text."
      );
      return null;
    }
    hideState(container);

    const hierarchy = d3.hierarchy(model().buildHierarchy(graph));
    const colors = model().assignBranchColors(hierarchy.data, model().BRANCH_COLORS);

    const svg = d3.select(svgEl);
    svg.selectAll("*").remove();
    svg.attr("role", "img").attr("aria-label", "Mind map: " + (graph.root || "concepts"));
    const gEl = svg.append("g").attr("class", "mm-canvas");
    gEl.append("g").attr("class", "mm-xlinks");
    gEl.append("g").attr("class", "mm-links");
    gEl.append("g").attr("class", "mm-xlabels");
    gEl.append("g").attr("class", "mm-nodes");

    const zoom = d3
      .zoom()
      .scaleExtent([ZOOM_MIN, ZOOM_MAX])
      .on("zoom", (event) => {
        gEl.attr("transform", event.transform);
        opts.onZoom && opts.onZoom(Math.round(event.transform.k * 100));
      });
    svg.call(zoom).on("dblclick.zoom", null);

    const inst = {
      svgId, svg, gEl, zoom, container,
      graph, hierarchy, colors,
      crossLinks: graph.edges,
      opts,
      viewport: currentViewport({ container }),
    };
    instances.set(svgId, inst);
    lastId = svgId;

    draw(inst);
    applyFit(inst);

    if (typeof ResizeObserver !== "undefined") {
      let last = inst.viewport;
      inst.ro = new ResizeObserver(() => {
        const vp = currentViewport(inst);
        if (Math.abs(vp.width - last.width) < 2 && Math.abs(vp.height - last.height) < 2) return;
        last = vp;
        // layout is viewport-independent (fixed ring spacing) — only re-frame
        applyFit(inst);
      });
      inst.ro.observe(container);
    }

    return publicHandle(svgId);
  }

  function publicHandle(id) {
    return {
      fit: () => fit(id),
      zoomBy: (f) => zoomBy(f, id),
      zoomReset: () => zoomReset(id),
      collapseAll: () => collapseAll(id),
      expandAll: () => expandAll(id),
      exportSVG: () => exportSVG(id),
      exportPNG: () => exportPNG(id),
      exportJSON: () => exportJSON(id),
      destroy: () => destroy(id),
    };
  }

  /* ── public: state helpers ──────────────────────────────────────────── */

  function showLoading(opts) {
    const c = containerOf(opts || {});
    if (c) setState(c, "loading", "", (opts && opts.message) || "Generating mind map…");
  }
  function showError(opts, message) {
    const c = containerOf(opts || {});
    if (c) setState(c, "error", "⚠", message || "Mind map failed.");
  }

  /* ── public: controls ───────────────────────────────────────────────── */

  function fit(id) {
    const inst = resolve(id);
    if (inst && d3) applyFit(inst);
  }
  function zoomBy(factor, id) {
    const inst = resolve(id);
    if (inst && d3) inst.svg.call(inst.zoom.scaleBy, factor);
  }
  function zoomReset(id) {
    fit(id);
  }
  function collapseAll(id) {
    const inst = resolve(id);
    if (!inst || !d3) return;
    (inst.hierarchy.children || []).forEach(collapse);
    draw(inst);
    applyFit(inst);
  }
  function expandAll(id) {
    const inst = resolve(id);
    if (!inst || !d3) return;
    expand(inst.hierarchy);
    draw(inst);
    applyFit(inst);
  }
  function destroy(id) {
    const inst = instances.get(id);
    if (!inst) return;
    if (inst.ro) inst.ro.disconnect();
    if (inst.svg) inst.svg.selectAll("*").remove();
    instances.delete(id);
    if (lastId === id) lastId = instances.size ? Array.from(instances.keys()).pop() : null;
  }

  /* ── public: export ────────────────────────────────────────────────── */

  function styledClone(inst) {
    const src = inst.svg.node();
    const clone = src.cloneNode(true);
    const ph = clone.querySelector(".mindmap-placeholder");
    if (ph) ph.remove();
    let bbox;
    try { bbox = inst.gEl.node().getBBox(); } catch (_) { bbox = { x: 0, y: 0, width: 900, height: 560 }; }
    const pad = 24;
    clone.setAttribute("xmlns", SVG_NS);
    clone.setAttribute(
      "viewBox",
      `${bbox.x - pad} ${bbox.y - pad} ${bbox.width + pad * 2} ${bbox.height + pad * 2}`
    );
    clone.setAttribute("width", Math.round(bbox.width + pad * 2));
    clone.setAttribute("height", Math.round(bbox.height + pad * 2));
    // reset any pan/zoom transform so the viewBox does the framing
    const g = clone.querySelector(".mm-canvas");
    if (g) g.removeAttribute("transform");

    const style = document.createElementNS(SVG_NS, "style");
    style.textContent = collectCss(src);
    clone.insertBefore(style, clone.firstChild);
    return clone;
  }

  // Copy the computed values of the .mm-* rules off live elements so the export
  // is styled even though the stylesheet is external.
  function collectCss(svgNode) {
    const pick = (sel, props) => {
      const el = svgNode.querySelector(sel);
      if (!el) return "";
      const cs = getComputedStyle(el);
      const body = props.map((p) => `${p}:${cs.getPropertyValue(p)}`).join(";");
      return `${sel}{${body}}`;
    };
    return [
      "svg{background:" + (getComputedStyle(svgNode.parentElement).backgroundColor || "#0f1419") + "}",
      pick(".mm-link", ["fill", "stroke", "stroke-width", "stroke-opacity"]),
      pick(".mm-xlink", ["fill", "stroke", "stroke-width", "stroke-dasharray", "stroke-opacity"]),
      pick(".mm-xlink-label", ["fill", "font", "font-size", "font-family", "opacity"]),
      pick(".mm-chip-box", ["stroke-width"]),
      pick(".mm-chip-label", ["fill", "font", "font-size", "font-family"]),
      pick(".mm-nub circle", ["stroke", "stroke-width"]),
      pick(".mm-nub-sign", ["fill", "font-size", "font-family"]),
    ].filter(Boolean).join("\n");
  }

  function exportSVG(id) {
    const inst = resolve(id);
    if (!inst || !d3) return;
    const str = new XMLSerializer().serializeToString(styledClone(inst));
    saveBlob(new Blob([str], { type: "image/svg+xml;charset=utf-8" }), "mindmap.svg");
  }

  function exportPNG(id) {
    const inst = resolve(id);
    if (!inst || !d3) return;
    const clone = styledClone(inst);
    const w = Number(clone.getAttribute("width")) || 900;
    const h = Number(clone.getAttribute("height")) || 560;
    const scale = Math.min(3, Math.max(2, (window.devicePixelRatio || 1)));
    const str = new XMLSerializer().serializeToString(clone);
    const svgUrl = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(str);
    const img = new Image();
    img.onload = () => {
      const canvas = document.createElement("canvas");
      canvas.width = Math.round(w * scale);
      canvas.height = Math.round(h * scale);
      const ctx = canvas.getContext("2d");
      ctx.fillStyle = getComputedStyle(inst.container).backgroundColor || "#0f1419";
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      canvas.toBlob((blob) => blob && saveBlob(blob, "mindmap.png"), "image/png");
    };
    img.onerror = () => exportSVG(id); // fall back to SVG if the raster step is blocked
    img.src = svgUrl;
  }

  function exportJSON(id) {
    const inst = resolve(id);
    if (!inst) return;
    const payload = { root: inst.graph.root, nodes: inst.graph.nodes, edges: inst.graph.edges };
    saveBlob(
      new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" }),
      "mindmap.json"
    );
  }

  return {
    render,
    showLoading,
    showError,
    fit,
    zoomBy,
    zoomReset,
    collapseAll,
    expandAll,
    exportSVG,
    exportPNG,
    exportJSON,
    destroy,
    _instances: instances,
  };
});
