#!/bin/env python3
import sys
import pytz
from PySide6 import QtCore, QtGui
from PySide6.QtCore import Slot,QStringListModel,QDateTime
from PySide6.QtWidgets import *
from PySide6.QtCharts import *
from PySide6.QtGui import *
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

class TradeListTable(QTableWidget):

    headers = [
            'Date','Ticker','Setup','Price','Units','Loss Limit','R1','R2'
            ]
    def __init__(self):
        super().__init__()
        self.setColumnCount(len(self.headers))
        self.setHorizontalHeaderLabels(self.headers)
        self.setAlternatingRowColors(True)

class TradeListWindow(QWidget):
    def __init__(self):
        super().__init__()

        self.list = TradeListTable()
        self.layout = QVBoxLayout(self)
        self.layout.addWidget(self.list)

        actionrow = QHBoxLayout(self)
        self.ticker_text = QTextEdit()
        self.ticker_text.setMaximumHeight(30)
        self.buy_button = QPushButton("Buy")
        actionrow.addWidget(self.ticker_text)
        actionrow.addWidget(self.buy_button)
        self.buy_button.clicked.connect(self.open_buy)

        self.layout.addLayout(actionrow)

    @Slot()
    def open_buy(self):
        self.buywindow = BuyWindow()
        self.buywindow.resize(800,600)
        self.buywindow.ticker_text.setText(self.ticker_text.toPlainText())
        self.buywindow.show()


class BuyWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.create_buy_form()
        self.create_info_box()
        self.create_chart()

        self.layout = QVBoxLayout(self)
        top_part = QHBoxLayout(self)
        top_part.addWidget(self._buy_form_group)
        top_part.addWidget(self._info_box_group)
        self.layout.addLayout(top_part)
        self.layout.addWidget(self._chart_group)
    
    def create_buy_form(self):
        self._buy_form_group = QGroupBox("Buy")
        layout = QFormLayout()
        self.ticker_text = QLineEdit()
        self.ticker_text.setText("BBBY")
        self.setup_text = QTextEdit()
        self.price_text = QLineEdit()
        self.stop_text = QLineEdit()
        self.r1_text = QLineEdit()
        self.r2_text = QLineEdit()
        self.buy_button = QPushButton("Buy")
        layout.addRow(QLabel("Ticker: "), self.ticker_text )
        layout.addRow(QLabel("Setup: "), self.setup_text )
        layout.addRow(QLabel("Price: "), self.price_text )
        layout.addRow(QLabel("Stop Loss: "), self.stop_text )
        layout.addRow(QLabel("R1: "), self.r1_text ) 
        layout.addRow(QLabel("R2: "), self.r2_text )
        layout.addRow(self.buy_button)
        self._buy_form_group.setLayout(layout)

    def create_info_box(self):
        self._info_box_group = QGroupBox("Info")
        layout = QFormLayout()
        self.yearlyhigh = QLabel("high")
        self.yearlylow = QLabel("low")
        self.stockfloat = QLabel("float")
        layout.addRow(QLabel("52 Week High: "), self.yearlyhigh)
        layout.addRow(QLabel("52 Week Low: "), self.yearlylow)
        layout.addRow(QLabel("Float: "), self.stockfloat)
        self._info_box_group.setLayout(layout)
    
    def create_chart(self):
        self._chart_group = QGroupBox("Chart")
        self.chart = QChart()
        acmeSeries = QCandlestickSeries()
        acmeSeries.setName("Acme Ltd")
        acmeSeries.setIncreasingColor(QColor(Qt.green))
        acmeSeries.setDecreasingColor(QColor(Qt.red))
        newYorkTz = pytz.timezone("America/New_York")
        end_date = datetime.now()
        days = 60
        start_date = end_date - timedelta(days=days)
        candles = yf.download('BBBY',start=start_date,end=end_date,interval='1d',prepost=False)
        candles['timestamp'] = [ pd.Timestamp(dt) for dt in candles.index.values ]
        categories = []
        print(str(candles))
        print("----------------------------------------------------")
        for idx in range(len(candles)):
            candle = candles.iloc[idx]
            candlestickSet = QCandlestickSet(candle['Open'],candle['Close'],candle['Low'],candle['High'],candle['timestamp'].timestamp())
            acmeSeries.append(candlestickSet)
            categories.append(QDateTime(candle['timestamp']).toString("dd-MM-yyyy"))

        print(str(categories))
        self.chart.addSeries(acmeSeries)
        self.chart.setTitle("Acme Ltd Historical Data")
        self.chart.setAnimationOptions(QChart.SeriesAnimations)
        self.chart.createDefaultAxes()
        axisX = QBarCategoryAxis(self.chart.axes(Qt.Horizontal)[0])
        axisX.orientation = "Vertical"
        axisX.setCategories(categories)
        axisY = QValueAxis(self.chart.axes(Qt.Vertical)[0])
        axisY.setMax(axisY.max() * 1.01)
        axisY.setMin(axisY.min() * 0.99)
        self.chart.legend().setVisible(True)
        self.chart.legend().setAlignment(Qt.AlignBottom)
        layout = QVBoxLayout()
        self.chartview = QChartView(self.chart)
        self.chartview.setRenderHint(QPainter.Antialiasing)
        layout.addWidget(self.chartview)
        self._chart_group.setLayout(layout)

if __name__=="__main__":
    app = QApplication([])
    widget = BuyWindow()
    widget.resize(800,600)
    widget.show()

    sys.exit(app.exec())
