from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QFont, QPen, QPolygonF
from PySide6.QtWidgets import (
    QGraphicsLineItem,
    QGraphicsPolygonItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
)

from app.core.geometry import transformed_placement_polygon
from app.models.cut_line import CutPath
from app.models.footprint import Footprint
from app.models.panel import Panel
from app.models.placement import Placement


class LayoutCanvas(QGraphicsView):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)

        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)

    def clear_layout(self) -> None:
        self._scene.clear()

    def draw_layout(
        self,
        panel: Panel,
        placements: list[Placement],
        footprints_by_id: dict[str, Footprint],
        cut_paths: list[CutPath] | None = None,
    ) -> None:
        self._scene.clear()

        if cut_paths is None:
            cut_paths = []

        panel_pen = QPen(Qt.black)
        panel_pen.setWidth(2)

        item_pen = QPen(Qt.darkBlue)
        item_pen.setWidth(1)

        item_brush = QBrush(Qt.lightGray)

        cut_pen = QPen(Qt.red)
        cut_pen.setWidth(2)
        cut_pen.setStyle(Qt.DashLine)

        panel_rect = QGraphicsRectItem(QRectF(0, 0, panel.width, panel.height))
        panel_rect.setPen(panel_pen)
        self._scene.addItem(panel_rect)

        for placement in placements:
            footprint = footprints_by_id[placement.footprint_id]
            poly = transformed_placement_polygon(footprint, placement)

            coords = [QPointF(x, y) for x, y in poly.exterior.coords[:-1]]
            polygon_item = QGraphicsPolygonItem(QPolygonF(coords))
            polygon_item.setPen(item_pen)
            polygon_item.setBrush(item_brush)
            self._scene.addItem(polygon_item)

            label = placement.footprint_id

            base_size = min(placement.width, placement.height) * 0.2
            font_size = max(6, min(40, base_size))

            font = QFont()
            font.setPointSizeF(font_size)
            if placement.rotated:
                font.setItalic(True)

            text_item = self._scene.addText(label, font)
            text_rect = text_item.boundingRect()

            text_item.setPos(
                placement.x + placement.width / 2 - text_rect.width() / 2,
                placement.y + placement.height / 2 - text_rect.height() / 2,
            )

        for cut_path in cut_paths:
            for segment in cut_path.segments:
                line_item = QGraphicsLineItem(
                    segment.start_x,
                    segment.start_y,
                    segment.end_x,
                    segment.end_y,
                )
                line_item.setPen(cut_pen)
                line_item.setZValue(10)
                self._scene.addItem(line_item)

        self.setSceneRect(self._scene.itemsBoundingRect().adjusted(-20, -20, 20, 20))
        self.fitInView(self.sceneRect(), Qt.KeepAspectRatio)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if not self._scene.items():
            return
        self.fitInView(self.sceneRect(), Qt.KeepAspectRatio)