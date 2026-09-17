"""The owner's light Launcher palette; the Houdini Panel keeps its own theme."""
from pathlib import Path
import re

from .theme import COLORS, studio_stylesheet

ARTWORK = Path(__file__).parent / 'assets/launcher-artwork'
ACCENT = '#416EB2'
INK = '#203B5D'
BACKGROUND = '#EEF6FC'
_PALETTE = {
    'background': BACKGROUND, 'surface': '#F8FCFF', 'surface_elevated': '#E4EFF8',
    'surface_hover': '#D5E7F5', 'surface_pressed': '#C7DEEF',
    'text_primary': INK, 'text_secondary': '#46607A', 'text_muted': '#60768C',
    'border_subtle': '#C5D8E8', 'border_control': '#839FB9',
    'primary_pink': ACCENT, 'primary_hover': '#345E9D', 'primary_pressed': '#294C82',
    'on_primary': '#FFFFFF', 'selected_surface': '#D5E9FA', 'focus_ring': ACCENT,
    'disabled_surface': '#E2EAF1', 'disabled_text': '#778999',
    'success': '#287B69', 'warning': '#8A5E10', 'error': '#B44857',
}
_LIGHT = {COLORS[name]: value for name, value in _PALETTE.items()}


def launcher_stylesheet(root_name):
    return re.sub(r'#[0-9A-Fa-f]{6}', lambda match: _LIGHT.get(match[0], match[0]),
                  studio_stylesheet(root_name))


def style_launcher_popup(widget):
    widget.setProperty('studioRole', 'popup')
    widget.setStyleSheet(launcher_stylesheet(widget.objectName()))
