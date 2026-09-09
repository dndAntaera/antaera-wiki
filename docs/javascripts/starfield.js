/* Procedural starfield background.
 *
 * The setting is a spelljamming campaign, so the page sits in space rather
 * than on a flat colour. Nothing here is an image file: every star and every
 * nebula is computed in the browser at load, which keeps the page weight at a
 * few kilobytes of script instead of a wallpaper, and lets the sky redraw at
 * whatever size and pixel density the reader's screen actually is.
 *
 * How it works, in the order it happens:
 *
 * 1. A seed is derived from the page's own URL path. The same page therefore
 *    gets the same sky every visit, on every machine, while two pages get
 *    different skies - each article is its own region of space. The seed
 *    drives a small deterministic generator (mulberry32), so "random" here is
 *    reproducible rather than different on every reload.
 *
 * 2. Three star layers are drawn, far to near. Each layer gets its own
 *    offscreen canvas so it can be moved independently. Star count scales with
 *    the area of the viewport, so a wide monitor is not sparser than a laptop.
 *
 * 3. Nebulae are radial gradients, a handful per sky, positioned and coloured
 *    from the same seed. They are drawn under the stars at low alpha.
 *
 * 4. On scroll the three layers translate at different rates. Nothing is
 *    redrawn - the layers are already painted, and only a CSS transform
 *    changes - so scrolling a ten-thousand-word page stays cheap.
 *
 * The light theme does not get stars: the cards are parchment and a starfield
 * behind them reads as a hole in the page. It gets the nebula wash only, very
 * faint, which gives the paper some depth without pretending to be space.
 */
