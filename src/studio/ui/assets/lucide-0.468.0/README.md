# Approved Studio icons

Only the 23 names in `studio.ui.icons.APPROVED_ICONS` are product icons. Their
approved uses are fixed by the Pro presentation specification. Other actions
use text. These resources are not a product logo.

Source: [Lucide 0.468.0](https://github.com/lucide-icons/lucide/tree/f12b0de177fbc2a6795e99be065887e72b237123/icons).
The GitHub tag ref `0.468.0` was checked against commit
`f12b0de177fbc2a6795e99be065887e72b237123` when importing this subset.
Each SVG and `LICENSE` are the upstream bytes, with no path edits. Rendering
changes only color, size and the expressly allowed `loader-circle` rotation.

`LICENSE` contains the complete ISC license from the fixed Lucide commit,
including its Feather attribution. `LICENSE-Feather` contains the complete MIT
license from [Feather v4.29.2](https://github.com/feathericons/feather/blob/v4.29.2/LICENSE).
Both copyright and permission notices are distributed with these resources.

Use `icon(name, size=20, color=None, dpr=1.0)` only on the existing Qt GUI thread.
`set_button_icon(button, name, text=..., icon_only=...)` preserves the existing
button and action, handles display-scale changes and retains action text if a
resource cannot load. Fixed-size icon actions keep compact padding even when
showing text. For longer labels, an explicit `fallback_text` supplies a short
visible label; `text` remains the full tooltip and accessible name. Font size
and the caller's button geometry are preserved.
`LoadingIcon.set_busy()` stops its timer when idle, hidden
or minimized. Missing-resource records are available from `icon_diagnostics()`
for existing details views; the loader creates no new user alerts.
