#!/bin/env python3
import sys
from PySide6 import QtCore, QtWidgets, QtGui

class TradeListWindow(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.buy_button = QtWidgets.QPushButton("Buy")
        self.layout = QtWidgets.QVBoxLayout(self)
        self.layout.addWidget(self.buy_button)

if __name__=="__main__":
    app = QtWidgets.QApplication([])
    widget = TradeListWindow()
    widget.resize(800,600)
    widget.show()

    sys.exit(app.exec())
