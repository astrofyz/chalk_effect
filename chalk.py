"""Chalk-on-a-blackboard styling for matplotlib, applied globally like ``plt.xkcd()``.

Two layers, use either or both:

* ``chalk.mplstyle`` -- a plain style file (``plt.style.use("chalk.mplstyle")``).
  It only sets colours + matplotlib's built-in ``path.sketch`` wobble, so it is
  essentially free and already touches *every* path in the figure (data lines,
  spines, ticks, grid, legend frame, patch edges).

* :class:`ChalkEffect` -- a path effect that redraws every stroke as a cloud of
  jittered chalk grains, giving the dusty texture.  It is installed globally
  through ``rcParams["path.effects"]`` by :func:`chalk`, so it also applies to
  everything.  Cost scales with the *number of artists*, not with a point count
  you pick by hand -- a whole figure is a few milliseconds, versus a giant
  ``scatter`` per line.

Example
-------
>>> from chalk import chalk
>>> with chalk():
...     fig, ax = plt.subplots()
...     ax.plot(x, y)

``chalk()`` works as a context manager or as a bare call (like ``plt.xkcd()``).

Requires an Agg-based backend (the default): ``path.sketch`` and
``draw_markers`` are Agg features.
"""

from __future__ import annotations

import contextlib
from pathlib import Path as _FSPath

import numpy as np
import matplotlib as mpl
import matplotlib.colors as mcolors
from cycler import cycler
from matplotlib import font_manager
from matplotlib.path import Path
from matplotlib.patheffects import AbstractPathEffect
from matplotlib.transforms import Affine2D, IdentityTransform

__all__ = ["ChalkEffect", "chalk", "use_font"]


# --------------------------------------------------------------------------- #
# fonts
# --------------------------------------------------------------------------- #
def use_font(*paths, set_family=True):
    """Register .ttf/.otf files with matplotlib and (optionally) make them the
    default.

    ``paths`` may be individual font files or directories (scanned for
    ``*.ttf``/``*.otf``).  Pass every face you have -- Regular, Bold, Italic,
    ... -- and matplotlib matches the right one by weight/style automatically
    since they share a family name.

    Returns the family name of the last registered face, which is what gets
    put in ``rcParams["font.family"]`` when ``set_family`` is True.
    """
    files = []
    for p in paths:
        p = _FSPath(p).expanduser()
        if p.is_dir():
            files += sorted(p.glob("*.ttf")) + sorted(p.glob("*.otf"))
        else:
            files.append(p)

    name = None
    for f in files:
        font_manager.fontManager.addfont(str(f))
        name = font_manager.FontProperties(fname=str(f)).get_name()

    if set_family and name is not None:
        mpl.rcParams["font.family"] = name
    return name


# --------------------------------------------------------------------------- #
# geometry helpers (all in display / pixel space)
# --------------------------------------------------------------------------- #
def _polylines(path):
    """Yield each connected run of vertices of *path* as an (N, 2) array."""
    run = []
    for verts, code in path.iter_segments(curves=False):
        if code == Path.MOVETO:
            if len(run) >= 2:
                yield np.asarray(run)
            run = [verts]
        elif code == Path.CLOSEPOLY:
            if run:
                run.append(run[0])
                if len(run) >= 2:
                    yield np.asarray(run)
            run = []
        else:  # LINETO
            run.append(verts)
    if len(run) >= 2:
        yield np.asarray(run)


def _resample(verts, spacing):
    """Resample a polyline at roughly even arc-length *spacing* (pixels)."""
    seg = np.diff(verts, axis=0)
    dist = np.hypot(seg[:, 0], seg[:, 1])
    s = np.concatenate([[0.0], np.cumsum(dist)])
    total = s[-1]
    if total < spacing:
        return verts
    n = int(total / spacing) + 1
    si = np.linspace(0.0, total, n)
    return np.column_stack([np.interp(si, s, verts[:, 0]),
                            np.interp(si, s, verts[:, 1])])


