"""Zoomable image viewer for page images."""

from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt, QRectF
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGestureEvent,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QPinchGesture,
)


MIN_ZOOM = 0.12
MAX_ZOOM = 12.0
TOOLBAR_ZOOM_STEP = 1.15
WHEEL_ZOOM_SENSITIVITY = 0.0008
PINCH_ZOOM_SMOOTHING = 0.65
MAX_GESTURE_STEP = 1.25


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
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setInteractive(True)
        self.setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents, True)
        self.viewport().setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents, True)
        self.grabGesture(Qt.GestureType.PinchGesture)
        self.viewport().grabGesture(Qt.GestureType.PinchGesture)

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
        self._apply_zoom(TOOLBAR_ZOOM_STEP)

    def zoom_out(self) -> None:
        self._apply_zoom(1 / TOOLBAR_ZOOM_STEP)

    def wheelEvent(self, event) -> None:  # pragma: no cover - GUI interaction
        if not self.has_image():
            super().wheelEvent(event)
            return

        if self._wheel_should_zoom(event.modifiers()):
            factor = self._wheel_zoom_factor(event)
            if factor != 1.0:
                self._apply_zoom(factor, anchor_pos=event.position())
            event.accept()
            return

        # Plain two-finger scroll / mouse wheel should pan the view. Let
        # QGraphicsView handle scrollbar movement instead of treating it as zoom.
        super().wheelEvent(event)

    def event(self, event) -> bool:  # pragma: no cover - GUI interaction
        if event.type() == QEvent.Type.Gesture:
            return self._handle_gesture_event(event)
        return super().event(event)

    def viewportEvent(self, event) -> bool:  # pragma: no cover - GUI interaction
        if event.type() == QEvent.Type.Gesture:
            return self._handle_gesture_event(event)
        return super().viewportEvent(event)

    def resizeEvent(self, event) -> None:  # pragma: no cover - GUI interaction
        super().resizeEvent(event)
        if self.has_image() and self._zoom == 1.0:
            self.fit_to_view()

    def _handle_gesture_event(self, event: QGestureEvent) -> bool:
        if not self.has_image():
            return super().event(event)

        gesture = event.gesture(Qt.GestureType.PinchGesture)
        if isinstance(gesture, QPinchGesture):
            factor = self._pinch_zoom_factor(gesture.scaleFactor())
            if factor != 1.0:
                self._apply_zoom(factor, anchor_pos=self._gesture_anchor_pos(gesture))
            event.accept(gesture)
            return True
        return False

    def _wheel_should_zoom(self, modifiers: Qt.KeyboardModifier) -> bool:
        return bool(
            modifiers
            & (
                Qt.KeyboardModifier.ControlModifier
                | Qt.KeyboardModifier.MetaModifier
            )
        )

    def _wheel_zoom_factor(self, event) -> float:
        delta = event.angleDelta().y()
        if delta == 0:
            delta = event.pixelDelta().y()
        if delta == 0:
            return 1.0
        return self._bounded_step(math.exp(delta * WHEEL_ZOOM_SENSITIVITY))

    def _pinch_zoom_factor(self, scale_factor: float) -> float:
        if scale_factor <= 0:
            return 1.0
        return self._bounded_step(scale_factor ** PINCH_ZOOM_SMOOTHING)

    def _bounded_step(self, factor: float) -> float:
        return max(1 / MAX_GESTURE_STEP, min(MAX_GESTURE_STEP, factor))

    def _gesture_anchor_pos(self, gesture: QPinchGesture) -> QPoint:
        point = gesture.centerPoint().toPoint()
        if self.viewport().rect().contains(point):
            return point
        local_point = self.viewport().mapFromGlobal(point)
        if self.viewport().rect().contains(local_point):
            return local_point
        return self.viewport().rect().center()

    def _apply_zoom(self, factor: float, *, anchor_pos: QPoint | QPointF | None = None) -> None:
        if not self.has_image():
            return
        if anchor_pos is None:
            anchor = self.viewport().rect().center()
        elif isinstance(anchor_pos, QPointF):
            anchor = anchor_pos.toPoint()
        else:
            anchor = anchor_pos

        scene_anchor = self.mapToScene(anchor)
        target_zoom = max(MIN_ZOOM, min(MAX_ZOOM, self._zoom * factor))
        actual_factor = target_zoom / self._zoom
        if actual_factor == 1.0:
            return
        self._zoom = target_zoom
        self.scale(actual_factor, actual_factor)
        self._restore_anchor(scene_anchor, anchor)

    def _restore_anchor(self, scene_anchor: QPointF, viewport_anchor: QPoint) -> None:
        shifted_anchor = self.mapFromScene(scene_anchor)
        delta = shifted_anchor - viewport_anchor
        self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() + delta.x())
        self.verticalScrollBar().setValue(self.verticalScrollBar().value() + delta.y())
