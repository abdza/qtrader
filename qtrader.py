#!/bin/env python3
import sys
import pytz
import math
from PySide6 import QtCore, QtGui
from PySide6.QtCore import Slot,QPointF,QDateTime
from PySide6.QtWidgets import *
from PySide6.QtCharts import *
from PySide6.QtGui import *
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

def find_levels(candles):
    levels = []
    size_mean = np.mean(candles['High']-candles['Low'])
    for i in range(2,len(candles)-2):
        if is_support(candles,i):
            val = candles['Low'][i]
            if is_far_from_levels(val,size_mean,levels):
                levels.append(val)
        elif is_resistance(candles,i):
            val = candles['High'][i]
            if is_far_from_levels(val,size_mean,levels):
                levels.append(val)
    return size_mean,levels

def is_support(candles,i):     # i is at lowest low
    cond1 = candles['Low'][i] <= candles['Low'][i-1]
    cond2 = candles['Low'][i] <= candles['Low'][i+1]
    cond3 = candles['Low'][i+1] < candles['Low'][i+2]
    cond4 = candles['Low'][i-1] < candles['Low'][i-2]
    return cond1 and cond2 and cond3 and cond4

def is_resistance(candles,i):  # i is at highest high
    cond1 = candles['High'][i] >= candles['High'][i-1]
    cond2 = candles['High'][i] >= candles['High'][i+1]
    cond3 = candles['High'][i+1] > candles['High'][i+2]
    cond4 = candles['High'][i-1] > candles['High'][i-2]
    return cond1 and cond2 and cond3 and cond4

def highest_low(candles,i):  # i is at highest low
    cond1 = candles['Low'][i] >= candles['Low'][i-1]
    cond2 = candles['Low'][i] >= candles['Low'][i+1]
    cond3 = candles['Low'][i+1] > candles['Low'][i+2]
    cond4 = candles['Low'][i-1] > candles['Low'][i-2]
    return cond1 and cond2 and cond3 and cond4

def lowest_high(candles,i):  # i is at lowest high
    cond1 = candles['High'][i] <= candles['High'][i-1]
    cond2 = candles['High'][i] <= candles['High'][i+1]
    cond3 = candles['High'][i+1] < candles['High'][i+2]
    cond4 = candles['High'][i-1] < candles['High'][i-2]
    return cond1 and cond2 and cond3 and cond4

def is_far_from_levels(val,size_mean,levels):
    return np.sum([abs(val-x) < size_mean for x in levels]) == 0

def candle_size(candle):
    return candle['High'] - candle['Low']

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
        self.trade_limit_text = QLineEdit("200")
        self.trade_limit_text.textChanged.connect(self.update_limit)
        self.ticker_text = QLineEdit()
        self.ticker_text.setText("BBBY")
        self.setup_text = QTextEdit()
        self.price_text = QLineEdit()
        self.price_text.textChanged.connect(self.update_price)
        self.stop_text = QLineEdit()
        self.r1_text = QLineEdit()
        self.r2_text = QLineEdit()
        self.amount_text = QLineEdit()
        self.amount_text.textChanged.connect(self.update_total_amount)
        self.buy_button = QPushButton("Buy")
        self.update_button = QPushButton("Update")
        self.update_button.clicked.connect(self.pressed_update)
        tickerbox = QHBoxLayout()
        tickerbox.addWidget(self.ticker_text)
        tickerbox.addWidget(self.update_button)
        layout.addRow(QLabel("Trade Limit: "), self.trade_limit_text )
        layout.addRow(QLabel("Ticker: "), tickerbox )
        layout.addRow(QLabel("Setup: "), self.setup_text )
        layout.addRow(QLabel("Price: "), self.price_text )
        layout.addRow(QLabel("Stop Loss: "), self.stop_text )
        layout.addRow(QLabel("R1: "), self.r1_text ) 
        layout.addRow(QLabel("R2: "), self.r2_text )
        layout.addRow(QLabel("Amount: "), self.amount_text )
        layout.addRow(self.buy_button)
        self._buy_form_group.setLayout(layout)

    @Slot()
    def update_limit(self):
        self.update_amount()

    @Slot()
    def update_price(self):
        self.price = float(self.price_text.text())
        self.update_amount()
    
    def update_amount(self):
        self.amount = math.floor(float(self.trade_limit_text.text())/self.price)
        self.amount_text.setText(str(self.amount))
        self.update_total_amount()

    @Slot()
    def update_total_amount(self):
        self.amount = float(self.amount_text.text())
        self.total_amount = self.price * self.amount
        self.total_amount_label.setText(str(self.total_amount))

    def create_info_box(self):
        self._info_box_group = QGroupBox("Info")
        layout = QFormLayout()
        self.stockfloat_label = QLabel("float")
        self.volume24h_label = QLabel("float")
        self.levels_label = QLabel("float")
        self.size_mean_label = QLabel("float")
        self.total_amount_label = QLabel("float")
        layout.addRow(QLabel("Float: "), self.stockfloat_label)
        layout.addRow(QLabel("24h Volume: "), self.volume24h_label)
        layout.addRow(QLabel("Levels: "), self.levels_label)
        layout.addRow(QLabel("Size Mean: "), self.size_mean_label)
        layout.addRow(QLabel("Total Amount: "), self.total_amount_label)
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
        days = 120
        start_date = end_date - timedelta(days=days)
        ticker = yf.Ticker(self.ticker_text.text().upper())
        self.stockfloat_label.setText(str(ticker.info['floatShares']))
        self.volume24h_label.setText(str(ticker.info['volume24Hr']))
        candles = yf.download(self.ticker_text.text().upper(),start=start_date,end=end_date,interval='1d',prepost=False)
        candles['timestamp'] = [ pd.Timestamp(dt) for dt in candles.index.values ]
        size_mean,levels = find_levels(candles)
        levels.sort()
        self.levels_label.setText(','.join([ str(x) for x in levels]))
        self.size_mean_label.setText(str(size_mean))
        lastcandle = candles.iloc[-1]
        secondlast = candles.iloc[-2]
        self.price = lastcandle['Close']
        self.price_text.setText(str(self.price))
        self.update_price()
        if self.price>levels[0]:
            i = 0
            while self.price>levels[i] and i<len(levels):
                i+=1
            self.r1_text.setText(str(levels[i]))
            j = i + 1
            if j<len(levels):
                while self.price>levels[j] and j<len(levels):
                    j+=1
                if j>i:
                    self.r2_text.setText(str(levels[j]))
        self.stop_text.setText(str(secondlast['Low']))
        categories = []
        for idx in range(len(candles)):
            candle = candles.iloc[idx]
            candlestickSet = QCandlestickSet(candle['Open'],candle['High'],candle['Low'],candle['Close'],QDateTime(candle['timestamp']).toMSecsSinceEpoch())
            acmeSeries.append(candlestickSet)
            categories.append(QDateTime(candle['timestamp']).toString("dd-MM-yyyy"))
        self.chart.removeAllSeries()
        self.chart.addSeries(acmeSeries)
        self.chart.createDefaultAxes()
        self.chart.axisX().setLabelsAngle(-90)
        self.chart.axisY().setMax(candles['High'].max() * 1.1)
        self.chart.axisY().setMin(candles['Low'].min() * 0.9)

        xmin = 0
        xmax = len(categories)
        ymin = candles['Low'].min()
        ymax = candles['High'].max()
    
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