def _smooth_noise(rng, n, amp, window=31):
    """Low-frequency 1-D noise with std == *amp*."""
    if n < 4 or amp == 0:
        return np.zeros(n)
    window = int(max(3, min(window, n)))
    k = np.ones(window) / window
    w = rng.normal(0.0, 1.0, n + 2 * window)
    s = np.convolve(w, k, mode="same")
    s = np.convolve(s, k, mode="same")[window:window + n]
    return s / (s.std() + 1e-12) * amp


# --------------------------------------------------------------------------- #
# the path effect
# --------------------------------------------------------------------------- #
class ChalkEffect(AbstractPathEffect):
    """Redraw a stroke as a cloud of chalk grains.

    Parameters
    ----------
    spacing : float
        Pixels between grain "stations" along the stroke.  Smaller -> denser,
        slower.
    spread : float
        Std dev (px) of grain scatter *across* the stroke -- the line's width.
    jitter : float
        Std dev (px) of extra isotropic per-grain jitter (the fuzz).
    wander : float
        Std dev (px) of a slow wobble of the stroke's centre line, on top of
        ``path.sketch``.  ``wander=0`` gives a dead-straight centre line that
        is still chalk-textured (only ``spread``/``jitter`` fuzz remain) --
        use it with ``chalk(sketch=None)`` for straight but chalky axes.
    wander_length : float
        Approximate wavelength (px) of that wobble.  Larger -> longer, lazier
        waves; smaller -> tighter squiggles.
    grain : float
        Base grain diameter in pixels.
    ref_linewidth : float or None
        Reference stroke width (points) that ``spread``/``grain`` are tuned
        for.  Each stroke's own ``linewidth`` (from ``lw=`` /
        ``rcParams["lines.linewidth"]``) is divided by this to scale its
        chalk width -- so thin lines draw thin, thick lines draw fat, as
        usual.  The ratio is clamped to ``[0.35, 3.0]``.  ``None`` ignores
        ``linewidth`` entirely and every stroke uses ``spread`` as-is.
        Default ``2.0`` matches ``chalk()``'s ``lines.linewidth``.
    alpha : float
        Overall opacity multiplier for the grains.
    passes : int
        Number of grain copies laid down per stroke (more -> denser).
    seed : int or None
        Seed for reproducible dust.
    keep_fill : bool
        If True, still paint the original face colour for filled patches
        (bars, wedges, fill_between) before laying chalk on the outline.
    fill_density : float
        Grains per 100x100 px scattered across a filled patch's *interior*
        to make the fill itself chalky (not just a flat colour).  ``0``
        (default) leaves the fill flat -- see ``keep_fill``.  Roughly
        ``300`` for a light shading, ``2000``+ for near-solid dusty fill.
        Combine with ``keep_fill=False`` for a translucent shaded look, or
        ``keep_fill=True`` for flat base + dusty overlay.
    fill_max : int
        Hard cap on interior grains per patch, so a huge polygon can't blow
        up the draw.  Default ``20000``.
    skip_text : bool
        If True (default) text is always drawn crisply, never grained.
        Detected structurally: a filled Bezier path drawn with linewidth 0
        (matplotlib's ``_draw_text_as_path`` forces that) or with several
        sub-paths (a multi-glyph string).  ``path.sketch`` still applies to
        it.  Set False to let text be grained too.
    min_extent : float
        Artists whose pixel bounding box is smaller than this in both
        dimensions skip the grainy *outline* (which would just swamp them)
        and are drawn with a crisp edge instead -- keeps tick marks and
        small markers sharp.  A small *filled* patch (a short histogram bar)
        still gets the ``keep_fill`` / ``fill_density`` treatment so it
        matches its taller neighbours.  Set to 0 to texturize everything.
    flat_bg : float
        A filled rectangle (<= 5 vertices) whose bounding box covers at least
        this fraction of the canvas is painted flat, with no grain -- this
        removes the grainy frame around the whole figure and the redundant
        border on the axes background (the spines still get chalked).  Set to
        ``1.0`` to only spare a full-canvas figure patch, or ``0`` to grain
        every rectangle (bars included -- those are always grained anyway,
        being well under any sane fraction).
    """

    # (fraction of stations kept, size multiple, alpha multiple)
    _LAYERS = ((0.90, 1.0, 0.55), (0.50, 0.6, 0.95), (0.16, 1.9, 0.14))

    def __init__(self, spacing=2.0, spread=1.5, jitter=0.5, wander=0.2,
                 wander_length=50.0, grain=2.2, alpha=0.9, passes=3, seed=None,
                 keep_fill=True, fill_density=0.0, fill_max=20000,
                 skip_text=True, min_extent=26.0, flat_bg=0.5,
                 ref_linewidth=2.0):
        super().__init__()
        self.spacing = spacing
        self.spread = spread
        self.jitter = jitter
        self.wander = wander
        self.wander_length = wander_length
        self.grain = grain
        self.alpha = alpha
        self.passes = passes
        self.seed = seed
        self.keep_fill = keep_fill
        self.fill_density = fill_density
        self.fill_max = fill_max
        self.skip_text = skip_text
        self.min_extent = min_extent
        self.flat_bg = flat_bg
        self.ref_linewidth = ref_linewidth

    def draw_path(self, renderer, gc, tpath, affine, rgbFace=None):
        rng = np.random.default_rng(self.seed)
        path = affine.transform_path(tpath)  # -> pixel space

        # scale chalk width by this stroke's own linewidth relative to the
        # reference, so thin lines stay thin and fat lines stay fat
        if self.ref_linewidth:
            lw_scale = float(np.clip(gc.get_linewidth() / self.ref_linewidth,
                                     0.35, 3.0))
        else:
            lw_scale = 1.0
        spread = self.spread * lw_scale
        grain = self.grain * lw_scale

        # Draw some things crisply (still wobbled by path.sketch) instead of
        # graining them.
        bb = path.get_extents()
        codes = tpath.codes

        # text -> once path.effects is set matplotlib routes glyphs through here
        # via _draw_text_as_path, which forces the linewidth to 0 before
        # calling draw_path (see matplotlib.backend_bases.RendererBase).  A real
        # filled patch keeps its edge width (chalk() sets patch.force_edgecolor).
        # Some glyphs -- straight-edged digits, the minus sign -- have no Bezier
        # codes, so key off lw == 0, not the curves.  Never grain text; its look
        # comes from the font.  This has to run before the small-artist branch
        # below, or short tick labels get caught there and dusted.
        if (self.skip_text and rgbFace is not None and codes is not None
                and gc.get_linewidth() == 0):
            n_sub = int(np.count_nonzero(codes == Path.MOVETO))
            has_curve = bool(np.any((codes == Path.CURVE3)
                                    | (codes == Path.CURVE4)))
            # spare glyphs, but not a large zero-width filled polygon
            if has_curve or n_sub >= 2 or bb.height < 4 * self.min_extent:
                renderer.draw_path(gc, tpath, affine, rgbFace)
                return

        # small artists -> don't grain the outline into fuzz
        if bb.width < self.min_extent and bb.height < self.min_extent:
            if rgbFace is None:
                # tick mark / tiny line marker -> draw crisp, done
                renderer.draw_path(gc, tpath, affine, rgbFace)
                return
            # small filled patch (a short histogram bar) -> keep it consistent
            # with tall bars: crisp thin edge, optional flat base, chalky fill;
            # just skip the grainy outline that would swamp it
            face = rgbFace if self.keep_fill else None
            renderer.draw_path(gc, tpath, affine, face)
            self._chalk_fill(renderer, gc, path, bb, rgbFace, rng, grain)
            return
        # big filled rectangle (figure patch, axes background) -> paint flat,
        # no grainy frame around the figure
        if rgbFace is not None and len(tpath.vertices) <= 5 and self.flat_bg > 0:
            cw, ch = renderer.get_canvas_width_height()
            if bb.width * bb.height >= self.flat_bg * cw * ch:
                renderer.draw_path(gc, tpath, affine, rgbFace)
                return

        if self.keep_fill and rgbFace is not None:
            gcf = renderer.new_gc()
            gcf.copy_properties(gc)
            gcf.set_linewidth(0)
            renderer.draw_path(gcf, path, IdentityTransform(), rgbFace)
            gcf.restore()

        self._chalk_fill(renderer, gc, path, bb, rgbFace, rng, grain)

        stations = []
        for verts in _polylines(path):
            xy = _resample(verts, self.spacing)
            if len(xy) < 2:
                continue
            tangent = np.gradient(xy, axis=0)
            normal = np.column_stack([-tangent[:, 1], tangent[:, 0]])
            normal /= np.linalg.norm(normal, axis=1, keepdims=True) + 1e-12
            win = max(3, int(round(self.wander_length / self.spacing)))
            spine = xy + normal * _smooth_noise(
                rng, len(xy), self.wander, window=win)[:, None]
            for _ in range(self.passes):
                perp = rng.normal(0.0, spread, len(xy))[:, None]
                fuzz = rng.normal(0.0, self.jitter, (len(xy), 2))
                stations.append(spine + normal * perp + fuzz)

        if not stations:
            return
        pts = np.concatenate(stations)

        gc0 = renderer.new_gc()
        gc0.copy_properties(gc)
        gc0.set_linewidth(0)
        gc0.set_sketch_params(None)          # our grains shouldn't be re-wiggled
        r, g, b, _ = mcolors.to_rgba(gc.get_rgb())
        marker = Path.unit_circle()

        for frac, size, a in self._LAYERS:
            mask = rng.random(len(pts)) < frac
            if not mask.any():
                continue
            layer = pts[mask] + rng.normal(0.0, self.jitter, (int(mask.sum()), 2))
            # positional args only: the Agg renderer's draw_markers is a C method
            renderer.draw_markers(
                gc0,
                marker, Affine2D().scale(size * grain / 2.0),
                Path(layer), IdentityTransform(),
                (r, g, b, min(1.0, a * self.alpha)),
            )
        gc0.restore()

    def _chalk_fill(self, renderer, gc, path, bb, rgbFace, rng, grain):
        """Scatter grains across a filled patch's interior (``fill_density``)."""
        if (not self.fill_density or rgbFace is None
                or bb.width <= 0 or bb.height <= 0):
            return
        # constant areal density -> same look on a tall bar and a short one
        n = int(min(self.fill_density * bb.width * bb.height / 1e4,
                    self.fill_max))
        if n <= 0:
            return
        pts = np.column_stack([rng.uniform(bb.x0, bb.x1, n),
                               rng.uniform(bb.y0, bb.y1, n)])
        pts = pts[path.contains_points(pts)]
        if not len(pts):
            return
        fr, fg, fb, fa = mcolors.to_rgba(rgbFace)
        gcf = renderer.new_gc()
        gcf.copy_properties(gc)
        gcf.set_linewidth(0)
        gcf.set_sketch_params(None)
        for size, a in ((1.0, 0.85), (0.55, 1.0)):
            jit = pts + rng.normal(0.0, 0.5 * self.jitter, pts.shape)
            renderer.draw_markers(
                gcf, Path.unit_circle(),
                Affine2D().scale(size * grain / 2.0),
                Path(jit), IdentityTransform(),
                (fr, fg, fb, min(1.0, a * fa * self.alpha)),
            )
        gcf.restore()


