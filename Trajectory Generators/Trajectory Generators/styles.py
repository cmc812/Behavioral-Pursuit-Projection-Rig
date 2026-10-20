# styles.py
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