import sys
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QPushButton, QLabel
from PyQt5.QtCore    import QProcess

class MainMenu(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Trajectory Generator Main Menu")
        self.processes = []            
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout()
        layout.addWidget(QLabel("Select a program to launch:"))

        btn_random = QPushButton("Randomized Trajectory Generator")
        btn_random.clicked.connect(self.launch_randomized_generator)
        layout.addWidget(btn_random)

        btn_characterized = QPushButton("Characterized Trajectory Generator")
        btn_characterized.clicked.connect(self.launch_characterized_generator)
        layout.addWidget(btn_characterized)

        btn_organizer = QPushButton("Trajectory Organizer")
        btn_organizer.clicked.connect(self.launch_organizer)
        layout.addWidget(btn_organizer)

        btn_interpolator = QPushButton("Interpolate Randomized Trajectory")
        btn_interpolator.clicked.connect(self.launch_interpolator)
        layout.addWidget(btn_interpolator)

        btn_exit = QPushButton("Exit")
        btn_exit.clicked.connect(self.close)
        layout.addWidget(btn_exit)

        self.setLayout(layout)

    def _start_tool(self, script_name):
        proc = QProcess(self)
        proc.finished.connect(self.on_process_finished)
        proc.start(sys.executable, [script_name])
        self.processes.append(proc)
        self.hide()

    def launch_randomized_generator(self):
        self._start_tool("pursuitsim.py")

    def launch_characterized_generator(self):
        self._start_tool("main.py")

    def launch_organizer(self):
        self._start_tool("trajectory_organizer.py")

    def launch_interpolator(self):
        self._start_tool("interpolate.py")

    def on_process_finished(self, exitCode, exitStatus):
        sender = self.sender()
        if sender in self.processes:
            self.processes.remove(sender)
        if not self.processes:
            self.show()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = MainMenu()
    win.show()
    sys.exit(app.exec_())
