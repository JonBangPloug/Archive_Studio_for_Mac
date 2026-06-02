"""Image viewer zoom policy tests."""

from __future__ import annotations

from pathlib import Path

from PIL import Image
from PySide6.QtCore import QPoint, Qt

from archivestudio.ui.widgets.image_viewer import (
    MAX_GESTURE_STEP,
    MAX_ZOOM,
    MIN_ZOOM,
    TOOLBAR_ZOOM_STEP,
    ImageViewer,
)


def test_zoom_requires_modifier_for_wheel(qtbot) -> None:
    viewer = ImageViewer()
    qtbot.addWidget(viewer)

    assert viewer._wheel_should_zoom(Qt.KeyboardModifier.NoModifier) is False
    assert viewer._wheel_should_zoom(Qt.KeyboardModifier.ControlModifier) is True
    assert viewer._wheel_should_zoom(Qt.KeyboardModifier.MetaModifier) is True


def test_wheel_zoom_factor_is_gentle(qtbot) -> None:
    viewer = ImageViewer()
    qtbot.addWidget(viewer)

    zoom_in = viewer._wheel_zoom_factor(_FakeWheelEvent(angle_y=120))
    zoom_out = viewer._wheel_zoom_factor(_FakeWheelEvent(angle_y=-120))

    assert 1.0 < zoom_in < TOOLBAR_ZOOM_STEP
    assert 1 / TOOLBAR_ZOOM_STEP < zoom_out < 1.0


def test_pinch_zoom_factor_is_smoothed_and_bounded(qtbot) -> None:
    viewer = ImageViewer()
    qtbot.addWidget(viewer)

    assert 1.0 < viewer._pinch_zoom_factor(1.2) < 1.2
    assert viewer._pinch_zoom_factor(10.0) == MAX_GESTURE_STEP
    assert viewer._pinch_zoom_factor(0.01) == 1 / MAX_GESTURE_STEP


def test_toolbar_zoom_uses_moderate_step_and_clamps(qtbot, tmp_path: Path) -> None:
    viewer = ImageViewer()
    qtbot.addWidget(viewer)
    image_path = tmp_path / "page.png"
    Image.new("RGB", (80, 60), color="white").save(image_path)

    assert viewer.set_image_path(image_path) is True
    assert viewer._zoom == 1.0

    viewer.zoom_in()
    assert viewer._zoom == TOOLBAR_ZOOM_STEP

    viewer.zoom_out()
    assert viewer._zoom == 1.0

    viewer._apply_zoom(10_000)
    assert viewer._zoom == MAX_ZOOM

    viewer._apply_zoom(0.00001)
    assert viewer._zoom == MIN_ZOOM


class _FakeWheelEvent:
    def __init__(self, *, angle_y: int = 0, pixel_y: int = 0) -> None:
        self._angle_delta = QPoint(0, angle_y)
        self._pixel_delta = QPoint(0, pixel_y)

    def angleDelta(self) -> QPoint:
        return self._angle_delta

    def pixelDelta(self) -> QPoint:
        return self._pixel_delta