(function () {
  "use strict";

  /* density is stars per 10,000 px², so the sky has the same thickness on a
     laptop as on a wide monitor. Roughly one star per 2,200 px² in the far
     layer, thinning by about a third at each step nearer; the three together
     come to some 650 stars on a 1280x800 window. Radius and alpha are ranges,
     drawn per star, which is what stops a layer reading as a regular grid of
     identical dots. */
  var LAYERS = [
    { density: 4.5, r: [0.3, 0.7], alpha: [0.20, 0.50], parallax: 0.03 },
    { density: 1.6, r: [0.45, 1.0], alpha: [0.35, 0.75], parallax: 0.07 },
    { density: 0.45, r: [0.8, 1.8], alpha: [0.55, 1.0], parallax: 0.14 }
  ];

  /* Star colours: mostly white, with the occasional blue or amber giant, which
     is what stops a starfield reading as grey noise. */
  var STAR_HUES = [
    [255, 255, 255], [255, 255, 255], [255, 255, 255],
    [202, 222, 255], [255, 232, 196], [226, 205, 255]
  ];

  /* Nebula hues. The purple is the site's own accent, so the background and
     the chrome belong to the same palette. */
  var NEBULA_HUES = [
    [191, 0, 255], [86, 60, 220], [40, 130, 200], [190, 70, 160], [60, 160, 190]
  ];

  /* mulberry32: 32 bits of state, one multiply-xor-shift round per call. Small
     enough to read, good enough that the eye finds no pattern in it. */
  function rng(seed) {
    var a = seed >>> 0;
    return function () {
      a = (a + 0x6d2b79f5) >>> 0;
      var t = a;
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  /* FNV-1a over the path, so the seed is a property of the page, not of the
     visit. Reloading gives the same sky; a different article gives another. */
  function seedFromPath(path) {
    var h = 2166136261;
    for (var i = 0; i < path.length; i++) {
      h ^= path.charCodeAt(i);
      h = Math.imul(h, 16777619);
    }
    return h >>> 0;
  }

  function between(rand, lo, hi) { return lo + rand() * (hi - lo); }

  function isDark() {
    var s = document.body.getAttribute("data-md-color-scheme");
    if (s === "slate") return true;
    if (s === "default") return false;
    return window.matchMedia("(prefers-color-scheme: dark)").matches;
  }

  var root = document.createElement("div");
  root.className = "wd-sky";
  root.setAttribute("aria-hidden", "true");

  var canvases = LAYERS.map(function () {
    var c = document.createElement("canvas");
    root.appendChild(c);
    return c;
  });
  var nebula = document.createElement("canvas");
  nebula.className = "wd-sky__nebula";
  root.insertBefore(nebula, root.firstChild);

  var dpr = 1, W = 0, H = 0;

  function sizeCanvas(c, w, h) {
    c.width = Math.round(w * dpr);
    c.height = Math.round(h * dpr);
    c.style.width = w + "px";
    c.style.height = h + "px";
    var ctx = c.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    return ctx;
  }

  function drawNebula(rand, dark) {
    var ctx = sizeCanvas(nebula, W, H);
    /* Fewer, larger clouds on a big screen; the count is tied to area so the
       sky does not thin out when the window grows. */
    var n = Math.round(3 + Math.min(4, (W * H) / 900000));
    for (var i = 0; i < n; i++) {
      var cx = between(rand, -0.1, 1.1) * W;
      var cy = between(rand, -0.1, 1.1) * H;
      var rad = between(rand, 0.25, 0.6) * Math.max(W, H);
      var hue = NEBULA_HUES[Math.floor(rand() * NEBULA_HUES.length)];
      var peak = dark ? between(rand, 0.06, 0.13) : between(rand, 0.02, 0.045);
      var g = ctx.createRadialGradient(cx, cy, 0, cx, cy, rad);
      g.addColorStop(0, "rgba(" + hue[0] + "," + hue[1] + "," + hue[2] + "," + peak + ")");
      g.addColorStop(0.55, "rgba(" + hue[0] + "," + hue[1] + "," + hue[2] + "," + peak * 0.35 + ")");
      g.addColorStop(1, "rgba(" + hue[0] + "," + hue[1] + "," + hue[2] + ",0)");
      ctx.fillStyle = g;
      ctx.fillRect(0, 0, W, H);
    }
  }

  function drawStars(rand) {
    LAYERS.forEach(function (layer, i) {
      /* Each layer is drawn taller than the viewport by the distance it will
         travel under parallax, so nothing runs out of sky at the foot of a
         long page. */
      var h = H * (1 + layer.parallax * 3);
      var ctx = sizeCanvas(canvases[i], W, h);
      var count = Math.round((W * h) / 10000 * layer.density);
      for (var s = 0; s < count; s++) {
        var x = rand() * W;
        var y = rand() * h;
        var r = between(rand, layer.r[0], layer.r[1]);
        var a = between(rand, layer.alpha[0], layer.alpha[1]);
        var hue = STAR_HUES[Math.floor(rand() * STAR_HUES.length)];
        ctx.beginPath();
        ctx.arc(x, y, r, 0, Math.PI * 2);
        ctx.fillStyle = "rgba(" + hue[0] + "," + hue[1] + "," + hue[2] + "," + a + ")";
        ctx.fill();
        /* The brightest few get a halo. Drawn as a second, wider gradient
           rather than a shadowBlur, which is far cheaper per star. */
        if (i === 2 && r > 1.5) {
          var g = ctx.createRadialGradient(x, y, 0, x, y, r * 6);
          g.addColorStop(0, "rgba(" + hue[0] + "," + hue[1] + "," + hue[2] + ",0.30)");
          g.addColorStop(1, "rgba(" + hue[0] + "," + hue[1] + "," + hue[2] + ",0)");
          ctx.fillStyle = g;
          ctx.fillRect(x - r * 6, y - r * 6, r * 12, r * 12);
        }
      }
    });
  }

  function render() {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    W = document.documentElement.clientWidth;
    H = window.innerHeight;
    var dark = isDark();
    root.classList.toggle("wd-sky--dark", dark);

    /* One generator, drawn from the page's seed, used for the whole sky. The
       nebulae and every layer of stars come out of the same stream, so the
       sky is reproducible as a whole rather than per-piece. */
    var rand = rng(seedFromPath(location.pathname));
    drawNebula(rand, dark);
    canvases.forEach(function (c) { c.style.display = dark ? "" : "none"; });
    if (dark) drawStars(rand);
    parallax();
  }

  var ticking = false;
  function parallax() {
    var y = window.scrollY || window.pageYOffset || 0;
    for (var i = 0; i < canvases.length; i++) {
      canvases[i].style.transform =
        "translate3d(0," + (-y * LAYERS[i].parallax).toFixed(2) + "px,0)";
    }
    ticking = false;
  }

  function onScroll() {
    if (!ticking) {
      ticking = true;
      window.requestAnimationFrame(parallax);
    }
  }

  var resizeTimer;
  function onResize() {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(render, 150);
  }

  function start() {
    document.body.insertBefore(root, document.body.firstChild);
    render();
    /* Reduced motion keeps the sky and drops the parallax: the background is
       decoration, not something that should move under a reader who asked for
       stillness. */
    if (!window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      window.addEventListener("scroll", onScroll, { passive: true });
    }
    window.addEventListener("resize", onResize);
    /* Material's palette toggle rewrites this attribute in place, so the sky
       is redrawn rather than left in the wrong theme. */
    new MutationObserver(render).observe(document.body, {
      attributes: true, attributeFilter: ["data-md-color-scheme"]
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
