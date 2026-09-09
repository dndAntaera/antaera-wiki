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
 * 2. Three star layers are drawn, far to near, each on its own canvas so it
 *    can be moved independently. Star count scales with the area of the
 *    viewport, so a wide monitor is not sparser than a laptop.
 *
 * 3. Nebulae are radial gradients, a handful per sky, positioned and coloured
 *    from the same seed, drawn under the stars at low alpha.
 *
 * 4. Every layer is painted at twice the viewport width, with each element
 *    drawn twice - once at x and once at x + width. That makes the layer
 *    seamless when it slides: panning it from 0 to -width and resetting is
 *    invisible, because the second copy is already in position. The sky drifts
 *    continuously, each layer at its own speed, which is what gives it depth.
 *
 * 5. Scrolling adds a vertical offset to the same transform, at a different
 *    rate per layer. Nothing is ever repainted - only a CSS transform changes -
 *    so a ten-thousand-word page stays cheap to scroll.
 *
 * The sky does not change between light and dark mode. It is the same space in
 * both; only the cards on top of it change.
 */
(function () {
  "use strict";

  /* density is stars per 10,000 px², so the sky has the same thickness on a
     laptop as on a wide monitor. Roughly one star per 2,200 px² in the far
     layer, thinning by about a third at each step nearer; the three together
     come to some 650 stars on a 1280x800 window. Radius and alpha are ranges,
     drawn per star, which is what stops a layer reading as a regular grid of
     identical dots.

     pan is px per second sideways and parallax is the fraction of the scroll
     distance the layer moves vertically. Near layers do both faster: that
     difference is the whole illusion of depth. */
  var LAYERS = [
    { density: 4.5, r: [0.3, 0.7], alpha: [0.20, 0.50], parallax: 0.03, pan: 1.4 },
    { density: 1.6, r: [0.45, 1.0], alpha: [0.35, 0.75], parallax: 0.07, pan: 2.9 },
    { density: 0.45, r: [0.8, 1.8], alpha: [0.55, 1.0], parallax: 0.14, pan: 5.2 }
  ];

  /* The nebulae are further away than any of the stars, so they drift slowest
     of all - about a screen width every twenty minutes. */
  var NEBULA_PAN = 0.5;

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

  var root = document.createElement("div");
  root.className = "wd-sky";
  root.setAttribute("aria-hidden", "true");

  var nebula = document.createElement("canvas");
  nebula.className = "wd-sky__nebula";
  root.appendChild(nebula);

  var canvases = LAYERS.map(function () {
    var c = document.createElement("canvas");
    root.appendChild(c);
    return c;
  });

  var dpr = 1, W = 0, H = 0;

  /* Every layer is 2W wide. Panning never has to jump: by the time the first
     copy has slid a full W to the left, the second copy occupies exactly the
     space it left. */
  function sizeCanvas(c, h) {
    c.width = Math.round(W * 2 * dpr);
    c.height = Math.round(h * dpr);
    c.style.width = (W * 2) + "px";
    c.style.height = h + "px";
    var ctx = c.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, W * 2, h);
    return ctx;
  }

  function drawNebula(rand) {
    var ctx = sizeCanvas(nebula, H);
    /* Fewer, larger clouds on a big screen; the count is tied to area so the
       sky does not thin out when the window grows. */
    var n = Math.round(3 + Math.min(4, (W * H) / 900000));
    for (var i = 0; i < n; i++) {
      var cx = between(rand, -0.1, 1.1) * W;
      var cy = between(rand, -0.1, 1.1) * H;
      var rad = between(rand, 0.25, 0.6) * Math.max(W, H);
      var hue = NEBULA_HUES[Math.floor(rand() * NEBULA_HUES.length)];
      var peak = between(rand, 0.06, 0.13);
      /* Twice, a screen apart, and clipped to each cloud's own box rather than
         filling the whole canvas - a radial gradient is transparent outside
         its radius anyway, and the smaller fill is far cheaper. */
      for (var copy = 0; copy < 2; copy++) {
        var x = cx + copy * W;
        var g = ctx.createRadialGradient(x, cy, 0, x, cy, rad);
        g.addColorStop(0, "rgba(" + hue + "," + peak + ")");
        g.addColorStop(0.55, "rgba(" + hue + "," + peak * 0.35 + ")");
        g.addColorStop(1, "rgba(" + hue + ",0)");
        ctx.fillStyle = g;
        ctx.fillRect(x - rad, cy - rad, rad * 2, rad * 2);
      }
    }
  }

  function drawStars(rand) {
    LAYERS.forEach(function (layer, i) {
      /* Taller than the viewport by the distance the layer will travel under
         parallax, so nothing runs out of sky at the foot of a long page. */
      var h = H * (1 + layer.parallax * 3);
      var ctx = sizeCanvas(canvases[i], h);
      var count = Math.round((W * h) / 10000 * layer.density);
      for (var s = 0; s < count; s++) {
        var x = rand() * W;
        var y = rand() * h;
        var r = between(rand, layer.r[0], layer.r[1]);
        var a = between(rand, layer.alpha[0], layer.alpha[1]);
        var hue = STAR_HUES[Math.floor(rand() * STAR_HUES.length)];
        for (var copy = 0; copy < 2; copy++) {
          var px = x + copy * W;
          ctx.beginPath();
          ctx.arc(px, y, r, 0, Math.PI * 2);
          ctx.fillStyle = "rgba(" + hue + "," + a + ")";
          ctx.fill();
          /* The brightest few get a halo. Drawn as a second, wider gradient
             rather than a shadowBlur, which is far cheaper per star. */
          if (i === 2 && r > 1.5) {
            var g = ctx.createRadialGradient(px, y, 0, px, y, r * 6);
            g.addColorStop(0, "rgba(" + hue + ",0.30)");
            g.addColorStop(1, "rgba(" + hue + ",0)");
            ctx.fillStyle = g;
            ctx.fillRect(px - r * 6, y - r * 6, r * 12, r * 12);
          }
        }
      }
    });
  }

  function render() {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    W = document.documentElement.clientWidth;
    H = window.innerHeight;
    /* One generator, drawn from the page's seed, used for the whole sky. The
       nebulae and every layer of stars come out of the same stream, so the sky
       is reproducible as a whole rather than per-piece. */
    var rand = rng(seedFromPath(location.pathname));
    drawNebula(rand);
    drawStars(rand);
    place();
  }

  /* Seconds of drift accumulated so far, and the timestamp of the last frame.
     Time is added up frame by frame rather than measured from a start point,
     so a tab that was hidden for an hour resumes where it left off instead of
     jumping an hour's worth of sky sideways on its first frame back. */
  var elapsed = 0;
  var last = 0;
  var paused = false;
  var drifting = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function place() {
    var y = window.scrollY || window.pageYOffset || 0;
    /* The modulo is what makes the drift endless: at W the layer is exactly
       one screen along and the second copy has taken its place, so resetting
       to 0 changes nothing on screen. */
    nebula.style.transform =
      "translate3d(" + (-(elapsed * NEBULA_PAN) % W).toFixed(2) + "px,0,0)";
    for (var i = 0; i < canvases.length; i++) {
      canvases[i].style.transform = "translate3d("
        + (-(elapsed * LAYERS[i].pan) % W).toFixed(2) + "px,"
        + (-y * LAYERS[i].parallax).toFixed(2) + "px,0)";
    }
  }

  function frame(now) {
    if (paused) return;
    if (last) elapsed += (now - last) / 1000;
    last = now;
    place();
    window.requestAnimationFrame(frame);
  }

  var resizeTimer;
  function onResize() {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(render, 150);
  }

  function start() {
    document.body.insertBefore(root, document.body.firstChild);
    render();
    if (drifting) {
      window.requestAnimationFrame(frame);
      /* A background tab should not be animating. rAF already throttles when
         hidden, but stopping outright means no work at all, and the drift
         picks up from where the clock says it should be rather than jumping. */
      document.addEventListener("visibilitychange", function () {
        paused = document.hidden;
        if (!paused) {
          last = 0;                 /* the gap while hidden is not drift time */
          window.requestAnimationFrame(frame);
        }
      });
    } else {
      /* No drift, but the parallax still needs the scroll position. */
      window.addEventListener("scroll", function () {
        window.requestAnimationFrame(function () { place(); });
      }, { passive: true });
    }
    window.addEventListener("resize", onResize);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
