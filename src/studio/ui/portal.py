"""Launcher-only vector art. No images, network access, fonts or render service."""
from __future__ import annotations

import math
from PySide6 import QtCore, QtGui, QtWidgets


LAUNCHER_STYLE = """
QWidget#studioLauncher { background: #0C1024; color: #EEF2FF; }
QWidget#studioLauncher QLabel { background: transparent; color: #EEF2FF; font-size: 13px; }
QWidget#studioLauncher QLabel#eyebrow { color: #71EBDD; font-size: 11px; font-weight: 700; }
QWidget#studioLauncher QLabel#brand { color: #F7F3FF; font-size: 19px; font-weight: 800; }
QWidget#studioLauncher QLabel#portalTitle { color: #F7F3FF; font-size: 54px; font-weight: 900; }
QWidget#studioLauncher QLabel#portalSubtitle { color: #D6CCEE; font-size: 19px; }
QWidget#studioLauncher QLabel#muted { color: #B2BDD8; }
QWidget#studioLauncher QLabel#statusMessage { color: #DEE7FC; padding: 12px; background: #1B2340; border-left: 3px solid #6EE6D6; }
QWidget#studioLauncher QFrame#launchDeck { background: #11182F; border-left: 1px solid #303A5D; }
QWidget#studioLauncher QFrame#runtimeSheet { background: #161F39; border: 1px solid #354063; border-radius: 12px; }
QWidget#studioLauncher QLineEdit, QWidget#studioLauncher QComboBox {
 background: #0D142A; color: #ECF4FF; border: 1px solid #3B486B;
 border-radius: 5px; padding: 9px; min-height: 20px; selection-background-color: #37466E;
}
QWidget#studioLauncher QLineEdit:focus, QWidget#studioLauncher QComboBox:focus { border: 1px solid #72ECDD; }
QWidget#studioLauncher QLineEdit:read-only { color: #B6C4DC; }
QWidget#studioLauncher QComboBox::drop-down { border: none; width: 24px; }
QWidget#studioLauncher QComboBox QAbstractItemView { background: #172039; color: #EEF2FF; selection-background-color: #344867; }
QWidget#studioLauncher QListWidget { background: #0D142A; color: #DFE9FF; border: 1px solid #354063; border-radius: 8px; outline: none; }
QWidget#studioLauncher QListWidget::item { padding: 12px; margin: 3px; border: 1px solid transparent; border-radius: 5px; }
QWidget#studioLauncher QListWidget::item:selected { background: #233950; border: 1px solid #6BE7D7; color: #F2FFFF; }
QWidget#studioLauncher QListWidget::item:hover { background: #252E4D; }
QWidget#studioLauncher QPushButton { background: #222E4B; color: #EBF0FF; border: 1px solid #435375; border-radius: 5px; padding: 9px 13px; font-weight: 600; }
QWidget#studioLauncher QPushButton:hover { background: #324464; border-color: #72ECDD; }
QWidget#studioLauncher QPushButton:pressed { background: #142B3A; }
QWidget#studioLauncher QPushButton:disabled { background: #1B253B; color: #7785A3; border-color: #2C3650; }
QWidget#studioLauncher QPushButton#launchPrimary { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #7CF2DA,stop:1 #81BDF7); color: #0C2030; border: none; padding: 17px 22px; font-size: 18px; font-weight: 800; }
QWidget#studioLauncher QPushButton#launchPrimary:hover { background: #B2FFEC; }
QWidget#studioLauncher QPushButton#launchPrimary:pressed { background: #57C7C2; }
QWidget#studioLauncher QPushButton#launchPrimary:disabled { background: #263953; color: #A2B8D1; }
QWidget#studioLauncher QScrollArea { background: transparent; border: 0; }
QWidget#studioLauncher QWidget#deckBody { background: #11182F; }
QWidget#studioLauncher QScrollBar:vertical { background: #11182F; width: 7px; }
QWidget#studioLauncher QScrollBar::handle:vertical { background: #435375; border-radius: 3px; min-height: 30px; }
QWidget#studioLauncher QScrollBar::add-line:vertical, QWidget#studioLauncher QScrollBar::sub-line:vertical { height: 0; }
QToolTip { color: #F3F5FF; background: #1C2845; border: 1px solid #6BE7D7; padding: 6px; }
"""


