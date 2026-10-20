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
from arena_widget import ArenaWidget
from trajectory_organizer import TrajectoryOrganizer

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Characterized Trajectory Editor')
        self.current_csv_path = None

        dark_theme = """
        QWidget {
            background-color: #2d2d30;
            color: #cccccc;
            font-family: Arial;
        }

        QPushButton {
            background-color: #505050;
            color: white;
            padding: 5px;
            border-radius: 5px;
        }

        QPushButton:hover {
            background-color: #606060;
        }

        QLineEdit {
            background-color: #404040;
            color: white;
            border-radius: 3px;
            padding: 2px;
        }

        QScrollBar:vertical {
            border: none;
            background: #404040;
            width: 12px;
            margin: 15px 0 15px 0;
            border-radius: 6px;
        }

        QScrollBar::handle:vertical {
            background-color: #606060;
            min-height: 30px;
            border-radius: 6px;
        }

        QScrollBar::handle:vertical:hover {
            background-color: #787878;
        }

        QScrollBar::sub-line:vertical, QScrollBar::add-line:vertical {
            height: 0;
            subcontrol-origin: margin;
        }

        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
            background: none;
        }
        """
        self.setStyleSheet(dark_theme)

        # Arena widget and defaults
        self.arena_widget = ArenaWidget()
        self.arena_widget.main_window = self
        self.arena_widget.speed_cm_s = 15
        self.arena_widget.sampling_rate_hz = 30
        self.arena_widget.arena_width_cm = 55
        self.arena_widget.arena_height_cm = 55

        # Controls
        self.speed_input = QLineEdit(str(self.arena_widget.speed_cm_s))
        self.sampling_rate_input = QLineEdit(str(self.arena_widget.sampling_rate_hz))
        self.arena_width_input = QLineEdit(str(self.arena_widget.arena_width_cm))
        self.arena_height_input = QLineEdit(str(self.arena_widget.arena_height_cm))

        update_btn = QPushButton("Update Parameters")
        update_btn.clicked.connect(self.update_parameters)

        self.export_btn = QPushButton('Export CSV')
        self.export_btn.clicked.connect(self.arena_widget.export_csv)

        clear_btn = QPushButton('Clear Plot')
        clear_btn.clicked.connect(self.clear_plot)

        exit_btn = QPushButton('Exit')
        exit_btn.clicked.connect(self.close)

        #self.interpolate_checkbox = QCheckBox("Interpolate Points on Export")
        #self.interpolate_checkbox.setChecked(False)

        # Left layout setup explicitly
        param_layout1 = QHBoxLayout()
        param_layout1.addWidget(QLabel("Speed (cm/s):"))
        param_layout1.addWidget(self.speed_input)
        param_layout1.addWidget(QLabel("Sampling Rate (Hz):"))
        param_layout1.addWidget(self.sampling_rate_input)

        param_layout2 = QHBoxLayout()
        param_layout2.addWidget(QLabel("Arena Width (cm):"))
        param_layout2.addWidget(self.arena_width_input)
        param_layout2.addWidget(QLabel("Arena Height (cm):"))
        param_layout2.addWidget(self.arena_height_input)

        left_layout = QVBoxLayout()
        left_layout.addLayout(param_layout1)
        left_layout.addLayout(param_layout2)
        left_layout.addWidget(update_btn)
        left_layout.addWidget(self.arena_widget)
        left_layout.addWidget(self.export_btn)

        # Folder name for batch exports
        self.version_input = QLineEdit("version1")
        self.version_input.setPlaceholderText("Export folder name")

        batch_export_btn = QPushButton("Batch Export Speeds (5–30 cm/s)")
        batch_export_btn.clicked.connect(self.batch_export_speeds)

        left_layout.addWidget(QLabel("Export Version Name:"))
        left_layout.addWidget(self.version_input)
        left_layout.addWidget(batch_export_btn)


        btn_layout = QHBoxLayout()
        btn_layout.addWidget(clear_btn)
        btn_layout.addWidget(exit_btn)
        left_layout.addLayout(btn_layout)
        #left_layout.addWidget(self.interpolate_checkbox)

        left_widget = QWidget()
        left_widget.setLayout(left_layout)

        # Trajectory viewer setup
        self.trajectory_list = QListWidget()
        self.trajectory_list.setFixedWidth(200)
        self.trajectory_list.setIconSize(QSize(180, 180))
        self.trajectory_list.itemClicked.connect(self.load_selected_trajectory)
        self.trajectory_list.setFrameShape(QListWidget.NoFrame)
        self.trajectory_list.setSelectionMode(QAbstractItemView.MultiSelection)
        self.trajectory_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.trajectory_list.customContextMenuRequested.connect(self.open_trajectory_menu)

        # Right splitter setup
        self.reps_input = QLineEdit("1")
        self.reps_input.setFixedWidth(50)

        export_combined_btn = QPushButton('Export Combined CSV')
        export_combined_btn.clicked.connect(self.export_combined_csv)

        right_layout = QVBoxLayout()
        right_layout.addWidget(QLabel("Repetitions per Trajectory:"))
        right_layout.addWidget(self.reps_input)
        right_layout.addWidget(export_combined_btn)
        right_layout.addStretch()

        right_widget = QWidget()
        right_widget.setLayout(right_layout)

        right_splitter = QSplitter(Qt.Vertical)
        right_splitter.addWidget(self.trajectory_list)
        right_splitter.addWidget(right_widget)
        right_splitter.setSizes([600, 100])

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left_widget)
        splitter.addWidget(right_splitter)
        splitter.setSizes([800, 200])

        flip_x_btn = QPushButton("Flip X Axis")
        flip_x_btn.clicked.connect(self.arena_widget.flip_x_axis)

        flip_y_btn = QPushButton("Flip Y Axis")
        flip_y_btn.clicked.connect(self.arena_widget.flip_y_axis)

        # Add to layout, e.g., same `btn_layout` or new one:
        btn_layout.addWidget(flip_x_btn)
        btn_layout.addWidget(flip_y_btn)

        # In your UI initialization/setup:
        self.organizer_btn = QPushButton("Open Trajectory Organizer")
        self.organizer_btn.clicked.connect(self.open_trajectory_organizer)
        btn_layout.addWidget(self.organizer_btn)  # Adjust to your actual layout

        main_layout = QHBoxLayout()
        main_layout.addWidget(splitter)
        self.setLayout(main_layout)

        self.load_trajectory_list()

    def update_parameters(self):
        try:
            speed  = float(self.speed_input.text())
            rate   = float(self.sampling_rate_input.text())
            new_w  = float(self.arena_width_input.text())
            new_h  = float(self.arena_height_input.text())
        except ValueError:
            print("Please enter valid numbers for speed, rate, width, and height.")
            return

        aw = self.arena_widget
        # 1) grab old dims
        old_w = aw.arena_width_cm
        old_h = aw.arena_height_cm

        # 2) remap every point
        remapped = []
        for pt in aw.points:
            x_old, y_old = pt[0], pt[1]
            # preserve teleport flag if present
            flag = pt[2] if len(pt) >= 3 else False

            # relative positions 0…1
            rel_x = (x_old + old_w/2)  / old_w
            rel_y = (y_old + old_h/2)  / old_h

            # new coords
            x_new = rel_x * new_w  - new_w/2
            y_new = rel_y * new_h  - new_h/2

            remapped.append((x_new, y_new, flag))

        # 3) apply new params and points
        aw.speed_cm_s       = speed
        aw.sampling_rate_hz = rate
        aw.arena_width_cm   = new_w
        aw.arena_height_cm  = new_h
        aw.points           = remapped

        aw.update()
        print(f"Parameters updated: speed={speed}, rate={rate}, size={new_w}×{new_h} cm")

    def create_trajectory_item(self, png_path, csv_path, base_name):
        widget = QWidget()
        layout = QVBoxLayout()

        # Image Preview explicitly
        pixmap = QPixmap(png_path).scaled(160, 160, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        image_label = QLabel()
        image_label.setPixmap(pixmap)
        image_label.setAlignment(Qt.AlignCenter)

        # Filename Label explicitly
        name_label = QLabel(base_name)
        name_label.setAlignment(Qt.AlignCenter)
        name_label.setStyleSheet("color: #cccccc; font-size: 12px;")

        layout.addWidget(image_label)
        layout.addWidget(name_label)
        widget.setLayout(layout)
        widget.setFixedSize(180, 200)  # explicitly set overall size (extra spacing)

        item = QListWidgetItem()
        item.setSizeHint(widget.sizeHint())
        item.setData(Qt.UserRole, csv_path)

        return item, widget


    def load_trajectory_list(self):
        self.trajectory_list.clear()
        trajectory_folder = 'trajectories'
        if not os.path.exists(trajectory_folder):
            return

        files = [f for f in os.listdir(trajectory_folder) if f.endswith('.csv')]
        for file in sorted(files, reverse=True):
            base_name = file.replace('.csv', '')
            png_path = os.path.join(trajectory_folder, f'{base_name}.png')
            csv_path = os.path.join(trajectory_folder, file)

            if os.path.exists(png_path):
                item, widget = self.create_trajectory_item(png_path, csv_path, base_name)
                self.trajectory_list.addItem(item)
                self.trajectory_list.setItemWidget(item, widget)


    def load_selected_trajectory(self, item):
        csv_path = item.data(Qt.UserRole)
        df = pd.read_csv(csv_path)

        # 1) Restore points with teleport flags
        pts = []
        for _, row in df.iterrows():
            x, y = row['X_cm'], row['Y_cm']
            tp = bool(row['Teleport']) if 'Teleport' in df.columns else False
            pts.append((x, y, tp))
        self.arena_widget.points = pts

        # 2) Restore arena dimensions if present
        if 'ArenaWidth_cm' in df.columns and 'ArenaHeight_cm' in df.columns:
            w = float(df.at[0, 'ArenaWidth_cm'])
            h = float(df.at[0, 'ArenaHeight_cm'])
            # apply to the widget
            self.arena_widget.arena_width_cm  = w
            self.arena_widget.arena_height_cm = h
            # update your QLineEdit fields
            self.arena_width_input.setText(str(w))
            self.arena_height_input.setText(str(h))
            print(f"Restored arena size to {w}×{h} cm")

        # 3) Refresh display and UI state
        self.arena_widget.update()
        self.current_csv_path = csv_path
        self.export_btn.setText("Save")
        print(f"Loaded trajectory: {csv_path}")

    def open_trajectory_organizer(self):
        self.organizer_window = TrajectoryOrganizer()
        self.organizer_window.show()

    def clear_plot(self):
        self.arena_widget.points = []
        self.arena_widget.loop_closed = False
        self.arena_widget.update()
        self.current_csv_path = None

        self.export_btn.setText("Export CSV")  # explicitly reset the button
        print("Plot cleared.")

    def export_combined_csv(self):
        selected_items = self.trajectory_list.selectedItems()
        if not selected_items:
            print("No trajectories selected!")
            return

        try:
            repetitions = int(self.reps_input.text())
            if repetitions < 1:
                raise ValueError
        except ValueError:
            print("Invalid number of repetitions entered!")
            return

        combined_data = []
        trial_number = 1

        # Get the parameters from the GUI.
        speed = float(self.speed_input.text())
        rate = float(self.sampling_rate_input.text())

        for item in selected_items:
            csv_path = item.data(Qt.UserRole)
            df = pd.read_csv(csv_path)

            # Extract main points from the CSV.
            main_points = df[['X_cm', 'Y_cm']].values.tolist()
            # main_points here are 2-element lists (since the export only saved X_cm and Y_cm).

            # Set the parameters for interpolation.
            self.arena_widget.speed_cm_s = speed
            self.arena_widget.sampling_rate_hz = rate
            # Use deep copy so we don’t alter the original data.
            self.arena_widget.points = [pt[:] for pt in main_points]

            # Note: if self.arena_widget.loop_closed is relevant here, ensure it is set accordingly.
            interpolated_points = self.arena_widget.interpolate_points()  
            # (Again, this will be a list of 2-element lists.)

            df_interpolated = pd.DataFrame(interpolated_points, columns=['X_cm', 'Y_cm'])

            for _ in range(repetitions):
                df_copy = df_interpolated.copy()
                df_copy['Trial'] = trial_number
                combined_data.append(df_copy)
                trial_number += 1

        final_df = pd.concat(combined_data, ignore_index=True)

        save_path = os.path.join('trajectories', 'combined_trials.csv')
        final_df.to_csv(save_path, index=False)
        print(f"Combined CSV exported at new speed ({speed} cm/s) to {save_path}")

    def open_trajectory_menu(self, position):
        item = self.trajectory_list.itemAt(position)
        if item is not None:
            menu = QMenu()

            delete_action = QAction("Delete Trajectory", self)
            archive_action = QAction("Archive Trajectory", self)

            delete_action.triggered.connect(lambda: self.delete_trajectory(item))
            archive_action.triggered.connect(lambda: self.archive_trajectory(item))

            menu.addAction(delete_action)
            menu.addAction(archive_action)

            menu.exec_(self.trajectory_list.viewport().mapToGlobal(position))

    def delete_trajectory(self, item):
        csv_path = item.data(Qt.UserRole)
        png_path = csv_path.replace('.csv', '.png')

        # Explicitly remove files
        os.remove(csv_path)
        if os.path.exists(png_path):
            os.remove(png_path)

        print(f"Deleted trajectory: {csv_path}")
        self.load_trajectory_list()

    def archive_trajectory(self, item):
        csv_path = item.data(Qt.UserRole)
        png_path = csv_path.replace('.csv', '.png')

        # Explicitly create archive folder if it doesn't exist
        archive_folder = os.path.join('trajectories', 'archive')
        os.makedirs(archive_folder, exist_ok=True)

        # Explicitly move files to archive
        shutil.move(csv_path, archive_folder)
        if os.path.exists(png_path):
            shutil.move(png_path, archive_folder)

        print(f"Archived trajectory: {csv_path}")
        self.load_trajectory_list()

    def batch_export_speeds(self):
        if len(self.arena_widget.points) < 2:
            print("Add at least two points first.")
            return

        base_name = self.version_input.text().strip()
        if not base_name:
            print("Please enter a valid folder name.")
            return

        try:
            repetitions = int(self.reps_input.text())
            if repetitions < 1:
                raise ValueError
        except ValueError:
            print("Invalid number of repetitions entered!")
            return

        output_dir = os.path.join("trajectories", base_name.lower().replace(" ", "_"))
        os.makedirs(output_dir, exist_ok=True)

        speeds = [5, 6, 8, 10, 12, 14, 15, 20, 25, 30]
        # Use a deep copy for original points to avoid mutating the original list.
        original_speed = self.arena_widget.speed_cm_s
        original_points = [pt[:] for pt in self.arena_widget.points]
        original_loop = self.arena_widget.loop_closed

        for speed in speeds:
            self.arena_widget.speed_cm_s = speed
            interpolated = self.arena_widget.interpolate_points()  
            # (interpolated returns a list of [X, Y] pairs.)

            # Create a DataFrame with the interpolated trajectory.
            df = pd.DataFrame(interpolated, columns=["X_cm", "Y_cm"])
            df['X_norm'] = df['X_cm'] / 30
            df['Y_norm'] = df['Y_cm'] / 30

            combined = []
            for trial_number in range(1, repetitions + 1):
                df_copy = df.copy()
                df_copy["Trial"] = trial_number
                combined.append(df_copy)

            result_df = pd.concat(combined, ignore_index=True)

            filename = f"{base_name.lower().replace(' ', '_')}_speed{speed}.csv"
            filepath = os.path.join(output_dir, filename)
            result_df.to_csv(filepath, index=False)
            print(f"Exported: {filepath}")

        # Restore original values.
        self.arena_widget.speed_cm_s = original_speed
        self.arena_widget.points = original_points
        self.arena_widget.loop_closed = original_loop
        print("Batch export complete.")

