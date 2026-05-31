"""Right-side options panel: per-image actions and preset management."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
)

from ..models.preset import Preset

# Default strength applied when the user first ticks "Protect skin tones".
_DEFAULT_SKIN_PROTECT = 0.6


class OptionsPanel(QFrame):
    reset_curve_requested = Signal()
    save_preset_requested = Signal()
    apply_preset_requested = Signal(object)  # Preset, to current image
    apply_preset_all_requested = Signal(object)  # Preset, to every image
    skin_protect_changed = Signal(float)  # 0..1 strength for the current image

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("Panel")
        self.setMinimumWidth(200)
        self._presets: list[Preset] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        layout.addWidget(self._heading("Curve"))
        reset_curve = QPushButton("Reset Curve")
        reset_curve.clicked.connect(self.reset_curve_requested)
        layout.addWidget(reset_curve)

        save_preset = QPushButton("Save as Preset…")
        save_preset.clicked.connect(self.save_preset_requested)
        layout.addWidget(save_preset)

        layout.addWidget(self._heading("Color"))
        self._skin_check = QCheckBox("Protect skin tones")
        self._skin_check.setToolTip(
            "Keep skin-toned colors near their original saturation while the "
            "curve reshapes everything else."
        )
        self._skin_check.toggled.connect(self._on_skin_toggled)
        layout.addWidget(self._skin_check)

        strength_row = QHBoxLayout()
        strength_row.addWidget(QLabel("Strength"))
        self._skin_slider = QSlider(Qt.Orientation.Horizontal)
        self._skin_slider.setRange(0, 100)
        self._skin_slider.setValue(int(_DEFAULT_SKIN_PROTECT * 100))
        self._skin_slider.valueChanged.connect(self._on_skin_slider)
        strength_row.addWidget(self._skin_slider, 1)
        layout.addLayout(strength_row)
        self._skin_slider.setEnabled(False)

        layout.addWidget(self._heading("Presets"))
        self._preset_combo = QComboBox()
        layout.addWidget(self._preset_combo)

        apply_one = QPushButton("Apply to Image")
        apply_one.clicked.connect(self._emit_apply_one)
        layout.addWidget(apply_one)

        apply_all = QPushButton("Apply to All Images")
        apply_all.clicked.connect(self._emit_apply_all)
        layout.addWidget(apply_all)

        layout.addStretch(1)

    def _heading(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("Heading")
        return label

    # ------------------------------------------------------------------ #
    # Presets
    # ------------------------------------------------------------------ #

    def set_presets(self, presets: list[Preset]) -> None:
        """Refresh the preset dropdown contents."""
        self._presets = presets
        self._preset_combo.clear()
        if presets:
            self._preset_combo.addItems([p.name for p in presets])
        else:
            self._preset_combo.addItem("(no presets saved)")
            self._preset_combo.setEnabled(False)
            return
        self._preset_combo.setEnabled(True)

    def select_preset(self, name: str) -> None:
        """Make the preset called ``name`` the active dropdown selection."""
        for i, preset in enumerate(self._presets):
            if preset.name == name:
                self._preset_combo.setCurrentIndex(i)
                return

    def _selected_preset(self) -> Preset | None:
        idx = self._preset_combo.currentIndex()
        if 0 <= idx < len(self._presets):
            return self._presets[idx]
        return None

    def _emit_apply_one(self) -> None:
        preset = self._selected_preset()
        if preset is not None:
            self.apply_preset_requested.emit(preset)

    def _emit_apply_all(self) -> None:
        preset = self._selected_preset()
        if preset is not None:
            self.apply_preset_all_requested.emit(preset)

    # ------------------------------------------------------------------ #
    # Skin-tone protection
    # ------------------------------------------------------------------ #

    def set_skin_protect(self, value: float) -> None:
        """Reflect the selected image's skin-protect setting without emitting."""
        on = value > 0.0
        for w in (self._skin_check, self._skin_slider):
            w.blockSignals(True)
        self._skin_check.setChecked(on)
        if on:
            self._skin_slider.setValue(int(round(value * 100)))
        self._skin_slider.setEnabled(on)
        for w in (self._skin_check, self._skin_slider):
            w.blockSignals(False)

    def _current_skin_protect(self) -> float:
        if not self._skin_check.isChecked():
            return 0.0
        return self._skin_slider.value() / 100.0

    def _on_skin_toggled(self, checked: bool) -> None:
        self._skin_slider.setEnabled(checked)
        self.skin_protect_changed.emit(self._current_skin_protect())

    def _on_skin_slider(self, _value: int) -> None:
        if self._skin_check.isChecked():
            self.skin_protect_changed.emit(self._current_skin_protect())