class PortalArt(QtWidgets.QWidget):
    """A procedural wing/crystal emblem; movement only during a visible launch."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(250, 230)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        self.setAccessibleName("Studio portal illustration")
        self.phase = 0.0
        self.launching = False
        self.motion = QtCore.QTimer(self)
        self.motion.setInterval(50)
        self.motion.timeout.connect(self.advance)

    def set_launching(self, value):
        self.launching = bool(value)
        if self.launching and self.isVisible():
            self.motion.start()
        else:
            self.motion.stop()
        self.update()

    def advance(self):
        self.phase = (self.phase + 2.0) % 360.0
        self.update()

    def showEvent(self, event):
        if self.launching:
            self.motion.start()
        super().showEvent(event)

    def hideEvent(self, event):
        self.motion.stop()
        super().hideEvent(event)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        scale = min(self.width() / 470.0, self.height() / 410.0)
        painter.translate((self.width() - 470 * scale) / 2, (self.height() - 410 * scale) / 2)
        painter.scale(scale, scale)
        glow = QtGui.QRadialGradient(235, 200, 218)
        glow.setColorAt(0, QtGui.QColor(107, 59, 179, 165))
        glow.setColorAt(0.6, QtGui.QColor(50, 67, 131, 70))
        glow.setColorAt(1, QtGui.QColor(12, 16, 36, 0))
        painter.fillRect(QtCore.QRectF(0, 0, 470, 410), glow)
        painter.setPen(QtGui.QPen(QtGui.QColor(105, 133, 182, 28), 1))
        for x in range(0, 470, 30):
            painter.drawLine(x, 0, x, 410)
        for y in range(0, 410, 30):
            painter.drawLine(0, y, 470, y)
        for i in range(31):
            x, y = (i * 137 + 19) % 455, (i * 79 + 17) % 390
            painter.setPen(QtGui.QColor(146, 204, 227, 60 + i % 4 * 30))
            painter.drawLine(x - 2, y, x + 2, y)
            painter.drawLine(x, y - 2, x, y + 2)
        painter.setBrush(QtCore.Qt.NoBrush)
        for radius, color in ((164, "#39436C"), (153, "#7660A9"), (126, "#395C75")):
            painter.setPen(QtGui.QPen(QtGui.QColor(color), 1))
            painter.drawEllipse(QtCore.QPointF(235, 195), radius, radius)
        painter.setPen(QtGui.QPen(QtGui.QColor("#79F1DF"), 3))
        painter.drawArc(QtCore.QRectF(71, 31, 328, 328), int((20 + self.phase) * 16), 64 * 16)
        painter.setPen(QtGui.QPen(QtGui.QColor("#F393C9"), 2))
        painter.drawArc(QtCore.QRectF(71, 31, 328, 328), int((203 + self.phase) * 16), 40 * 16)
        for degrees in range(0, 360, 10):
            a = math.radians(degrees)
            inner = 169 if degrees % 30 else 166
            painter.setPen(QtGui.QPen(QtGui.QColor("#6A799D"), 1))
            painter.drawLine(QtCore.QPointF(235 + inner * math.cos(a), 195 + inner * math.sin(a)),
                             QtCore.QPointF(235 + 175 * math.cos(a), 195 + 175 * math.sin(a)))

        def facet(points, color, outline=None):
            painter.setBrush(QtGui.QColor(color))
            painter.setPen(QtGui.QPen(QtGui.QColor(outline), 1) if outline else QtCore.Qt.NoPen)
            painter.drawPolygon(QtGui.QPolygonF([QtCore.QPointF(x, y) for x, y in points]))

        # Broad swept wings, floating shards and a faceted procedural core.
        facet([(222, 218), (65, 74), (98, 206), (182, 257)], "#50658A", "#9EBACF")
        facet([(207, 218), (77, 89), (135, 221)], "#A6EFEE")
        facet([(166, 225), (100, 156), (115, 238), (192, 265)], "#497B99")
        facet([(243, 225), (407, 105), (368, 230), (275, 272)], "#B669AE", "#F5ADE2")
        facet([(257, 213), (393, 119), (335, 232)], "#E7B0EA")
        facet([(303, 255), (361, 202), (333, 278), (263, 295)], "#725BBA")
        facet([(235, 102), (302, 196), (237, 321), (168, 196)], "#D9FCFA", "#FFFFFF")
        facet([(235, 102), (238, 213), (168, 196)], "#80D4DC")
        facet([(235, 102), (302, 196), (238, 213)], "#FCF4FF")
        facet([(238, 213), (302, 196), (237, 321)], "#8A82DA")
        facet([(168, 196), (238, 213), (237, 321)], "#497DAD")
        facet([(227, 166), (254, 193), (232, 228), (208, 193)], "#152A49", "#B2FDF0")
        facet([(53, 242), (72, 275), (93, 244)], "#89E2D9")
        facet([(357, 59), (389, 70), (378, 40)], "#EF9ACF")
        facet([(349, 322), (366, 300), (385, 335)], "#718AD1")
        painter.setPen(QtGui.QPen(QtGui.QColor("#8FF3E3"), 1))
        painter.drawLine(50, 328, 128, 328)
        painter.drawLine(128, 328, 150, 306)
        painter.drawLine(319, 81, 341, 59)
        painter.drawLine(341, 59, 400, 59)
        font = QtGui.QFont("Consolas", 9)
        font.setLetterSpacing(QtGui.QFont.AbsoluteSpacing, 2)
        painter.setFont(font)
        painter.drawText(QtCore.QPointF(25, 351), "PROCEDURAL / CORE")
        painter.setPen(QtGui.QColor("#A99BCB"))
        painter.drawText(QtCore.QPointF(297, 383), "BCS - 001")
        painter.end()
