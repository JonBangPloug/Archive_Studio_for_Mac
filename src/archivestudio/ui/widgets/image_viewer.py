"""Zoomable image viewer for page images."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import QFrame, QGraphicsPixmapItem, QGraphicsScene, QGraphicsView


class ImageViewer(QGraphicsView):
    """Simple QGraphicsView-based page viewer with zoom, pan, and fit-to-view."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self._pixmap_item = QGraphicsPixmapItem()
        self._scene.addItem(self._pixmap_item)
        self.setScene(self._scene)

        self._current_pixmap = QPixmap()
        self._zoom = 1.0

        self.setRenderHints(
            QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setBackgroundBrush(Qt.GlobalColor.darkGray)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)

    def has_image(self) -> bool:
        return not self._current_pixmap.isNull()

    def clear_image(self) -> None:
        self._current_pixmap = QPixmap()
        self._pixmap_item.setPixmap(self._current_pixmap)
        self._scene.setSceneRect(QRectF())
        self._zoom = 1.0
        self.resetTransform()
        self.setDragMode(QGraphicsView.DragMode.NoDrag)

    def set_image_path(self, path: Path | None) -> bool:
        if path is None:
            self.clear_image()
            return False

        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self.clear_image()
            return False

        self._current_pixmap = pixmap
        self._pixmap_item.setPixmap(pixmap)
        self._scene.setSceneRect(QRectF(pixmap.rect()))
        self._zoom = 1.0
        self.resetTransform()
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.fit_to_view()
        return True

    def fit_to_view(self) -> None:
        if not self.has_image():
            return
        self.resetTransform()
        self._zoom = 1.0
        self.fitInView(self._pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)

    def zoom_in(self) -> None:
        self._apply_zoom(1.2)

    def zoom_out(self) -> None:
        self._apply_zoom(1 / 1.2)

    def wheelEvent(self, event) -> None:  # pragma: no cover - GUI interaction
        if not self.has_image():
            super().wheelEvent(event)
            return
        if event.angleDelta().y() > 0:
            self.zoom_in()
        else:
            self.zoom_out()
        event.accept()

    def resizeEvent(self, event) -> None:  # pragma: no cover - GUI interaction
        super().resizeEvent(event)
        if self.has_image() and self._zoom == 1.0:
            self.fit_to_view()

    def _apply_zoom(self, factor: float) -> None:
        if not self.has_image():
            return
        self._zoom *= factor
        self.scale(factor, factor)
