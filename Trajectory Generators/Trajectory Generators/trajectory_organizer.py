import sys
import os
import random
import pandas as pd

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QListWidget, QListWidgetItem,
    QVBoxLayout, QWidget, QHBoxLayout, QPushButton, QMenu, QAction,
    QMessageBox, QInputDialog, QLabel, QComboBox, QSplitter, QCheckBox, QSpinBox
)
from PyQt5.QtCore import Qt

import pyqtgraph as pg

from PyQt5.QtGui import QColor, QBrush

import re

class Trial:
    def __init__(self, trial_num, random_data):
        self.original_trial_num = trial_num
        self.random_data = random_data.copy()
        self.is_characterized = False
        self.characterized_source = None

    def get_data(self, characterized_dfs):
        if self.is_characterized and self.characterized_source in characterized_dfs:
            return characterized_dfs[self.characterized_source]
        else:
            return self.random_data

class TrajectoryOrganizer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Trajectory Organizer")
        self.trials = []
        self.random_trials_loaded = False
        self.characterized_dfs = {}
        self.init_UI()

    def init_UI(self):
        splitter = QSplitter(Qt.Horizontal)
        self.setCentralWidget(splitter)

        # Left pane
        left_widget = QWidget()
        left_layout = QVBoxLayout()
        left_widget.setLayout(left_layout)
        splitter.addWidget(left_widget)

        left_layout.addWidget(QLabel("Trials:"))
        self.trial_list = QListWidget()
        self.trial_list.itemClicked.connect(self.load_selected_trajectory)
        self.trial_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.trial_list.customContextMenuRequested.connect(self.open_context_menu)
        left_layout.addWidget(self.trial_list)

        btn_randomize = QPushButton("Randomize RP Trials")
        btn_randomize.clicked.connect(self.randomize_trials)
        left_layout.addWidget(btn_randomize)

        btn_random_replace = QPushButton("Randomly Replace Trials")
        btn_random_replace.clicked.connect(self.random_replace_trials)
        left_layout.addWidget(btn_random_replace)

        btn_custom_replace = QPushButton("Custom Replace Pattern")
        btn_custom_replace.clicked.connect(self.custom_replace_pattern)
        left_layout.addWidget(btn_custom_replace)

        btn_custom_cue = QPushButton("Custom Cue Pattern")
        btn_custom_cue.clicked.connect(self.custom_cue_pattern)
        left_layout.addWidget(btn_custom_cue)

        self.mixed_cue_checkbox = QCheckBox("Mixed Cue")
        left_layout.addWidget(self.mixed_cue_checkbox)

        self.even_dist_checkbox = QCheckBox("Even Distribution")
        # Tooltip to explain behavior
        self.even_dist_checkbox.setToolTip(
            "When Mixed Cue is on, make all (TrialType,CueType) combos\n"
            "as even as possible across the session."
        )
        left_layout.addWidget(self.even_dist_checkbox)

        self.replace_checkbox = QCheckBox("Replace")
        left_layout.addWidget(self.replace_checkbox)

        right_widget = QWidget()
        right_layout = QVBoxLayout()
        right_widget.setLayout(right_layout)
        splitter.addWidget(right_widget)

        right_layout.addWidget(QLabel("Active Characterized File:"))
        self.char_combo = QComboBox()
        self.char_combo.addItem("No characterized loaded")
        self.char_combo.currentIndexChanged.connect(self.on_char_combo_changed)
        right_layout.addWidget(self.char_combo)

        self.update_all_char_button = QPushButton("Update Active Characterized")
        self.update_all_char_button.clicked.connect(self.update_all_characterized_trials)
        right_layout.addWidget(self.update_all_char_button)

        self.plot_widget = pg.PlotWidget(title="Trajectory Preview")
        self.plot_widget.setLabel('bottom', 'Normalized X')
        self.plot_widget.setLabel('left', 'Normalized Y')
        right_layout.addWidget(self.plot_widget)

        menu = self.menuBar()
        file_menu = menu.addMenu("File")

        action_import_random = QAction("Import Random CSV", self)
        action_import_random.triggered.connect(self.import_random_csv)
        file_menu.addAction(action_import_random)

        action_import_char = QAction("Import Characterized CSV", self)
        action_import_char.triggered.connect(self.import_characterized_csv)
        file_menu.addAction(action_import_char)

        action_import_char_folder = QAction("Import Characterized Folder", self)
        action_import_char_folder.triggered.connect(self.import_characterized_folder)
        file_menu.addAction(action_import_char_folder)

        action_import_mixed = QAction("Import Mixed CSV", self)
        action_import_mixed.triggered.connect(self.import_mixed_csv)
        file_menu.addAction(action_import_mixed)

        action_export = QAction("Export CSV", self)
        action_export.triggered.connect(self.export_csv)
        file_menu.addAction(action_export)

        self.random_csv_path = None
        self.characterized_folder_path = None
        self.characterized_csv_paths = {}

    def import_random_csv(self):
        fileName, _ = QFileDialog.getOpenFileName(self, "Open Random CSV", "", "CSV Files (*.csv)")
        if fileName:
            try:
                df = pd.read_csv(fileName, header=0, usecols=range(5))
                self.trials = []
                unique_trials = df.iloc[:, 4].unique()
                for trial_id in unique_trials:
                    trial_df = df[df.iloc[:, 4] == trial_id]
                    t = Trial(trial_id, trial_df.copy())
                    self.trials.append(t)
                self.random_trials_loaded = True
                self.load_trajectory_list()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to import CSV: {e}")

    def import_characterized_csv(self):
        fileName, _ = QFileDialog.getOpenFileName(self, "Open Characterized CSV", "", "CSV Files (*.csv)")
        if fileName:
            try:
                df = pd.read_csv(fileName, header=0)
                trial_val = df.iloc[0, 4]
                char_df = df[df.iloc[:, 4] == trial_val].copy()
                label = os.path.basename(fileName)
                self.characterized_dfs[label] = char_df
                if self.char_combo.count() == 1 and self.char_combo.itemText(0) == "No characterized loaded":
                    self.char_combo.clear()
                self.char_combo.addItem(label)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to import CSV: {e}")

    def import_characterized_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder of Characterized CSVs")
        if folder:
            for filename in os.listdir(folder):
                if filename.lower().endswith(".csv"):
                    path = os.path.join(folder, filename)
                    try:
                        df = pd.read_csv(path, header=0, usecols=range(5))
                        trial_val = df.iloc[0, 4]
                        char_df = df[df.iloc[:, 4] == trial_val].copy()
                        label = os.path.basename(path)
                        self.characterized_dfs[label] = char_df
                        if self.char_combo.count() == 1 and self.char_combo.itemText(0) == "No characterized loaded":
                            self.char_combo.clear()
                        self.char_combo.addItem(label)
                    except Exception as e:
                        QMessageBox.warning(self, "Error", f"Failed to load {filename}: {e}")

    def import_mixed_csv(self):
        fileName, _ = QFileDialog.getOpenFileName(self, "Open Mixed CSV", "", "CSV Files (*.csv)")
        if fileName:
            try:
                df = pd.read_csv(fileName, header=0, usecols=range(8))
                self.trials = []
                for trial_id in df.iloc[:, 4].unique():
                    trial_df = df[df.iloc[:, 4] == trial_id].copy()
                    t = Trial(trial_id, trial_df)
                    t.mixed_type = int(trial_df.iloc[0, 7])
                    self.trials.append(t)
                self.random_trials_loaded = True
                self.load_trajectory_list()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to import Mixed CSV: {e}")

    def load_trajectory_list(self):
        self.trial_list.clear()
        for idx, trial in enumerate(self.trials):
            orig_id = getattr(trial, "trial_id", getattr(trial, "id", idx+1))

            if hasattr(trial, 'mixed_type'):
                label = "Mixed CP" if trial.mixed_type == 1 else "Mixed RP"
                text = f"{orig_id} ({label})"
            else:
                if trial.is_characterized:
                    text = f"{orig_id} (Characterized: {trial.characterized_source})"
                else:
                    text = f"{orig_id} (Random)"

            item = QListWidgetItem(text)

            is_cued = getattr(trial, "cue_pattern", None)
            if is_cued is None and getattr(self, "mixed_cue_checkbox", None):
                is_cued = self.mixed_cue_checkbox.isChecked() and trial.is_characterized
            if is_cued:
                item.setForeground(QBrush(QColor("cyan")))

            self.trial_list.addItem(item)

        if hasattr(self, "cue_count_spin"):
            self.cue_count_spin.setMaximum(len(self.trials))

    def load_selected_trajectory(self, item):
        idx = self.trial_list.row(item)
        self.plot_trial(self.trials[idx])

    def plot_trial(self, trial):
        self.plot_widget.clear()
        df = trial.get_data(self.characterized_dfs)
        x = df.iloc[:,2].values
        y = df.iloc[:,3].values
        self.plot_widget.plot(x, y, pen=None, symbol='o')

    def open_context_menu(self, position):
        item = self.trial_list.itemAt(position)
        if item:
            menu = QMenu()
            idx = self.trial_list.row(item)
            trial = self.trials[idx]
            if trial.is_characterized:
                act = QAction("Revert to Random", self)
                act.triggered.connect(lambda: self.revert_to_randomized(idx))
                menu.addAction(act)
            else:
                if self.char_combo.count() > 0:
                    act = QAction("Replace with Characterized", self)
                    act.triggered.connect(lambda: self.change_to_characterized(idx))
                    menu.addAction(act)
            delAct = QAction("Delete Trial", self)
            delAct.triggered.connect(lambda: self.delete_trajectory(idx))
            menu.addAction(delAct)
            menu.exec_(self.trial_list.viewport().mapToGlobal(position))

    def change_to_characterized(self, idx):
        if self.char_combo.count() == 0: return
        label = self.char_combo.currentText()
        self.trials[idx].is_characterized = True
        self.trials[idx].characterized_source = label
        self.load_trajectory_list()
        self.plot_trial(self.trials[idx])

    def revert_to_randomized(self, idx):
        self.trials[idx].is_characterized = False
        self.trials[idx].characterized_source = None
        self.load_trajectory_list()
        self.plot_trial(self.trials[idx])

    def delete_trajectory(self, idx):
        if QMessageBox.question(self, "Confirm", f"Delete trial {idx+1}?", QMessageBox.Yes|QMessageBox.No) == QMessageBox.Yes:
            del self.trials[idx]
            self.load_trajectory_list()
            self.plot_widget.clear()

    def parse_pattern(self, pattern_str):

        try:
            expanded = self.parse_shorthand_pattern(pattern_str)
        except ValueError as e:
            QMessageBox.warning(self, "Invalid Pattern", str(e))
            return []

        segments = []
        if not expanded:
            return segments

        last = expanded[0]
        count = 1
        for ch in expanded[1:]:
            if ch == last:
                count += 1
            else:
                segments.append((last, count))
                last = ch
                count = 1
        segments.append((last, count))
        return segments

    def randomize_trials(self):

        if not self.random_trials_loaded:
            QMessageBox.warning(self, "Warning", "Load random trials first.")
            return

        rp_trials = [t for t in self.trials if not t.is_characterized]
        random.shuffle(rp_trials)

        new_trials = []
        rp_idx = 0
        for trial in self.trials:
            if trial.is_characterized:
                new_trials.append(trial)
            else:
                new_trials.append(rp_trials[rp_idx])
                rp_idx += 1

        self.trials = new_trials
        self.load_trajectory_list()


    def disperse_characterized_trials(self, segments):

        rp_pool = [t for t in self.trials if not t.is_characterized]

        label = self.char_combo.currentText()
        char_df = self.characterized_dfs.get(label)
        if char_df is None:
            QMessageBox.warning(self, "Error", "No characterized data selected.")
            return

        trial_val = int(char_df.iloc[0, 4])

        new_trials = []
        i_r = 0
        for typ, count in segments:
            if typ == "R":
                new_trials.extend(rp_pool[i_r : i_r + count])
                i_r += count
            else: 
                for _ in range(count):
                    t = Trial(trial_val, char_df.copy())
                    t.is_characterized = True
                    t.characterized_source = label
                    new_trials.append(t)

        self.trials = new_trials
        self.load_trajectory_list()

    def random_replace_trials(self):
        if not self.random_trials_loaded or self.char_combo.count() == 0:
            QMessageBox.warning(self, "Warning", "Load both random and characterized CSV first.")
            return

        replace_mode = self.replace_checkbox.isChecked()

        if not replace_mode:
            rp_list = [t for t in self.trials if not t.is_characterized]
            rp_count = len(rp_list)

            cp_count, ok = QInputDialog.getInt(
                self, "Add Characterized",
                f"How many characterized trials to add? (You have {rp_count} random trials)",
                min=1
            )
            if not ok:
                return

            label = self.char_combo.currentText()
            char_df = self.characterized_dfs.get(label)
            if char_df is None:
                QMessageBox.warning(self, "Error", "No characterized data selected.")
                return
            trial_val = int(char_df.iloc[0, 4])

            cp_list = []
            for _ in range(cp_count):
                t = Trial(trial_val, char_df.copy())
                t.is_characterized = True
                t.characterized_source = label
                cp_list.append(t)

            total_slots = rp_count + cp_count
            insert_positions = set(random.sample(range(total_slots), cp_count))

            new_trials = []
            i_r = i_c = 0
            for slot in range(total_slots):
                if slot in insert_positions:
                    new_trials.append(cp_list[i_c]); i_c += 1
                else:
                    new_trials.append(rp_list[i_r]);   i_r += 1

            self.trials = new_trials
            self.load_trajectory_list()
            return

        total = len(self.trials)
        num, ok = QInputDialog.getInt(
            self, "Random Replacement", f"Replace how many out of {total}?", min=1, max=total
        )
        if not ok:
            return

        indices = [i for i, t in enumerate(self.trials) if not t.is_characterized]
        if len(indices) < num:
            QMessageBox.warning(self, "Warning", "Not enough random trials.")
            return

        chosen = random.sample(indices, num)
        label = self.char_combo.currentText()
        for i in chosen:
            self.trials[i].is_characterized = True
            self.trials[i].characterized_source = label

        self.load_trajectory_list()

    def on_char_combo_changed(self, idx):
        current = self.trial_list.currentItem()
        if current:
            self.change_to_characterized(self.trial_list.row(current))

    def update_all_characterized_trials(self):
        if self.char_combo.count()==0: return
        label = self.char_combo.currentText()
        for t in self.trials:
            if t.is_characterized:
                t.characterized_source = label
        self.load_trajectory_list()
        current = self.trial_list.currentItem()
        if current: self.plot_trial(self.trials[self.trial_list.row(current)])

    def export_csv(self):
        if not self.trials:
            QMessageBox.warning(self, "Warning", "No trials to export.")
            return

        HZ = 30
        total = len(self.trials)

        mixed = getattr(self, "mixed_cue_checkbox", None) and self.mixed_cue_checkbox.isChecked()
        even  = getattr(self, "even_dist_checkbox",  None) and self.even_dist_checkbox.isChecked()
        has_custom = any(hasattr(t, "cue_pattern") for t in self.trials)

        if not mixed:
            cue_flags = [int(t.is_characterized) for t in self.trials]

        else:
            if has_custom:
                cue_flags = [int(t.cue_pattern) for t in self.trials]
            elif mixed and even:
                rp_indices = [i for i, t in enumerate(self.trials) if not t.is_characterized]
                cp_indices = [i for i, t in enumerate(self.trials) if     t.is_characterized]

                base = total // 4
                rem  = total % 4
                priority = [(1,1),(0,1),(1,0),(0,0)]
                counts = {combo: base for combo in priority}
                for j in range(rem):
                    counts[priority[j]] += 1

                cue_flags = [0]*total
                for idx in random.sample(cp_indices, min(counts[(1,1)], len(cp_indices))):
                    cue_flags[idx] = 1
                for idx in random.sample(rp_indices, min(counts[(0,1)], len(rp_indices))):
                    cue_flags[idx] = 1

            else:
                cue_flags = [int(t.is_characterized) for t in self.trials]
                if hasattr(self, "cue_count_spin"):
                    n_cues = min(self.cue_count_spin.value(), total)
                else:
                    n_cues = total
                for i in random.sample(range(total), n_cues):
                    cue_flags[i] = 1

        df_list = []
        for tn, (trial, cue) in enumerate(zip(self.trials, cue_flags), start=1):
            df0 = trial.get_data(self.characterized_dfs).iloc[:, :4].copy()
            df0.columns = ["X", "Y", "Normalized X", "Normalized Y"]
            duration = round(len(df0) / HZ, 3)

            df0["Trial"]      = tn
            df0["HZ"]         = HZ
            df0["Duration"]   = duration
            df0["Cue Type"]   = int(cue)
            df0["Trial Type"] = int(trial.is_characterized)

            df_list.append(df0)

        export_df = pd.concat(df_list, ignore_index=True)

        fname, _ = QFileDialog.getSaveFileName(self, "Export CSV", "", "CSV Files (*.csv)")
        if fname:
            try:
                export_df.to_csv(fname, index=False)
                QMessageBox.information(self, "Export", "CSV exported successfully.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to export CSV: {e}")

    def custom_replace_pattern(self):
        if not self.random_trials_loaded or self.char_combo.count() == 0:
            QMessageBox.warning(self, "Warning", "Load both random and characterized CSV first.")
            return

        replace_mode = self.replace_checkbox.isChecked()

        if replace_mode:
            pattern, ok = QInputDialog.getText(
                self, "Custom Pattern", "Enter pattern shorthand (e.g., R10C5R5):"
            )
            if not ok:
                return

            expanded = self.parse_shorthand_pattern(pattern)
            if not expanded:
                QMessageBox.warning(self, "Invalid Input", "Pattern must follow R10C5…")
                return

            if len(expanded) != len(self.trials):
                reply = QMessageBox.question(
                    self, "Length Mismatch",
                    f"Expanded pattern length ({len(expanded)}) != trials ({len(self.trials)}). Continue?",
                    QMessageBox.Yes | QMessageBox.No
                )
                if reply == QMessageBox.No:
                    return

            label = self.char_combo.currentText()
            for i, c in enumerate(expanded):
                if i >= len(self.trials):
                    break
                is_c = (c == 'C')
                self.trials[i].is_characterized = is_c
                self.trials[i].characterized_source = label if is_c else None

            self.load_trajectory_list()
            return

        pattern, ok = QInputDialog.getText(
            self, "Disperse Pattern", "Enter shorthand (e.g. R10C10R10C10R5C5):"
        )
        if not ok:
            return

        segments = self.parse_pattern(pattern)
        if not segments:
            QMessageBox.warning(self, "Invalid Input", "Pattern must be like R10C5R5…")
            return

        self.disperse_characterized_trials(segments)

    def custom_cue_pattern(self):
        if not self.random_trials_loaded or self.char_combo.count() == 0:
            QMessageBox.warning(self, "Warning", "Load both random and characterized CSV first.")
            return

        pattern, ok = QInputDialog.getText(
            self, "Custom Cue Pattern",
            "Enter cue pattern shorthand (e.g. R10C5R5):"
        )
        if not ok:
            return

        expanded = self.parse_shorthand_pattern(pattern)
        if not expanded:
            QMessageBox.warning(self, "Invalid Input", "Pattern must follow R/C format like R10C5…")
            return

        if len(expanded) != len(self.trials):
            reply = QMessageBox.question(
                self, "Length Mismatch",
                f"Expanded cue pattern length ({len(expanded)}) differs from trials ({len(self.trials)}). Continue?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.No:
                return

        for i, c in enumerate(expanded):
            if i >= len(self.trials):
                break
            self.trials[i].cue_pattern = (c == "C")

        self.load_trajectory_list()

    def parse_shorthand_pattern(self, pattern):
        pattern = pattern.replace(" ", "").upper()

        def expand_group(s):
            output = ""
            i = 0
            while i < len(s):
                if s[i] in "RC":
                    char = s[i]
                    i += 1
                    num = ""
                    while i < len(s) and s[i].isdigit():
                        num += s[i]
                        i += 1
                    count = int(num) if num else 1
                    output += char * count
                elif s[i] == "(":
                    depth = 1
                    j = i + 1
                    while j < len(s) and depth > 0:
                        if s[j] == "(": depth += 1
                        elif s[j] == ")": depth -= 1
                        j += 1
                    if depth != 0:
                        raise ValueError("Unmatched parentheses in pattern.")
                    group = s[i+1:j-1]
                    i = j
                    num = ""
                    while i < len(s) and s[i].isdigit():
                        num += s[i]
                        i += 1
                    count = int(num) if num else 1
                    output += expand_group(group) * count
                else:
                    raise ValueError(f"Unexpected character '{s[i]}' in pattern.")
            return output

        return expand_group(pattern)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = TrajectoryOrganizer()
    window.show()
    sys.exit(app.exec_())
