from pathlib import Path
import json

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QDoubleSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.io.project_json_generator import (
    crop_image_to_content,
    is_supported_image,
    polygon_from_cropped_image,
    scale_polygon_points,
)


class FootprintMetadataWidget(QWidget):
    def __init__(self, image_path: Path, cropped_pixel_width: int, cropped_pixel_height: int) -> None:
        super().__init__()

        self.image_path = image_path

        layout = QFormLayout(self)

        self.title_label = QLabel(
            f"{image_path.name} | cropped: {cropped_pixel_width} x {cropped_pixel_height} px"
        )
        self.title_label.setWordWrap(True)
        layout.addRow(self.title_label)

        self.id_edit = QLineEdit()
        self.id_edit.setText(image_path.stem)
        layout.addRow("Footprint id:", self.id_edit)

        self.width_spin = QDoubleSpinBox()
        self.width_spin.setRange(0.000001, 1_000_000)
        self.width_spin.setDecimals(4)
        self.width_spin.setValue(float(cropped_pixel_width))
        layout.addRow("Real width:", self.width_spin)

        self.height_spin = QDoubleSpinBox()
        self.height_spin.setRange(0.000001, 1_000_000)
        self.height_spin.setDecimals(4)
        self.height_spin.setValue(float(cropped_pixel_height))
        layout.addRow("Real height:", self.height_spin)

        self.quantity_spin = QSpinBox()
        self.quantity_spin.setRange(0, 1_000_000)
        self.quantity_spin.setValue(0)
        self.quantity_spin.setSpecialValueText("Unlimited")
        layout.addRow("Quantity:", self.quantity_spin)

        self.allow_rotation_check = QCheckBox()
        self.allow_rotation_check.setChecked(True)
        layout.addRow("Allow rotation:", self.allow_rotation_check)

    def to_dict(self, crop_info: dict) -> dict:
        quantity = self.quantity_spin.value()
        return {
            "id": self.id_edit.text().strip(),
            "width": self.width_spin.value(),
            "height": self.height_spin.value(),
            "allow_rotation": self.allow_rotation_check.isChecked(),
            "quantity": None if quantity == 0 else quantity,
            "source_image": crop_info["original_path"],
            "cropped_image": crop_info["cropped_path"],
            "cropped_pixel_width": crop_info["cropped_pixel_size"]["width"],
            "cropped_pixel_height": crop_info["cropped_pixel_size"]["height"],
            "crop_bbox": crop_info["bbox"],
        }


class ProjectGeneratorDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self.setWindowTitle("Generate Project JSON from Images")
        self.resize(900, 700)

        self.selected_images: list[Path] = []
        self.crop_infos: list[dict] = []
        self.footprint_widgets: list[FootprintMetadataWidget] = []

        self._build_ui()

    def _build_ui(self) -> None:
        main_layout = QVBoxLayout(self)

        project_group = QGroupBox("Project settings")
        project_form = QFormLayout(project_group)

        self.panel_width_spin = QDoubleSpinBox()
        self.panel_width_spin.setRange(0.000001, 1_000_000)
        self.panel_width_spin.setDecimals(4)
        self.panel_width_spin.setValue(100.0)
        project_form.addRow("Panel width:", self.panel_width_spin)

        self.panel_height_spin = QDoubleSpinBox()
        self.panel_height_spin.setRange(0.000001, 1_000_000)
        self.panel_height_spin.setDecimals(4)
        self.panel_height_spin.setValue(80.0)
        project_form.addRow("Panel height:", self.panel_height_spin)

        self.spacing_spin = QDoubleSpinBox()
        self.spacing_spin.setRange(0.0, 1_000_000)
        self.spacing_spin.setDecimals(4)
        self.spacing_spin.setValue(2.0)
        project_form.addRow("Spacing:", self.spacing_spin)

        self.threshold_spin = QSpinBox()
        self.threshold_spin.setRange(0, 255)
        self.threshold_spin.setValue(245)
        project_form.addRow("Crop threshold:", self.threshold_spin)

        self.margin_spin = QSpinBox()
        self.margin_spin.setRange(0, 10_000)
        self.margin_spin.setValue(0)
        project_form.addRow("Crop margin (px):", self.margin_spin)

        self.simplify_spin = QDoubleSpinBox()
        self.simplify_spin.setRange(0.0, 100.0)
        self.simplify_spin.setDecimals(3)
        self.simplify_spin.setValue(1.0)
        project_form.addRow("Polygon simplify (px):", self.simplify_spin)

        self.generate_polygon_check = QCheckBox()
        self.generate_polygon_check.setChecked(True)
        project_form.addRow("Generate polygon_points:", self.generate_polygon_check)

        main_layout.addWidget(project_group)

        buttons_row = QHBoxLayout()

        self.select_images_button = QPushButton("Select images")
        self.select_images_button.clicked.connect(self.select_images)
        buttons_row.addWidget(self.select_images_button)

        self.save_json_button = QPushButton("Save JSON")
        self.save_json_button.clicked.connect(self.save_json)
        self.save_json_button.setEnabled(False)
        buttons_row.addWidget(self.save_json_button)

        main_layout.addLayout(buttons_row)

        self.info_label = QLabel("No images selected.")
        self.info_label.setWordWrap(True)
        main_layout.addWidget(self.info_label)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)

        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setAlignment(Qt.AlignTop)

        self.scroll_area.setWidget(self.scroll_content)
        main_layout.addWidget(self.scroll_area, stretch=1)

        button_box = QDialogButtonBox(QDialogButtonBox.Close)
        button_box.rejected.connect(self.reject)
        main_layout.addWidget(button_box)

    def select_images(self) -> None:
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select footprint images",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp)",
        )

        if not file_paths:
            return

        image_paths = [Path(p) for p in file_paths]
        invalid = [p for p in image_paths if not is_supported_image(p)]
        if invalid:
            QMessageBox.critical(
                self,
                "Invalid files",
                "Some selected files are not supported images.",
            )
            return

        self._clear_footprint_widgets()
        self.selected_images = image_paths
        self.crop_infos = []

        cropped_dir = Path("assets/footprints")
        threshold = self.threshold_spin.value()
        margin = self.margin_spin.value()

        try:
            for image_path in self.selected_images:
                crop_info = crop_image_to_content(
                    image_path=image_path,
                    output_dir=cropped_dir,
                    threshold=threshold,
                    margin=margin,
                )
                self.crop_infos.append(crop_info)

                widget = FootprintMetadataWidget(
                    image_path=image_path,
                    cropped_pixel_width=crop_info["cropped_pixel_size"]["width"],
                    cropped_pixel_height=crop_info["cropped_pixel_size"]["height"],
                )
                self.footprint_widgets.append(widget)
                self.scroll_layout.addWidget(widget)
        except Exception as exc:
            QMessageBox.critical(self, "Crop error", str(exc))
            self._clear_footprint_widgets()
            self.selected_images = []
            self.crop_infos = []
            self.save_json_button.setEnabled(False)
            self.info_label.setText("No images selected.")
            return

        self.info_label.setText(f"Loaded {len(self.selected_images)} image(s).")
        self.save_json_button.setEnabled(True)

    def save_json(self) -> None:
        if not self.selected_images or not self.footprint_widgets:
            QMessageBox.warning(self, "No data", "Select images first.")
            return

        footprints = []
        used_ids: set[str] = set()

        threshold = self.threshold_spin.value()
        simplify_tolerance_px = self.simplify_spin.value()
        generate_polygon_points = self.generate_polygon_check.isChecked()

        for widget, crop_info in zip(self.footprint_widgets, self.crop_infos):
            data = widget.to_dict(crop_info)

            if not data["id"]:
                QMessageBox.warning(self, "Invalid data", "Footprint id cannot be empty.")
                return

            if data["id"] in used_ids:
                QMessageBox.warning(
                    self,
                    "Duplicate id",
                    f"Duplicate footprint id: {data['id']}",
                )
                return

            used_ids.add(data["id"])

            if generate_polygon_points:
                try:
                    polygon_px = polygon_from_cropped_image(
                        crop_info["cropped_path"],
                        threshold=threshold,
                        simplify_tolerance_px=simplify_tolerance_px,
                    )
                    polygon_real = scale_polygon_points(
                        polygon_points_px=polygon_px,
                        pixel_width=crop_info["cropped_pixel_size"]["width"],
                        pixel_height=crop_info["cropped_pixel_size"]["height"],
                        real_width=data["width"],
                        real_height=data["height"],
                    )
                    data["polygon_points"] = polygon_real
                except Exception as exc:
                    QMessageBox.critical(
                        self,
                        "Polygon generation error",
                        f"Failed for {Path(crop_info['cropped_path']).name}:\n{exc}",
                    )
                    return

            footprints.append(data)

        project_data = {
            "panel": {
                "width": self.panel_width_spin.value(),
                "height": self.panel_height_spin.value(),
            },
            "spacing": self.spacing_spin.value(),
            "footprints": footprints,
        }

        output_path_str, _ = QFileDialog.getSaveFileName(
            self,
            "Save project JSON",
            "examples/generated_project.json",
            "JSON Files (*.json)",
        )

        if not output_path_str:
            return

        output_path = Path(output_path_str)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            output_path.write_text(
                json.dumps(project_data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as exc:
            QMessageBox.critical(self, "Save error", str(exc))
            return

        QMessageBox.information(
            self,
            "Success",
            f"Project JSON saved to:\n{output_path}",
        )

    def _clear_footprint_widgets(self) -> None:
        while self.scroll_layout.count():
            item = self.scroll_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.footprint_widgets.clear()