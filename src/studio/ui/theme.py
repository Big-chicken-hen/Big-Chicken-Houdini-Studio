"""Finite Studio tokens and widget-local QSS; never change the host application."""
from __future__ import annotations

import re
from types import MappingProxyType

COLORS = MappingProxyType({
    "background": "#17181C", "surface": "#202127", "surface_elevated": "#292B33",
    "surface_hover": "#343641", "surface_pressed": "#1B1C22",
    "text_primary": "#F4F4F6", "text_secondary": "#C3C5CE", "text_muted": "#989CAA",
    "border_subtle": "#454956", "border_control": "#6E7382",
    "primary_pink": "#EFA2BD", "primary_hover": "#F6B6CC", "primary_pressed": "#D980A4",
    "on_primary": "#27141F", "selected_surface": "#392A34", "focus_ring": "#F7BCD2",
    "disabled_surface": "#292B31", "disabled_text": "#797E89",
    "success": "#8ED5AD", "warning": "#E8C27A", "error": "#F0989B",
})
SPACING = (4, 8, 12, 16, 24, 32)
RADII = MappingProxyType({"control": 6, "surface": 8, "composer": 10})
FONT_POINTS = MappingProxyType({"body": 11, "meta": 9.5, "section": 13, "title": 19})


def studio_stylesheet(root_name):
    """Every selector has the caller's root ID, including pseudo states."""
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", root_name):
        raise ValueError("Use a plain Studio root object name")
    root, c = "QWidget#" + root_name, COLORS
    rules = []

    def rule(selectors, declarations):
        scoped = [root + (" " + selector if selector else "") for selector in selectors.split(",")]
        rules.append(", ".join(scoped) + " { " + declarations + " }")

    rule("", f"background: {c['background']}; color: {c['text_primary']};")
    rule("QWidget", f"font-family: 'Segoe UI', 'Microsoft YaHei UI', sans-serif; font-size: 11pt; color: {c['text_primary']};")
    rule("QLabel", "background: transparent;")
    rule("QLabel#muted,QLabel#hint,QLabel#eyebrow", f"color: {c['text_muted']};")
    rule("QLabel#eyebrow", "font-size: 9.5pt;")
    rule("QLabel#heading,QLabel#title", "font-size: 19pt; font-weight: 600;")
    rule("QLabel#brand,QLabel#sectionTitle", "font-size: 13pt; font-weight: 600;")
    rule("QLabel[tone='error']", f"color: {c['error']};")
    rule("QLabel[tone='warning'],QLabel[tone='unknown']", f"color: {c['warning']};")
    rule("QLabel[tone='success']", f"color: {c['success']};")
    rule("QFrame#card,QFrame#surface", f"background: {c['surface']}; border: 1px solid {c['border_subtle']}; border-radius: 8px;")
    rule("QFrame#composer,QFrame#studioError", f"background: {c['surface_elevated']}; border: 1px solid {c['border_subtle']}; border-radius: 10px;")
    rule("QPushButton,QToolButton", f"background: {c['surface_elevated']}; border: 2px solid {c['border_subtle']}; border-radius: 6px; padding: 5px 10px; min-height: 16px;")
    rule("QPushButton:hover,QToolButton:hover", f"background: {c['surface_hover']}; border-color: {c['border_control']};")
    rule("QPushButton:pressed,QToolButton:pressed", f"background: {c['surface_pressed']};")
    rule("QPushButton:checked,QToolButton:checked", f"background: {c['selected_surface']}; border-color: {c['primary_pink']};")
    primary = "QPushButton#primary,QPushButton#stop,QPushButton[studioRole='primary']"
    rule(primary, f"background: {c['primary_pink']}; color: {c['on_primary']}; border-color: {c['primary_pink']}; font-weight: 600;")
    rule(",".join(s + ":hover" for s in primary.split(",")), f"background: {c['primary_hover']}; border-color: {c['primary_hover']};")
    rule(",".join(s + ":pressed" for s in primary.split(",")), f"background: {c['primary_pressed']}; border-color: {c['primary_pressed']};")
    rule("QPushButton#quiet,QToolButton#quiet,QPushButton[studioRole='quiet']", f"background: transparent; color: {c['text_secondary']}; border-color: transparent;")
    rule("QPushButton#quiet:hover,QToolButton#quiet:hover,QPushButton[studioRole='quiet']:hover", f"background: {c['surface_hover']};")
    rule("QPushButton#quiet:pressed,QToolButton#quiet:pressed,QPushButton[studioRole='quiet']:pressed", f"background: {c['surface_pressed']};")
    rule("QPushButton[studioRole='danger']", f"color: {c['error']};")
    rule("QPushButton:focus,QToolButton:focus", f"border-color: {c['focus_ring']};")
    rule(",".join(s + ":focus" for s in primary.split(",")), f"border-color: {c['focus_ring']};")
    rule("QPushButton:disabled,QToolButton:disabled", f"background: {c['disabled_surface']}; color: {c['disabled_text']}; border-color: {c['border_subtle']};")
    rule(",".join(s + ":disabled" for s in primary.split(",")), f"background: {c['disabled_surface']}; color: {c['disabled_text']}; border-color: {c['border_subtle']};")
    rule("QLineEdit,QComboBox,QTextEdit,QPlainTextEdit", f"background: {c['surface_elevated']}; border: 2px solid {c['border_control']}; border-radius: 6px; padding: 5px 8px; selection-background-color: {c['selected_surface']}; selection-color: {c['text_primary']};")
    rule("QLineEdit:focus,QComboBox:focus,QTextEdit:focus,QPlainTextEdit:focus", f"border-color: {c['focus_ring']};")
    rule("QLineEdit:disabled,QComboBox:disabled,QTextEdit:disabled,QPlainTextEdit:disabled", f"color: {c['disabled_text']}; background: {c['disabled_surface']}; border-color: {c['border_subtle']};")
    rule("QComboBox::drop-down", "border: 0; width: 24px;")
    rule("QComboBox QAbstractItemView", f"background: {c['surface_elevated']}; color: {c['text_primary']}; selection-background-color: {c['selected_surface']}; selection-color: {c['text_primary']};")
    rule("QTextBrowser,QScrollArea", "background: transparent; border: 0;")
    rule("QPlainTextEdit#statusDetails", "background: transparent; border: 0; font-size: 9.5pt;")
    rule("QListWidget", f"background: {c['surface']}; border: 1px solid {c['border_subtle']}; border-radius: 8px; outline: 0; padding: 4px;")
    rule("QListWidget::item", "border: 2px solid transparent; border-radius: 6px; padding: 8px; margin: 2px;")
    rule("QListWidget::item:hover", f"background: {c['surface_hover']};")
    rule("QListWidget::item:selected", f"background: {c['selected_surface']}; border-color: {c['primary_pink']};")
    rule("QTabWidget::pane", "border: 0;")
    rule("QTabBar::tab", f"background: transparent; color: {c['text_secondary']}; padding: 8px 12px; border-bottom: 2px solid transparent;")
    rule("QTabBar::tab:selected", f"color: {c['text_primary']}; border-bottom-color: {c['primary_pink']};")
    rule("QScrollBar:vertical", "background: transparent; width: 8px; margin: 0;")
    rule("QScrollBar::handle:vertical", f"background: {c['border_control']}; min-height: 28px; border-radius: 4px;")
    rule("QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical", "height: 0;")
    rule("QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical", "background: transparent;")
    rule("QCheckBox", f"spacing: 8px; color: {c['text_secondary']};")
    return "\n".join(rules)


def apply_theme(root):
    """Theme one Studio root. Host application font/style/palette remain untouched."""
    root.setStyleSheet(studio_stylesheet(root.objectName()))
