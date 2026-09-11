"""Encode the approved portrait as a Windows multi-size ICO without altering it."""
from pathlib import Path
import struct

from PySide6 import QtCore, QtGui


def main():
    assets = Path(__file__).resolve().parents[1] / 'src/studio/ui/assets/launcher-artwork'
    portrait = QtGui.QImage(str(assets / 'portrait.png'))
    if portrait.isNull() or portrait.width() != portrait.height():
        raise ValueError('The approved square portrait is missing')
    entries, frames = [], []
    sizes = (16, 24, 32, 48, 64, 128, 256)
    offset = 6 + 16 * len(sizes)
    for size in sizes:
        frame = portrait.scaled(size, size, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
        buffer = QtCore.QBuffer()
        buffer.open(QtCore.QIODevice.WriteOnly)
        if not frame.save(buffer, 'PNG'):
            raise ValueError('Could not encode icon frame')
        data = bytes(buffer.data())
        entries.append(struct.pack('<BBBBHHII', size % 256, size % 256, 0, 0, 1, 32, len(data), offset))
        frames.append(data)
        offset += len(data)
    (assets / 'studio.ico').write_bytes(struct.pack('<HHH', 0, 1, len(sizes)) + b''.join(entries + frames))
    print('Studio icon: ' + ', '.join(str(size) for size in sizes))


if __name__ == '__main__':
    main()
