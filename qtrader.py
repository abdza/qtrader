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
        top_part.addWidget(self._buy_form_group,2)
        top_part.addWidget(self._info_box_group,2)
        self.layout.addLayout(top_part,1)
        self.layout.addWidget(self._chart_group,5)
    
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
        self.update_button = QPushButton("Update")
        self.update_button.clicked.connect(self.pressed_update)
        tickerbox = QHBoxLayout()
        tickerbox.addWidget(self.ticker_text)
        tickerbox.addWidget(self.update_button)
        layout.addRow(QLabel("Ticker: "), tickerbox )
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

    @Slot()
    def pressed_update(self):
        self.update_chart()

    def update_chart(self):
        acmeSeries = QCandlestickSeries()
        acmeSeries.setName(self.ticker_text.text())
        acmeSeries.setIncreasingColor(QColor(Qt.green))
        acmeSeries.setDecreasingColor(QColor(Qt.red))
        newYorkTz = pytz.timezone("America/New_York")
        end_date = datetime.now()
        days = 60
        start_date = end_date - timedelta(days=days)
        candles = yf.download(self.ticker_text.text().upper(),start=start_date,end=end_date,interval='1d',prepost=False)
        candles['timestamp'] = [ pd.Timestamp(dt) for dt in candles.index.values ]
        categories = []
        print(str(candles))
        print("----------------------------------------------------")
        for idx in range(len(candles)):
            candle = candles.iloc[idx]
            candlestickSet = QCandlestickSet(candle['Open'],candle['Close'],candle['Low'],candle['High'],QDateTime(candle['timestamp']).toMSecsSinceEpoch())
            acmeSeries.append(candlestickSet)
            categories.append(QDateTime(candle['timestamp']).toString("dd-MM-yyyy"))

        print(str(categories))
        self.chart.removeAllSeries()
        self.chart.addSeries(acmeSeries)
        self.chart.createDefaultAxes()
        self.chart.axisX().setLabelsAngle(-90)
        self.chart.axisY().setMax(candles['High'].max() * 1.1)
        self.chart.axisY().setMin(candles['Low'].min() * 0.9)
    
    def create_chart(self):
        self.ticker_text.setText("BBBY")
        self._chart_group = QGroupBox("Chart")
        self.chart = QChart()
        self.update_chart()
        self.chart.setTitle("Historical Data")
        self.chart.setAnimationOptions(QChart.SeriesAnimations)
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
