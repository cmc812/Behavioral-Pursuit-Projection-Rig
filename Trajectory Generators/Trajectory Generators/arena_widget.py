import sys
import os
import shutil
from datetime import datetime
import numpy as np
import pandas as pd
from PyQt5.QtWidgets import (
    QApplication, QWidget, QPushButton, QVBoxLayout, QLabel, QLineEdit, QHBoxLayout, 
    QCheckBox, QListWidget, QListWidgetItem, QSplitter, QAbstractItemView, QMenu, QAction,
    QShortcut
)
from PyQt5.QtGui import QPainter, QPen, QPixmap, QIcon, QKeySequence
from PyQt5.QtCore import Qt, QPointF, QSize
from utils import rdp

class ArenaWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedSize(400, 400)
        self.points = []
        self.selected_point_index = None
        self.arena_width_cm = 55
        self.arena_height_cm = 55
        self.speed_cm_s = 15
        self.sampling_rate_hz = 30
        self.loop_closed = False
        self.teleport_mode = False
        self.setFocusPolicy(Qt.StrongFocus)

        undo_shortcut = QShortcut(QKeySequence.Undo, self)
        undo_shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        undo_shortcut.activated.connect(self.undo_via_right_click)

        self.teleport_indicator = QLabel("Teleport Mode: OFF", self)
        self.teleport_indicator.setGeometry(10, 10, 120, 25)
        self.teleport_indicator.setStyleSheet("""
            background-color: rgba(50, 50, 50, 180);
            color: white;
            font-size: 12px;
            border-radius: 8px;
            padding: 2px;
        """)

        # Set up shortcut for toggling teleport mode.
        toggle_teleport_shortcut = QShortcut(QKeySequence("T"), self)
        toggle_teleport_shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        toggle_teleport_shortcut.activated.connect(self.toggle_teleport_mode)

    def mousePressEvent(self, event):
        x, y = event.x(), event.y()
        cm_x = ((x / self.width()) * self.arena_width_cm) - (self.arena_width_cm / 2)
        cm_y = (((self.height() - y) / self.height()) * self.arena_height_cm) - (self.arena_height_cm / 2)

        idx = self.get_nearest_point_index(cm_x, cm_y)

        if event.button() == Qt.LeftButton:
            if idx is not None and self.distance_to_point(cm_x, cm_y, self.points[idx][:2]) < 2:
                if idx == 0 and len(self.points) >= 3:
                    self.loop_closed = True
                    print("Loop explicitly closed.")
                else:
                    self.selected_point_index = idx
            else:
                if not self.loop_closed:
                    # new points already include the flag
                    self.points.append((cm_x, cm_y, self.teleport_mode))
        elif event.button() == Qt.RightButton:
            if idx is not None:
                self.points.pop(idx)
                self.loop_closed = False

        self.update()

    def mouseMoveEvent(self, event):
        if self.selected_point_index is not None:
            x, y = event.x(), event.y()
            cm_x = ((x / self.width()) * self.arena_width_cm) - (self.arena_width_cm / 2)
            cm_y = (((self.height() - y) / self.height()) * self.arena_height_cm) - (self.arena_height_cm / 2)

            # grab the old point (which may be (x, y) or (x, y, flag))
            old = self.points[self.selected_point_index]
            # preserve the teleport flag if it exists
            is_tp = old[2] if len(old) >= 3 else False

            # reassign with the flag still intact
            self.points[self.selected_point_index] = (cm_x, cm_y, is_tp)
            self.update()

    def mouseReleaseEvent(self, event):
        self.selected_point_index = None

    def distance_to_point(self, x, y, point):
        return ((x - point[0]) ** 2 + (y - point[1]) ** 2) ** 0.5

    def get_nearest_point_index(self, x, y):
        min_dist = float('inf')
        min_idx = None
        for idx, point in enumerate(self.points):
            dist = self.distance_to_point(x, y, point)
            if dist < min_dist and dist < 2:
                min_dist = dist
                min_idx = idx
        return min_idx

    def paintEvent(self, event):
        painter = QPainter(self)

        background_color = Qt.white
        grid_color = Qt.lightGray
        boundary_color = Qt.black
        line_color = Qt.gray
        point_color = Qt.blue

        painter.fillRect(self.rect(), background_color)

        painter.setPen(QPen(grid_color, 1, Qt.DotLine))
        num_lines = 12
        step_x = self.width() / num_lines
        step_y = self.height() / num_lines
        for i in range(num_lines + 1):
            painter.drawLine(int(i * step_x), 0, int(i * step_x), self.height())
            painter.drawLine(0, int(i * step_y), self.width(), int(i * step_y))

        painter.setPen(QPen(boundary_color, 3))
        painter.drawRect(0, 0, self.width() - 1, self.height() - 1)

        # Draw trajectory lines
        painter.setPen(QPen(line_color, 2, Qt.DashLine))
        num_points = len(self.points)
        for i in range(num_points - 1):
            current_point, next_point = self.points[i], self.points[i + 1]

            next_teleport = next_point[2] if len(next_point) > 2 else False
            if next_teleport:
                continue

            x1 = int((current_point[0] + self.arena_width_cm / 2) / self.arena_width_cm * self.width())
            y1 = int(self.height() - ((current_point[1] + self.arena_height_cm / 2) / self.arena_height_cm * self.height()))
            x2 = int((next_point[0] + self.arena_width_cm / 2) / self.arena_width_cm * self.width())
            y2 = int(self.height() - ((next_point[1] + self.arena_height_cm / 2) / self.arena_height_cm * self.height()))
            painter.drawLine(x1, y1, x2, y2)

        # Handle loop closure explicitly outside the loop
        if self.loop_closed and num_points > 1:
            first_point, last_point = self.points[0], self.points[-1]
            last_teleport = last_point[2] if len(last_point) > 2 else False
            first_teleport = first_point[2] if len(first_point) > 2 else False

            # Close loop only if neither end is teleport
            if not last_teleport and not first_teleport:
                first_x = int(((first_point[0] + self.arena_width_cm / 2) / self.arena_width_cm) * self.width())
                first_y = int(self.height() - ((first_point[1] + self.arena_height_cm / 2) / self.arena_height_cm) * self.height())
                last_x = int(((last_point[0] + self.arena_width_cm / 2) / self.arena_width_cm) * self.width())
                last_y = int(self.height() - ((last_point[1] + self.arena_height_cm / 2) / self.arena_height_cm) * self.height())
                painter.drawLine(last_x, last_y, first_x, first_y)

        # Draw points explicitly
        painter.setPen(QPen(point_color, 8))
        for point in self.points:
            x = int((point[0] + self.arena_width_cm / 2) / self.arena_width_cm * self.width())
            y = int(self.height() - ((point[1] + self.arena_height_cm / 2) / self.arena_height_cm * self.height()))
            is_teleport = point[2] if len(point) > 2 else False
            painter.setBrush(Qt.red if is_teleport else Qt.blue)
            painter.drawEllipse(QPointF(x, y), 5, 5)

    def interpolate_points(self):
        dist_per_sample = self.speed_cm_s / self.sampling_rate_hz

        def is_teleport(pt):
            # If the point has three (or more) elements and the third is truthy, return True;
            # Otherwise, assume it's not a teleport.
            return len(pt) >= 3 and pt[2]

        def process_segment(segment):
            """Interpolate a continuous segment of non-teleport points.
            Optionally simplifies via RDP if speed is high.
            """
            if len(segment) < 2:
                # If there is only one point, return that point.
                return [[segment[0][0], segment[0][1]]] if segment else []
            if self.speed_cm_s > 10:
                points_xy = [(pt[0], pt[1]) for pt in segment]
                simplified = rdp(points_xy, epsilon=0.5)
            else:
                simplified = [(pt[0], pt[1]) for pt in segment]
            seg_interp = []
            for i in range(len(simplified) - 1):
                start = simplified[i]
                end = simplified[i + 1]
                dx, dy = end[0] - start[0], end[1] - start[1]
                dist = np.hypot(dx, dy)
                num_samples = int(np.ceil(dist / dist_per_sample))
                for step in range(num_samples):
                    fraction = step / num_samples
                    x = start[0] + fraction * dx
                    y = start[1] + fraction * dy
                    seg_interp.append([x, y])
            seg_interp.append([simplified[-1][0], simplified[-1][1]])
            return seg_interp

        interpolated = []
        segment = []

        # Iterate over points and break segments at teleport points.
        for pt in self.points:
            if is_teleport(pt):  # This point is marked as teleport.
                if segment:
                    if len(segment) >= 2:
                        seg_interp = process_segment(segment)
                        # Replace the final point of the processed segment with the teleport coordinates.
                        if seg_interp:
                            seg_interp[-1] = [pt[0], pt[1]]
                        interpolated.extend(seg_interp)
                    else:
                        # If segment has only one point, output that point as is and then the teleport.
                        interpolated.append([segment[0][0], segment[0][1]])
                        interpolated.append([pt[0], pt[1]])
                else:
                    # No preceding segment: add the teleport point directly.
                    interpolated.append([pt[0], pt[1]])
                # Start a new segment with the teleport point as the first element.
                segment = [pt]
            else:
                segment.append(pt)

        # Process any remaining segment.
        if segment:
            # If the remaining segment has exactly one point and that point is a teleport,
            # we know it was already added, so we do nothing.
            if len(segment) == 1:
                if not is_teleport(segment[0]):
                    interpolated.append([segment[0][0], segment[0][1]])
            else:
                interpolated.extend(process_segment(segment))

        # Loop closure: always append the first point at the end if loop_closed.
        if self.loop_closed and len(self.points) > 1:
            first_pt = self.points[0]
            last_pt = self.points[-1]
            # If last point is non-teleport, perform interpolation from last to first.
            if not is_teleport(last_pt):
                dx, dy = first_pt[0] - last_pt[0], first_pt[1] - last_pt[1]
                dist = np.hypot(dx, dy)
                num_samples = int(np.ceil(dist / dist_per_sample))
                for step in range(num_samples):
                    fraction = step / num_samples
                    x = last_pt[0] + fraction * dx
                    y = last_pt[1] + fraction * dy
                    interpolated.append([x, y])
            # In any case, ensure the loop is truly closed by appending the first point.
            interpolated.append([first_pt[0], first_pt[1]])

        return interpolated

    def export_csv(self):
        if len(self.points) < 2:
            print("Add at least two points first.")
            return

        os.makedirs('trajectories', exist_ok=True)
        main_window = self.main_window

        if main_window.current_csv_path:
            csv_path = main_window.current_csv_path
            png_path = csv_path.replace('.csv', '.png')
            print(f"Saving changes to existing trajectory: {csv_path}")
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            csv_path = os.path.join('trajectories', f'trajectory_{timestamp}.csv')
            png_path = os.path.join('trajectories', f'trajectory_{timestamp}.png')
            print(f"Saving new trajectory: {csv_path}")

        # Build a list of (X, Y, Teleport) from self.points
        export_points = []
        for pt in self.points:
            x, y = pt[0], pt[1]
            tp = pt[2] if len(pt) >= 3 else False
            export_points.append((x, y, tp))

        df = pd.DataFrame(export_points, columns=['X_cm', 'Y_cm', 'Teleport'])
        df['ArenaWidth_cm']  = self.arena_width_cm
        df['ArenaHeight_cm'] = self.arena_height_cm
        df.to_csv(csv_path, index=False)

        self.save_preview_image(png_path)
        main_window.load_trajectory_list()

    def save_preview_image(self, filename):
        pixmap = QPixmap(self.size())
        self.render(pixmap)
        pixmap.save(filename)

    # def undo_last_point(self):
    #     if self.points:
    #         removed_point = self.points.pop()
    #         print(f"Removed last point: {removed_point}")
    #         self.loop_closed = False  # Explicitly reset loop if any point changes
    #         self.update()

    def undo_via_right_click(self):
        if not self.points:
            print("No points to remove.")
            return
        
        # Explicitly simulate right-click logic on the last point
        removed_point = self.points.pop(-1)
        self.loop_closed = False  # Reset the loop explicitly
        print(f"Removed last point via shortcut: {removed_point}")
        self.update()

    def toggle_teleport_mode(self):
        self.teleport_mode = not self.teleport_mode
        state_text = "ON" if self.teleport_mode else "OFF"
        self.teleport_indicator.setText(f"Teleport Mode: {state_text}")
        print("Teleport mode:", state_text)
        self.update()

    def flip_x_axis(self):
        new_points = []
        for pt in self.points:
            # If the point has a teleport flag (3 elements), preserve it.
            if isinstance(pt, (list, tuple)) and len(pt) >= 3:
                new_points.append((pt[0], -pt[1], pt[2]))
            else:
                new_points.append((pt[0], -pt[1]))
        self.points = new_points
        print("Flipped over X axis.")
        self.update()

    def flip_y_axis(self):
        new_points = []
        for pt in self.points:
            if isinstance(pt, (list, tuple)) and len(pt) >= 3:
                new_points.append((-pt[0], pt[1], pt[2]))
            else:
                new_points.append((-pt[0], pt[1]))
        self.points = new_points
        print("Flipped over Y axis.")
        self.update()
