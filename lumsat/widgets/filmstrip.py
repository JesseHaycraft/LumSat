"""Left-side filmstrip: a vertical list of imported photos.

Each row shows a thumbnail and the file name. Selecting a row tells the rest of
the app which :class:`ImageItem` is active via the ``selection_changed`` signal.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QListWidget, QListWidgetItem

from ..models.image_item import ImageItem
from ..qt_util import ndarray_to_qpixmap


class Filmstrip(QListWidget):
    # Emits the index of the newly selected image, or -1 if none.
    selection_changed = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self.setIconSize(QSize(96, 96))
        self.setSpacing(2)
        self.setUniformItemSizes(False)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.currentRowChanged.connect(self.selection_changed)

    def add_image(self, item: ImageItem) -> None:
        """Append a thumbnail row for a freshly imported image."""
        icon = QIcon(ndarray_to_qpixmap(item.thumbnail))
        list_item = QListWidgetItem(icon, item.name)
        list_item.setToolTip(item.source_path)
        self.addItem(list_item)

    def select(self, index: int) -> None:
        if 0 <= index < self.count():
            self.setCurrentRow(index)
