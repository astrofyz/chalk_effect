# chalk

Chalk-on-a-blackboard styling for matplotlib, applied globally.

The look is two independent effects:

1. **Wobble** — matplotlib's built-in `path.sketch` rcParam, applied by the Agg
   renderer to every path. This is the same mechanism `plt.xkcd()` uses.
2. **Grain** — `ChalkEffect`, a custom path effect installed into
   `rcParams["path.effects"]`. It redraws each stroke as a cloud of jittered
   chalk grains rendered with `renderer.draw_markers`.

Requires an Agg-based backend (the default). `path.sketch` and `draw_markers`
are Agg features.

```python
from chalk import chalk

with chalk():
    fig, ax = plt.subplots()
    ax.plot(x, y)
```

`chalk()` also works as a bare call (applies immediately and stays applied, like
`plt.xkcd()`):

```python
chalk()
# ... all following figures are chalky
```

---

## `chalk(...)`

The global activator. Sets the blackboard colours, the `path.sketch` wobble, and
installs a `ChalkEffect`. Returns a context manager that captures the current
`rcParams` before applying the style and restores them on `with` exit; call it
bare to apply for the rest of the session (no restore).

| Keyword | Default | Description |
|---|---|---|
| `sketch` | `(1.5, 120, 2)` | The `path.sketch` triple `(scale, length, randomness)` — matplotlib's built-in wobble applied to **every** path. `scale` = wobble amplitude, `length` = wavelength, `randomness` = how much the wavelength varies. **Pass `None`** (or a `scale` of `0`) to switch the wobble off entirely. |
| `grain` | `None` | The grain path effect. `None` builds `ChalkEffect(**grain_kw)` from whatever extra keywords you passed. Pass a ready-made `ChalkEffect(...)` instance here to bypass `grain_kw` completely. For a fast wobble-only look with no grain, set `rcParams["path.effects"] = []` afterwards. |
| `board` | `"#0d0d0d"` | Figure background colour (`figure.facecolor`, `savefig.facecolor`). |
| `panel` | `"#161616"` | Axes background colour (`axes.facecolor`, `legend.facecolor`). |
| `ink` | `"#ededed"` | Foreground colour — text, spines, tick labels, tick marks, legend edge. |
| `grid` | `"#4a4a4a"` | Grid line colour. The grid is turned **on** by `chalk()`. |
| `font` | `None` | One or more `.ttf`/`.otf` files, or a directory of them, to register and use for all text. `None` keeps the sans-serif default. See [Fonts](#fonts). |
| `**grain_kw` | — | Any remaining keywords are forwarded to `ChalkEffect` when `grain is None`. E.g. `chalk(sketch=None, wander=0)` or `chalk(spread=2, grain=3, seed=0)`. |

Besides the above, `chalk()` also sets: a pastel coloured-chalk `axes.prop_cycle`
(white, cream, blue, pink, green, violet), `lines.linewidth=2`, round line caps,
`patch.force_edgecolor=True` (so bar/patch faces get a chalk edge), and
`font.family="sans-serif"`.

---

## `ChalkEffect(...)`

The path effect that produces the grain. Instantiate it yourself only when you
want to reuse one or pass it explicitly; normally you tune it through
`chalk(**grain_kw)`. It is a `matplotlib.patheffects.AbstractPathEffect` and can
also be attached to a single artist with `artist.set_path_effects([ChalkEffect()])`.

### Texture — how the grain looks

| Keyword | Default | Description |
|---|---|---|
| `spacing` | `1.6` | Pixels between grain "stations" sampled along the stroke. Smaller → denser, slower. |
| `spread` | `1.1` | Std dev (px) of grain scatter **across** the stroke. This is effectively the drawn line's width / furriness. |
| `jitter` | `0.9` | Std dev (px) of extra isotropic per-grain jitter — the fine fuzz on top of `spread`. |
| `grain` | `2.2` | Base grain (chalk speck) diameter in pixels. The three internal layers scale this by ×1.0, ×0.6 and ×1.9. |
| `alpha` | `0.9` | Overall opacity multiplier for the grains. |
| `passes` | `3` | Number of grain copies laid down per stroke. More → denser, creamier, slower. |
| `ref_linewidth` | `2.0` | Reference stroke width (points) that `spread` and `grain` are tuned for. Each stroke's own `linewidth` (from `lw=` / `rcParams["lines.linewidth"]`) is divided by this and the ratio, clamped to `[0.35, 3.0]`, scales its chalk width — so thin lines draw thin, thick lines draw fat. The default `2.0` matches `chalk()`'s `lines.linewidth`. Set to `None` (or `0`) to ignore `linewidth` and draw every stroke at `spread`/`grain` as-is. |
| `seed` | `None` | Seed for the RNG. Set an int for reproducible dust across renders. |

### Centre-line wobble (independent of `path.sketch`)

| Keyword | Default | Description |
|---|---|---|
| `wander` | `2.0` | Std dev (px) of a slow, smooth sideways wobble of the stroke's **centre line**, on top of `path.sketch`. **`wander=0` gives a dead-straight centre line** that is still chalk-textured (only `spread`/`jitter` fuzz remain). |
| `wander_length` | `50.0` | Approximate wavelength (px) of that wobble. Larger → longer, lazier waves; smaller → tighter squiggles. Internally converted to a smoothing window of `wander_length / spacing` samples. |

### What to leave alone (readability guards)

| Keyword | Default | Description |
|---|---|---|
| `keep_fill` | `True` | For filled patches (bars, wedges, `fill_between`), paint the original face colour **flat** first, then lay chalk on the outline. `False` drops the fill and keeps only the grained edge. |
| `fill_density` | `0.0` | Grains per 100×100 px scattered across a filled patch's **interior**, so the fill itself is chalky rather than a flat block. `0` leaves it flat. Roughly `300` for light shading, `2000`+ for a near-solid dusty fill. Pair with `keep_fill=False` for a translucent shaded look, or `keep_fill=True` for a flat base plus dusty overlay. |
| `fill_max` | `20000` | Hard cap on interior grains per patch, so a huge polygon can't blow up the draw time. |
| `hatch` | `None` | Draw a patch's hatch as chalky grain lines. matplotlib paints hatches inside the renderer, not as an artist, so `ChalkEffect` otherwise **drops them entirely**. `None` honours each patch's own `hatch=` (`/ \ | - + x`, and repeats like `///` for denser lines — `o O . *` are unsupported and skipped). Pass a hatch string or an angle in degrees here to force one on every patch. Works with `fill=False` too. |
| `hatch_spacing` | `8.0` | Pixels between hatch lines (divided by the repeat count). Grains along each line use `spacing`. Smaller smears into a dusty fill; larger gives distinct strokes. |
| `skip_text` | `True` | Never grain text — draw every glyph crisp. Detected structurally: a filled path drawn with linewidth 0 (matplotlib's `_draw_text_as_path` forces that) that is also curved, multi-subpath, or short (`< 4 × min_extent` px tall) — so straight-edged digits and the minus sign are caught too. Checked **before** the `min_extent` guard so short tick labels don't slip through. `False` lets text be grained. The chalk look for labels comes from the `font` you pass to `chalk()`, not the grain. |
| `min_extent` | `26.0` | Artists whose pixel bounding box is smaller than this in **both** dimensions skip the grainy **outline** (it would just swamp them) and get a crisp edge instead — keeps tick marks and small markers sharp. A small **filled** patch (a short histogram bar) still gets the `keep_fill` / `fill_density` fill treatment, so it matches its taller neighbours. Set to `0` to texturize everything. |
| `flat_bg` | `0.5` | A filled rectangle (≤ 5 vertices) whose bounding box covers at least this fraction of the canvas is painted **flat, with no grain**. This removes the grainy frame around the whole figure and the redundant border on the axes background — the spines still get chalked. Set to `1.0` to spare only a full-canvas figure patch, or `0` to grain every rectangle. |

---

## Fonts

You have the `.ttf` files, so nothing needs installing — register them at
runtime. Easiest is to pass them straight to `chalk()`:

```python
with chalk(font="fonts/MyChalkFont-Regular.ttf"):
    ...
```

Pass every face you have so bold/italic resolve correctly, or point at a folder:

```python
chalk(font=["fonts/MyChalkFont-Regular.ttf",
            "fonts/MyChalkFont-Bold.ttf",
            "fonts/MyChalkFont-Italic.ttf"])

chalk(font="fonts/")          # registers every .ttf/.otf in the directory
```

Or register once, up front, and reuse the name yourself:

```python
from chalk import use_font

use_font("fonts/")                       # sets rcParams["font.family"]
name = use_font("fonts/", set_family=False)   # just register, returns the name
```

`use_font(*paths, set_family=True)` calls `matplotlib.font_manager.fontManager.addfont`
on each file (directories are scanned for `*.ttf`/`*.otf`), and returns the
family name of the last face — which is what lands in
`rcParams["font.family"]`. No font-cache rebuild is needed.

---

## Recipes

**Straight but chalk-textured** — no wobble from either source:

```python
with chalk(sketch=None, wander=0):
    ...
```

**Just a bit of wobble, subtle grain:**

```python
with chalk(sketch=(1, 100, 1), spread=0.8, passes=2, wander=1.0):
    ...
```

**Heavy, dusty chalk:**

```python
with chalk(spread=2.2, jitter=1.4, grain=3.0, passes=4, spacing=1.3):
    ...
```

**Chalky hatched bars** — the `hatch=` on each patch is redrawn as grain lines
(matplotlib's own hatch is otherwise dropped):

```python
with chalk(sketch=None):
    ax.bar(x, y, facecolor="none", edgecolor="#a8d8ff", hatch="//")
    ax.bar(x, y2, facecolor="none", edgecolor="#ffb3c6", hatch="xx")
```

Or force one angle on every patch: `chalk(sketch=None, hatch=45)`. Widen the
lines with `hatch_spacing`.

**Recolour the board** (e.g. dark green chalkboard):

```python
with chalk(board="#0d1f14", panel="#0d1f14", grid="#2e4a38"):
    ...
```

**Reproducible output:**

```python
with chalk(seed=0):
    ...
```

**Wobble only, no grain:**

```python
import matplotlib as mpl
chalk()
mpl.rcParams["path.effects"] = []
```

**Exempt a specific artist** (path effects fall back to the rc default, so clear
the list on that artist):

```python
fig.patch.set_path_effects([])     # plain figure background
ax.patch.set_path_effects([])      # plain axes panel
some_line.set_path_effects([])     # this one line stays crisp
```

---

## Notes & limitations

- **Agg only.** `path.sketch` and `renderer.draw_markers` are Agg-renderer
  features; the SVG/PDF backends will not reproduce the grain.
- **Text** is routed through the path-effects machinery once `path.effects` is
  set. `ChalkEffect` detects it structurally — a filled path drawn with
  linewidth 0 (matplotlib's `_draw_text_as_path` forces that) that is curved,
  multi-subpath, or short — and always draws it crisp. The chalk look for text
  comes from the `font` you pass, not the grain. Set `skip_text=False` to grain
  it anyway.
- **Plot markers** (`marker="o"` etc.) become fuzzy chalk blobs — on theme, but
  be aware.
- The grain is regenerated every draw. With `seed=None` an interactive figure
  will shimmer slightly on each redraw; set `seed` to freeze it.
