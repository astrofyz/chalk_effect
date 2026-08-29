# chalk

Chalk-on-a-blackboard styling for matplotlib, applied **globally** like
`plt.xkcd()` — every line, spine, tick, grid line, patch edge and legend frame
in the figure gets the treatment, not just artists you opt in by hand.

The look is two independent effects:

1. **Wobble** — matplotlib's built-in `path.sketch` rcParam, applied by the Agg
   renderer to every path. This is the same mechanism `plt.xkcd()` uses.
2. **Grain** — `ChalkEffect`, a custom path effect installed into
   `rcParams["path.effects"]`. It redraws each stroke as a cloud of jittered
   chalk grains rendered with `renderer.draw_markers` (the fast C path, the same
   one `scatter` uses). Cost scales with the **number of artists**, not with a
   point count you tune by hand — a whole figure is a few milliseconds.

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
installs a `ChalkEffect`. Returns an `rc_context`, so use it with `with` for a
scoped effect or call it bare to apply for the rest of the session.

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
| `seed` | `None` | Seed for the RNG. Set an int for reproducible dust across renders. |

### Centre-line wobble (independent of `path.sketch`)

| Keyword | Default | Description |
|---|---|---|
| `wander` | `2.0` | Std dev (px) of a slow, smooth sideways wobble of the stroke's **centre line**, on top of `path.sketch`. **`wander=0` gives a dead-straight centre line** that is still chalk-textured (only `spread`/`jitter` fuzz remain). |
| `wander_length` | `50.0` | Approximate wavelength (px) of that wobble. Larger → longer, lazier waves; smaller → tighter squiggles. Internally converted to a smoothing window of `wander_length / spacing` samples. |

### What to leave alone (readability guards)

| Keyword | Default | Description |
|---|---|---|
| `keep_fill` | `True` | For filled patches (bars, wedges, `fill_between`), paint the original face colour first, then lay chalk on the outline. `False` drops the fill and keeps only the grained edge. |
| `min_extent` | `26.0` | Strokes whose pixel bounding box is smaller than this in **both** dimensions are drawn normally (still wobbled by `path.sketch`) instead of grained — keeps tick marks and small markers crisp. Text is additionally spared via a separate check (filled multi-subpath runs no taller than `3 × min_extent`). Set to `0` to texturize everything, including glyphs. |
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
  set. `ChalkEffect` detects and spares it (see `min_extent`), so labels stay
  legible; large display text above `~3 × min_extent` px tall will still get
  grained.
- **Plot markers** (`marker="o"` etc.) become fuzzy chalk blobs — on theme, but
  be aware.
- The grain is regenerated every draw. With `seed=None` an interactive figure
  will shimmer slightly on each redraw; set `seed` to freeze it.
