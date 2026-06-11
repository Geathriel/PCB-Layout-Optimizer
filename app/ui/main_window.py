from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QComboBox,
    QInputDialog,
)

from app.core.cut_generator import generate_cut_paths
from app.core.gcode_generator import save_contour_gcode
from app.core.packer_naive import pack_advanced
from app.core.report import generate_text_report
from app.core.validator import validate_placements
from app.io.json_loader import load_project_from_json
from app.models.project import Project
from app.ui.canvas import LayoutCanvas
from app.ui.project_generator_dialog import ProjectGeneratorDialog


class PackingWorker(QObject):
    progress = Signal(int, int, int)
    finished = Signal(object, object, object, str)
    failed = Signal(str)

    def __init__(self, project: Project, cut_mode: str) -> None:
        super().__init__()
        self.project = project
        self.cut_mode = cut_mode
        self._cancel_requested = False

    @Slot()
    def request_cancel(self) -> None:
        self._cancel_requested = True

    def _should_cancel(self) -> bool:
        return self._cancel_requested

    def _progress_callback(self, done: int, total: int, best_count: int) -> None:
        self.progress.emit(done, total, best_count)

    @Slot()
    def run(self) -> None:
        try:
            placements = pack_advanced(
                self.project,
                workers=None,
                time_limit_seconds=60.0,
                progress_callback=self._progress_callback,
                should_cancel=self._should_cancel,
            )

            if self._cancel_requested:
                self.failed.emit("Layout generation cancelled.")
                return

            validation_result = validate_placements(self.project, placements)

            report = generate_text_report(self.project.panel, placements)

            if not validation_result.is_valid:
                report += "\n\n=== Validation errors ===\n"
                report += "\n".join(validation_result.errors)

            footprints_by_id = {
                footprint.id: footprint
                for footprint in self.project.footprints
            }

            cut_paths = generate_cut_paths(
                placements=placements,
                footprints_by_id=footprints_by_id,
                mode=self.cut_mode,
                panel=self.project.panel,
            )

            self.finished.emit(placements, footprints_by_id, cut_paths, report)

        except Exception as exc:
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        self.setWindowTitle("PCB Layout Optimizer")
        self.resize(1200, 800)

        self.current_project: Project | None = None
        self.current_placements = []
        self.current_file_path: Path | None = None

        self._packing_thread: QThread | None = None
        self._packing_worker: PackingWorker | None = None

        self._build_ui()

    def _build_ui(self) -> None:
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        root_layout = QHBoxLayout(central_widget)

        left_panel = QVBoxLayout()

        self.file_label = QLabel("No file loaded")
        left_panel.addWidget(self.file_label)

        self.generate_json_button = QPushButton("Create JSON from images")
        self.generate_json_button.clicked.connect(self.open_project_generator)
        left_panel.addWidget(self.generate_json_button)

        self.load_button = QPushButton("Load JSON")
        self.load_button.clicked.connect(self.load_json)
        left_panel.addWidget(self.load_button)

        self.generate_button = QPushButton("Generate Layout")
        self.generate_button.clicked.connect(self.generate_layout)
        self.generate_button.setEnabled(False)
        left_panel.addWidget(self.generate_button)

        self.cancel_generation_button = QPushButton("Cancel generation")
        self.cancel_generation_button.clicked.connect(self.cancel_generation)
        self.cancel_generation_button.setEnabled(False)
        left_panel.addWidget(self.cancel_generation_button)

        self.export_gcode_button = QPushButton("Export contour G-code")
        self.export_gcode_button.clicked.connect(self.export_contour_gcode)
        self.export_gcode_button.setEnabled(False)
        left_panel.addWidget(self.export_gcode_button)

        self.cut_mode_combo = QComboBox()
        self.cut_mode_combo.addItems(["none", "straight", "contour"])
        left_panel.addWidget(QLabel("Cut mode:"))
        left_panel.addWidget(self.cut_mode_combo)

        self.report_box = QTextEdit()
        self.report_box.setReadOnly(True)
        left_panel.addWidget(self.report_box, stretch=1)

        self.canvas = LayoutCanvas()

        root_layout.addLayout(left_panel, stretch=1)
        root_layout.addWidget(self.canvas, stretch=2)

    def open_project_generator(self) -> None:
        dialog = ProjectGeneratorDialog(self)
        dialog.exec()

    def load_json(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open project JSON",
            "examples",
            "JSON Files (*.json)",
        )

        if not file_path:
            return

        try:
            project = load_project_from_json(file_path)
        except Exception as exc:
            QMessageBox.critical(self, "Load error", str(exc))
            return

        self.current_project = project
        self.current_file_path = Path(file_path)
        self.current_placements = []

        self.file_label.setText(f"Loaded: {self.current_file_path.name}")
        self.report_box.setPlainText("Project loaded successfully.\nClick 'Generate Layout'.")
        self.canvas.clear_layout()

        self.generate_button.setEnabled(True)
        self.cancel_generation_button.setEnabled(False)
        self.export_gcode_button.setEnabled(False)

    def generate_layout(self) -> None:
        if self.current_project is None:
            QMessageBox.warning(self, "No project", "Load a project first.")
            return

        if self._packing_thread is not None:
            QMessageBox.warning(self, "Busy", "Layout generation is already running.")
            return

        self.current_placements = []
        self.export_gcode_button.setEnabled(False)

        self.generate_button.setEnabled(False)
        self.load_button.setEnabled(False)
        self.generate_json_button.setEnabled(False)
        self.cancel_generation_button.setEnabled(True)

        self.report_box.setPlainText("Generating layout...\n")
        self.canvas.clear_layout()

        cut_mode = self.cut_mode_combo.currentText()

        self._packing_thread = QThread(self)
        self._packing_worker = PackingWorker(self.current_project, cut_mode)
        self._packing_worker.moveToThread(self._packing_thread)

        self._packing_thread.started.connect(self._packing_worker.run)
        self._packing_worker.progress.connect(self._on_packing_progress)
        self._packing_worker.finished.connect(self._on_packing_finished)
        self._packing_worker.failed.connect(self._on_packing_failed)

        self._packing_worker.finished.connect(self._packing_thread.quit)
        self._packing_worker.failed.connect(self._packing_thread.quit)

        self._packing_thread.finished.connect(self._cleanup_packing_thread)

        self._packing_thread.start()

    @Slot()
    def cancel_generation(self) -> None:
        if self._packing_worker is not None:
            self._packing_worker.request_cancel()
            self.cancel_generation_button.setEnabled(False)
            self.report_box.append("\nCancelling...")

    @Slot(int, int, int)
    def _on_packing_progress(self, done: int, total: int, best_count: int) -> None:
        self.report_box.setPlainText(
            f"Generating layout...\n"
            f"Finished attempts: {done}/{total}\n"
            f"Best placed boards so far: {best_count}"
        )

    @Slot(object, object, object, str)
    def _on_packing_finished(
        self,
        placements,
        footprints_by_id,
        cut_paths,
        report: str,
    ) -> None:
        if self.current_project is None:
            return

        self.current_placements = placements
        self.report_box.setPlainText(report)

        self.canvas.draw_layout(
            self.current_project.panel,
            placements,
            footprints_by_id,
            cut_paths=cut_paths,
        )

        self.export_gcode_button.setEnabled(bool(placements))

    @Slot(str)
    def _on_packing_failed(self, message: str) -> None:
        self.report_box.append(f"\nGeneration stopped: {message}")

        if message != "Layout generation cancelled.":
            QMessageBox.critical(self, "Generation error", message)

    @Slot()
    def _cleanup_packing_thread(self) -> None:
        if self._packing_worker is not None:
            self._packing_worker.deleteLater()
            self._packing_worker = None

        if self._packing_thread is not None:
            self._packing_thread.deleteLater()
            self._packing_thread = None

        self.generate_button.setEnabled(self.current_project is not None)
        self.load_button.setEnabled(True)
        self.generate_json_button.setEnabled(True)
        self.cancel_generation_button.setEnabled(False)

    def export_contour_gcode(self) -> None:
        if self.current_project is None:
            QMessageBox.warning(self, "No project", "Load a project first.")
            return

        if not self.current_placements:
            QMessageBox.warning(self, "No layout", "Generate layout first.")
            return

        cut_z, ok = QInputDialog.getDouble(
            self,
            "Cut depth",
            "Cut Z height:",
            -1.6,
            -1000.0,
            1000.0,
            3,
        )

        if not ok:
            return

        safe_z, ok = QInputDialog.getDouble(
            self,
            "Safe height",
            "Safe Z height:",
            5.0,
            -1000.0,
            1000.0,
            3,
        )

        if not ok:
            return

        output_path_str, _ = QFileDialog.getSaveFileName(
            self,
            "Save contour G-code",
            "output/contour_cut.gcode",
            "G-code Files (*.gcode *.nc *.tap);;All Files (*)",
        )

        if not output_path_str:
            return

        try:
            footprints_by_id = {
                footprint.id: footprint
                for footprint in self.current_project.footprints
            }

            output_path = save_contour_gcode(
                output_path=output_path_str,
                placements=self.current_placements,
                footprints_by_id=footprints_by_id,
                cut_z=cut_z,
                safe_z=safe_z,
            )

        except Exception as exc:
            QMessageBox.critical(self, "G-code export error", str(exc))
            return

        QMessageBox.information(
            self,
            "G-code exported",
            f"G-code saved to:\n{output_path}",
        )