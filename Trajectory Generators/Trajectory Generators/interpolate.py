import os
import sys
import pandas as pd
import numpy as np
import random
from rdp import rdp
from PyQt6.QtWidgets import (
    QApplication, QFileDialog, QDialog, QVBoxLayout, QLabel,
    QSpinBox, QPushButton, QHBoxLayout, QLineEdit
)

# Arena constants
ARENA_CM = 60.0
AXIS_UNITS = 2.0
CM_PER_UNIT = ARENA_CM / AXIS_UNITS
NORM_MIN = -0.8
NORM_MAX = 0.8
NORM_RANGE = NORM_MAX - NORM_MIN


def select_input_file():
    app = QApplication.instance() or QApplication(sys.argv)
    initial_dir = os.path.join(os.getcwd(), "trajectories")
    file_path, _ = QFileDialog.getOpenFileName(
        None,
        "Select trajectory CSV to interpolate",
        initial_dir,
        "CSV Files (*.csv)"
    )
    if not file_path:
        print("No file selected; exiting.", file=sys.stderr)
        sys.exit(1)
    return file_path


class OptionsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Interpolation Options")

        layout = QVBoxLayout()

        # Filename box
        fname_layout = QHBoxLayout()
        fname_layout.addWidget(QLabel("Base filename:"))
        self.fname_edit = QLineEdit()
        self.fname_edit.setText("RP1")
        fname_layout.addWidget(self.fname_edit)
        layout.addLayout(fname_layout)

        # Min speed
        min_layout = QHBoxLayout()
        min_layout.addWidget(QLabel("Minimum Speed (cm/s):"))
        self.min_spin = QSpinBox()
        self.min_spin.setRange(1, 1000)
        self.min_spin.setValue(20)
        min_layout.addWidget(self.min_spin)
        layout.addLayout(min_layout)

        # Max speed
        max_layout = QHBoxLayout()
        max_layout.addWidget(QLabel("Maximum Speed (cm/s):"))
        self.max_spin = QSpinBox()
        self.max_spin.setRange(1, 1000)
        self.max_spin.setValue(25)
        max_layout.addWidget(self.max_spin)
        layout.addLayout(max_layout)

        # Buttons
        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("OK")
        cancel_btn = QPushButton("Cancel")
        ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        self.setLayout(layout)

    def get_values(self):
        return self.fname_edit.text(), self.min_spin.value(), self.max_spin.value()


def get_options():
    app = QApplication.instance() or QApplication(sys.argv)
    dialog = OptionsDialog()
    if dialog.exec() == QDialog.DialogCode.Accepted:
        return dialog.get_values()
    else:
        print("No options selected; exiting.", file=sys.stderr)
        sys.exit(1)


def process_segment(segment, speed_cm_s, sampling_rate_hz, epsilon=0.5):
    if len(segment) < 2:
        return [segment[0]] if segment else []

    points_xy = [(pt[0], pt[1]) for pt in segment]
    simplified = rdp(points_xy, epsilon=epsilon) if speed_cm_s > 10 else points_xy

    out = []
    step_size = speed_cm_s / sampling_rate_hz

    for start, end in zip(simplified, simplified[1:]):
        dx, dy = end[0] - start[0], end[1] - start[1]
        dist_units = np.hypot(dx, dy)
        dist_cm = dist_units * CM_PER_UNIT
        if dist_cm == 0:
            continue

        direction = np.array([dx, dy]) / dist_units

        num_steps = int(dist_cm // step_size)
        for step in range(num_steps):
            frac = (step * step_size) / dist_cm
            out.append([start[0] + frac * dx, start[1] + frac * dy])

    return out


def interpolate_with_random_speeds(points, sampling_rate_hz, chunk_size=8, speed_range=(20, 25)):
    new_pts = []
    for i in range(0, len(points), chunk_size):
        start_idx = max(i - 1, 0)
        chunk = points[start_idx: i + chunk_size]

        speed = random.randint(*speed_range)
        speed = max(speed_range[0], min(speed, speed_range[1]))

        seg = process_segment(chunk, speed, sampling_rate_hz)
        if new_pts:
            seg = seg[1:]
        new_pts.extend(seg)
    return new_pts


def build_interpolated_dataframe(df, speed_range):
    out_dfs = []
    for trial_id, g in df.groupby("Trial"):
        raw_min_x, raw_max_x = g["X"].min(), g["X"].max()
        raw_min_y, raw_max_y = g["Y"].min(), g["Y"].max()

        norm_pts = list(zip(g["Norm X"], g["Norm Y"]))
        hz = g["HZ"].iloc[0]

        interp_norm = interpolate_with_random_speeds(
            norm_pts, sampling_rate_hz=hz, speed_range=speed_range
        )

        max_samples = int(hz * 15)
        while len(interp_norm) < max_samples:
            interp_norm.extend(interp_norm[::-1])
        interp_norm = interp_norm[:max_samples]

        trial_df = pd.DataFrame({
            "Normalized X": [p[0] for p in interp_norm],
            "Normalized Y": [p[1] for p in interp_norm],
            "Trial": trial_id,
            "HZ": hz,
        })
        trial_df["Duration"] = len(trial_df) / hz

        trial_df["X"] = ((trial_df["Normalized X"] - NORM_MIN) / NORM_RANGE) * (raw_max_x - raw_min_x) + raw_min_x
        trial_df["Y"] = ((trial_df["Normalized Y"] - NORM_MIN) / NORM_RANGE) * (raw_max_y - raw_min_y) + raw_min_y

        trial_df = trial_df[[
            "X", "Y",
            "Normalized X", "Normalized Y",
            "Trial", "HZ", "Duration"
        ]]
        trial_df["Cue Type"] = 0
        trial_df["Trial Type"] = 0
        out_dfs.append(trial_df)

    return pd.concat(out_dfs, ignore_index=True)


def shuffle_trials(df):
    groups = [g.copy() for _, g in df.groupby("Trial")]
    random.shuffle(groups)
    shuffled = pd.concat(groups, ignore_index=True)

    # Reset trial numbers
    new_ids = []
    trial_counter = 1
    last_trial = None
    for t in shuffled["Trial"]:
        if t != last_trial:
            last_trial = t
            trial_counter += 1
        new_ids.append(trial_counter - 1)
    shuffled["Trial"] = new_ids
    return shuffled


def main():
    input_csv = select_input_file()
    base_name, speed_min, speed_max = get_options()

    folder, fname = os.path.split(input_csv)
    name, ext = os.path.splitext(fname)

    df = pd.read_csv(input_csv)
    df.columns = df.columns.str.strip()

    result = build_interpolated_dataframe(df, speed_range=(15, 25))
    result.to_csv(os.path.join(folder, f"Interpolated_{name}.csv"), index=False)
    print(f"Saved Interpolated_{name}.csv")

    out_folder = os.path.join(folder, f"{base_name}_speed{speed_min}-{speed_max}")
    os.makedirs(out_folder, exist_ok=True)

    base_df = build_interpolated_dataframe(df, speed_range=(speed_min, speed_max))
    for i in range(1, 6):
        if i == 1:
            out_df = base_df.copy()
        else:
            out_df = shuffle_trials(base_df)
        out_df.to_csv(os.path.join(out_folder, f"{base_name}-{i}.csv"), index=False)
        print(f"Saved {base_name}-{i}.csv in {out_folder}")


if __name__ == "__main__":
    main()