# --------------------------------------------------------------------------- #
# global activator, mirrors plt.xkcd()
# --------------------------------------------------------------------------- #
_CHALK_CYCLE = ["#f5f5f5", "#ffe9a8", "#a8d8ff", "#ffb3c6", "#b5f2c9", "#d9c2ff"]


def chalk(sketch=(1.5, 120, 2), grain=None,
          board="#0d0d0d", panel="#161616", ink="#ededed", grid="#4a4a4a",
          font=None, **grain_kw):
    """Turn the whole figure into chalk-on-a-blackboard.

    Returns a context manager so it works with ``with`` *and* is applied
    immediately when called bare, just like :func:`matplotlib.pyplot.xkcd`.
    The original ``rcParams`` are captured before the update and restored on
    ``with`` exit (bare calls leave the chalk style in place).

    Parameters
    ----------
    sketch : tuple or None
        The ``path.sketch`` triple ``(scale, length, randomness)``; matplotlib's
        built-in wobble, applied by Agg to every path.  Pass ``None`` (or a
        ``scale`` of 0) to switch it off entirely -- combine with
        ``wander=0`` for perfectly straight but still chalk-textured lines
        and axes.
    grain : ChalkEffect or None
        The grain texture.  ``None`` builds ``ChalkEffect(**grain_kw)``.  Pass
        a ready-made instance to bypass ``grain_kw``.  For the fast
        sketch-only look, use ``chalk.mplstyle`` directly, or afterwards do
        ``matplotlib.rcParams["path.effects"] = []``.
    board, panel, ink, grid : color
        Figure background, axes background, foreground, and grid colour.
    font : path, list of paths, or None
        One or more ``.ttf``/``.otf`` files (or a directory of them) to
        register and use for all text.  See :func:`use_font`.  ``None`` keeps
        the sans-serif default.
    **grain_kw
        Forwarded to :class:`ChalkEffect` when ``grain is None`` -- e.g.
        ``chalk(sketch=None, wander=0)`` or ``chalk(spread=2, grain=3)``.
    """
    family = "sans-serif"
    if font is not None:
        paths = [font] if isinstance(font, (str, _FSPath)) else list(font)
        family = use_font(*paths, set_family=False) or family

    rc = {
        "path.sketch": sketch,
        "path.effects": [grain if grain is not None
                         else ChalkEffect(**grain_kw)],
        "figure.facecolor": board,
        "axes.facecolor": panel,
        "savefig.facecolor": board,
        "text.color": ink,
        "axes.edgecolor": ink,
        "axes.labelcolor": ink,
        "axes.titlecolor": ink,
        "xtick.color": ink,
        "ytick.color": ink,
        "legend.facecolor": panel,
        "legend.edgecolor": ink,
        "legend.framealpha": 1.0,
        "grid.color": grid,
        "axes.grid": True,
        "grid.linewidth": 0.8,
        "lines.linewidth": 2.0,
        "lines.solid_capstyle": "round",
        "lines.dash_capstyle": "round",
        "patch.edgecolor": ink,
        "patch.force_edgecolor": True,
        "axes.prop_cycle": cycler(color=_CHALK_CYCLE),
        "font.family": family,
    }
    orig = mpl.rcParams.copy()
    mpl.rcParams.update(rc)

    @contextlib.contextmanager
    def _restore():
        try:
            yield
        finally:
            mpl.rcParams.update(orig)
    return _restore()


# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    import matplotlib.pyplot as plt

    with chalk():
        fig, ax = plt.subplots(figsize=(7.5, 4.5))
        x = np.linspace(0, 4 * np.pi, 240)
        ax.plot(x, np.sin(x), label="sin x")
        ax.plot(x, 0.6 * np.cos(1.3 * x), label="cos 1.3x")
        ax.fill_between(x, np.sin(x), 0, alpha=0.15)
        ax.bar([2, 5, 8], [0.4, -0.6, 0.8], width=0.5, alpha=0.5)
        ax.set_title("chalk effect as a global style")
        ax.set_xlabel("x")
        ax.set_ylabel("y")
        ax.legend()
        fig.tight_layout()
        fig.savefig("chalk_demo.png", dpi=130)
        plt.show()
