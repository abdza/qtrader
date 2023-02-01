#!/bin/env python3
import sys
import pytz
import math
import sqlite3
import ib_insync as ib
from PySide6 import QtCore, QtGui
from PySide6.QtCore import Slot,QPointF,QDateTime
from PySide6.QtWidgets import *
from PySide6.QtCharts import *
from PySide6.QtGui import *
import yfinance as yf
import yahooquery as yq
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

con = sqlite3.connect("qtrader.db")
current_ib = ib.IB()

def latest_price(ticker):
    tickerQuery = yq.Ticker(ticker, asynchronous=False, Timeout=100)
    if "regularMarketPrice" in tickerQuery.price[ticker]:
        return tickerQuery.price[ticker]["regularMarketPrice"]
    else:
        return 0

def connect_ib():
    if not current_ib.isConnected():
        print("Currently not connected")
        try:
            current_ib.connect('127.0.0.1', 7777, clientId=1)  # TWS live
            print("Connected to IB")
            print("Current positions:")
            print(current_ib.positions())
        except Exception as e:
            print("Fail to connect to IB")
            print(e)

def update_table():
    cursor = con.cursor()
    cursor.execute("create table if not exists trades(trade_id INTEGER PRIMARY KEY,trade_date,ticker,setup,buy_price,sell_price,amount,stop_loss,r1,r2,total,status,pnl)")
    cursor.execute("create table if not exists trigger(trigger_id INTEGER PRIMARY KEY,trade_date,ticker,status,trigger_type,price)")
    con.commit()
    cursor.close()

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
    headers = ['Date','Ticker','Setup','Price','Units','Loss Limit','R1','R2','P&L']
    def __init__(self):
        super().__init__()
        self.setColumnCount(len(self.headers))
        self.setAlternatingRowColors(True)
        self.update_list()
        header = self.horizontalHeader()
        header.setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1,QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2,QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3,QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4,QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(5,QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(6,QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(7,QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(8,QHeaderView.ResizeMode.Stretch)
        self.setHorizontalHeaderLabels(self.headers)
    
    def update_list(self):
        cursor = con.cursor()
        trades = cursor.execute("select * from trades")
        self.clear()
        self.setRowCount(0)
        for trade in trades:
            curpos = self.rowCount()
            self.insertRow(curpos)
            self.setItem(curpos,0,QTableWidgetItem(trade[1]))
            self.setItem(curpos,1,QTableWidgetItem(trade[2]))
            self.setItem(curpos,2,QTableWidgetItem(trade[3]))
            self.setItem(curpos,3,QTableWidgetItem(trade[4]))
            self.setItem(curpos,4,QTableWidgetItem(trade[6]))
            self.setItem(curpos,5,QTableWidgetItem(trade[7]))
            self.setItem(curpos,6,QTableWidgetItem(trade[8]))
            self.setItem(curpos,7,QTableWidgetItem(trade[9]))
            self.setItem(curpos,8,QTableWidgetItem(trade[12]))
        self.setHorizontalHeaderLabels(self.headers)
        cursor.close()

class TradeListWindow(QWidget):
    def __init__(self):
        super().__init__()
        connect_ib()

        self.list = TradeListTable()
        self.layout = QVBoxLayout(self)
        self.layout.addWidget(self.list)

        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.checkprice)
        self.timer.start(60000)

        actionrow = QHBoxLayout(self)
        self.ticker_text = QTextEdit("BBBY")
        self.ticker_text.setMaximumHeight(30)
        self.buy_button = QPushButton("Buy")
        actionrow.addWidget(self.ticker_text)
        actionrow.addWidget(self.buy_button)
        self.buy_button.clicked.connect(self.open_buy)

        self.layout.addLayout(actionrow)
    
    @Slot()
    def checkprice(self):
        print("Checking prices")
        if current_ib.isConnected():
            cursor = con.cursor()
            tickers = cursor.execute("select distinct ticker from trigger where status='Active'")
            cur_pos = current_ib.positions()
            positions = {}
            for cps in cur_pos:  # Loop over stock we own according to ib
                ticker = cps[1].localSymbol
                amount = cps[2]
                positions[ticker] = amount
            for ticker in tickers.fetchall():
                if ticker[0] in positions and positions[ticker[0]]>0:
                    price = latest_price(ticker[0])
                    triggers = cursor.execute("select * from trigger where status='Active' and ticker=:ticker and trigger_type=:trigger_type order by price",
                    {'ticker':ticker[0],'trigger_type':'Above'})
                    trigger = triggers.fetchone()
                    if trigger:
                        if price>trigger[5]:
                            divide = len(triggers.fetchall())
                            if divide==0:
                                divide = 1
                            to_sell = math.floor(positions[ticker[0]]/divide)
                            stock = ib.Stock(ticker[0],'SMART','USD')
                            order = ib.Order()
                            order.lmtPrice = price
                            order.orderType = 'LMT'
                            order.transmit = True
                            order.totalQuantity = float(to_sell)
                            order.action = 'SELL'
                            dps = str(current_ib.reqContractDetails(stock)[0].minTick + 1)[::-1].find('.') - 1
                            order.lmtPrice = round(order.lmtPrice + current_ib.reqContractDetails(stock)[0].minTick * 2,dps)
                            sell = current_ib.placeOrder(stock,order)
                            current_ib.sleep(5)
                            if sell.orderStatus.status=='Filled' or sell.orderStatus.status=='Submitted':
                                cursor.execute("update trigger set status='Filled' where trigger_id=:id",{'id':trigger[0]})
                                if divide==1:
                                    cursor.execute("update trigger set status='Cancel' where ticker=:ticker and status='Active'",{'ticker':ticker[0]})
                                status = True
                            else:
                                status = False
            triggers = cursor.execute("select * from trigger where status='Active' and ticker=:ticker and trigger_type=:trigger_type order by price desc",
            {'ticker':ticker[0],'trigger_type':'Below'})
            trigger = triggers.fetchone()
            if trigger:
                if price<trigger[5]:
                    divide = len(triggers.fetchall())
                    if divide==0:
                        divide = 1
                    to_sell = math.floor(positions[ticker[0]]/divide)
                    stock = ib.Stock(ticker[0],'SMART','USD')
                    order = ib.Order()
                    order.lmtPrice = price
                    order.orderType = 'MKT'
                    order.transmit = True
                    order.totalQuantity = float(to_sell)
                    order.action = 'SELL'
                    dps = str(current_ib.reqContractDetails(stock)[0].minTick + 1)[::-1].find('.') - 1
                    order.lmtPrice = round(order.lmtPrice + current_ib.reqContractDetails(stock)[0].minTick * 2,dps)
                    sell = current_ib.placeOrder(stock,order)
                    current_ib.sleep(5)
                    if sell.orderStatus.status=='Filled' or sell.orderStatus.status=='Submitted':
                        cursor.execute("update trigger set status='Filled' where trigger_id=:id",{'id':trigger[0]})
                        if divide==1:
                            cursor.execute("update trigger set status='Cancel' where ticker=:ticker and status='Active'",{'ticker':ticker[0]})
                        status = True
                    else:
                        status = False
            con.commit()
            cursor.close()

    @Slot()
    def open_buy(self):
        self.buywindow = BuyWindow()
        self.buywindow.caller = self
        self.buywindow.resize(800,600)
        self.buywindow.ticker_text.setText(self.ticker_text.toPlainText())
        self.buywindow.pressed_update()
        self.buywindow.showMaximized()
        self.buywindow.activateWindow()

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
        self.stop_text.textChanged.connect(self.update_total_amount)
        self.r1_text = QLineEdit()
        self.r1_text.textChanged.connect(self.update_total_amount)
        self.r2_text = QLineEdit()
        self.r2_text.textChanged.connect(self.update_total_amount)
        self.amount_text = QLineEdit()
        self.amount_text.textChanged.connect(self.update_total_amount)
        self.buy_button = QPushButton("Buy")
        self.buy_button.clicked.connect(self.buy_action)
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
    def buy_action(self):
        if current_ib.isConnected():
            stock = ib.Stock(self.ticker_text.text(),'SMART','USD')
            order = ib.Order()
            order.lmtPrice = float(self.price_text.text())
            order.orderType = 'LMT'
            order.transmit = True
            order.totalQuantity = float(self.amount_text.text())
            order.action = 'BUY'
            dps = str(current_ib.reqContractDetails(stock)[0].minTick + 1)[::-1].find('.') - 1
            order.lmtPrice = round(order.lmtPrice + current_ib.reqContractDetails(stock)[0].minTick * 2,dps)
            bought = current_ib.placeOrder(stock,order)
            current_ib.sleep(5)
            if bought.orderStatus.status=='Filled' or bought.orderStatus.status=='Submitted':
                status = True
            else:
                status = False
        cursor = con.cursor()
        query = "insert into trades(trade_date,ticker,setup,buy_price,sell_price,amount,stop_loss,r1,r2,total,status,pnl) values (:trade_date,:ticker,:setup,:buy_price,:sell_price,:amount,:stop_loss,:r1,:r2,:total,:status,:pnl)"
        data = {"trade_date":datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "ticker":self.ticker_text.text(),
        "setup":self.setup_text.toPlainText(),
        "buy_price":self.price_text.text(),
        "sell_price":None,
        "amount":self.amount_text.text(),
        "stop_loss":self.stop_text.text(),
        "r1":self.r1_text.text(),
        "r2":self.r2_text.text(),
        "total":self.total_amount_label.text(),
        "status":"New",
        "pnl":None}
        print("Query:",query)
        print("Data:",data)
        cursor.execute(query,data)
        con.commit()
        query = "insert into trigger(trade_date,ticker,status,trigger_type,price) values (:trade_date,:ticker,:status,:trigger_type,:price)"
        data = [{"trade_date":datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "ticker":self.ticker_text.text(),
        "status":"Active",
        "trigger_type":"Above",
        "price":float(self.r1_text.text())},
        {"trade_date":datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "ticker":self.ticker_text.text(),
        "status":"Active",
        "trigger_type":"Below",
        "price":float(self.stop_text.text())}]
        if len(self.r2_text.text()):
            data.append(
        {"trade_date":datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "ticker":self.ticker_text.text(),
        "status":"Active",
        "trigger_type":"Above",
        "price":float(self.r2_text.text())}
            )
        print("Query:",query)
        print("Data:",data)
        cursor.executemany(query,data)
        con.commit()
        cursor.close()
        print("Buy ticker ",self.ticker_text.text())
        self.caller.list.update_list()
        self.caller.activateWindow()
        self.close()

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
        if len(self.amount_text.text()):
            self.amount = float(self.amount_text.text())
        else:
            self.amount = 0
        self.total_amount = self.price * self.amount
        self.total_amount_label.setText(str(self.total_amount))

        if len(self.stop_text.text()):
            pnl_stop = (self.amount * float(self.stop_text.text())) - self.total_amount
            self.pnl_stop_label.setText(str(pnl_stop))
        else:
            self.pnl_stop_label.setText("0")

        if len(self.r1_text.text()):
            pnl_r1 = (self.amount * float(self.r1_text.text())) - self.total_amount
            self.pnl_r1_label.setText(str(pnl_r1))
        else:
            self.pnl_r1_label.setText("0")

        if len(self.r2_text.text()):
            pnl_r2 = (self.amount * float(self.r2_text.text())) - self.total_amount
            self.pnl_r2_label.setText(str(pnl_r2))
        else:
            self.pnl_r2_label.setText("0")

    def create_info_box(self):
        self._info_box_group = QGroupBox("Info")
        layout = QFormLayout()
        self.stockfloat_label = QLabel("float")
        self.volume24h_label = QLabel("float")
        self.levels_label = QLabel("float")
        self.size_mean_label = QLabel("float")
        self.total_amount_label = QLabel("float")
        self.pnl_stop_label = QLabel("float")
        self.pnl_r1_label = QLabel("float")
        self.pnl_r2_label = QLabel("float")
        layout.addRow(QLabel("Float: "), self.stockfloat_label)
        layout.addRow(QLabel("24h Volume: "), self.volume24h_label)
        layout.addRow(QLabel("Levels: "), self.levels_label)
        layout.addRow(QLabel("Size Mean: "), self.size_mean_label)
        layout.addRow(QLabel("Total Amount: "), self.total_amount_label)
        layout.addRow(QLabel("Stop Loss P&L: "), self.pnl_stop_label)
        layout.addRow(QLabel("R1 P&L: "), self.pnl_r1_label)
        layout.addRow(QLabel("R2 P&L: "), self.pnl_r2_label)
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
        ymin = candles['Low'].min()
        ymax = candles['High'].max()
        size_mean,levels = find_levels(candles)
        levels.sort()
        self.levels_label.setText(','.join([ str(x) for x in levels]))
        self.size_mean_label.setText(str(size_mean))
        lastcandle = candles.iloc[-1]
        self.price = latest_price(self.ticker_text.text().upper())
        curend = -2
        endloop = len(candles) * -1
        while curend>endloop and candles.iloc[curend]['Low']>self.price:
            curend -= 1
        if curend>endloop:
            self.stop_text.setText(str(round(candles.iloc[curend]['Low'],4)))
        else:
            self.stop_text.setText(str(round(lastcandle['Low'],4)))
        self.price_text.setText(str(round(self.price,4)))
        self.update_price()
        self.r2_text.setText("")
        if self.price<levels[-1]:
            i = 0
            while i<len(levels)-1 and self.price>levels[i]:
                i+=1
            self.r1_text.setText(str(round(levels[i],4)))
            j = i + 1
            if j<len(levels):
                while self.price>levels[j] and j<len(levels):
                    j+=1
                if j>i:
                    self.r2_text.setText(str(round(levels[j],4)))
        else:
            self.r1_text.setText(str(math.ceil(self.price)))

        for idx in range(len(candles)):
            candle = candles.iloc[idx]
            candlestickSet = QCandlestickSet(candle['Open'],candle['High'],candle['Low'],candle['Close'],QDateTime(candle['timestamp']).toMSecsSinceEpoch())
            acmeSeries.append(candlestickSet)
        self.chart.removeAllSeries()
        self.chart.addSeries(acmeSeries)
        self.chart.createDefaultAxes()
        self.chart.axisX().setLabelsAngle(-90)
        self.chart.axisY().setMax(ymax * 1.1)
        self.chart.axisY().setMin(ymin * 0.9)
    
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
    update_table()
    app = QApplication([])
    widget = TradeListWindow()
    widget.resize(800,600)
    widget.showMaximized()

    sys.exit(app.exec())
