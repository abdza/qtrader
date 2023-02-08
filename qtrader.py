#!/bin/env python3
import sys
import csv
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
newYorkTz = pytz.timezone("America/New_York")

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
    cursor.execute("create table if not exists trades(trade_id INTEGER PRIMARY KEY,trade_date,ticker,setup,buy_price,sell_price,amount,stop_loss,r1,r2,total,status,pnl,close_date)")
    cursor.execute("create table if not exists trigger(trigger_id INTEGER PRIMARY KEY,trade_date,ticker,status,trigger_type,price,pnl,close_date)")
    cursor.execute("create table if not exists stocks(stocks_id INTEGER PRIMARY KEY,name,ticker,price,bear_score,vol_score,bounce_score,bear_steps,bounce_steps,pullbackswallow)")
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

def red_candle(candle):
    if candle['Open'] > candle['Close']:
        return True
    elif candle['Open'] < candle['Close']:
        return False
    else:
        if candle['High'] - candle['Close'] > candle['Close'] - candle['Low']:
            return True
        else:
            return False

def green_candle(candle):
    return not red_candle(candle)

def clean_bear_movement(first,second):
    cond1 = second['High']<=first['High']
    cond2 = second['Low']<=first['Low']
    cond3 = second['Open']<=first['Open']
    cond4 = second['Close']<=first['Close']
    return cond1 and cond2 and cond3 and cond4

def clean_bull_movement(first,second):
    cond1 = second['High']>=first['High']
    cond2 = second['Low']>=first['Low']
    cond3 = second['Open']>=first['Open']
    cond4 = second['Close']>=first['Close']
    return cond1 and cond2 and cond3 and cond4


class ScanListTable(QTableWidget):
    headers = ['Ticker','Name','Price','Bear Score','Bear Steps','Bounce Score','Bounce Steps','Vol Score','Swallow']
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

    def export_csv(self):
        cursor = con.cursor()
        stocks = cursor.execute("select name,ticker,price,bear_score,bear_steps,bounce_score,bounce_steps,vol_score,pullbackswallow from stocks where bear_steps > 0 and bounce_steps > 0 order by bear_steps desc, bear_score desc, vol_score  desc, bounce_steps desc, bounce_score desc")
        with open('shortlist_' + datetime.now().strftime("%Y_%m_%d_%H_%M_%S") + '.csv','w') as f:
            writer = csv.writer(f)
            writer.writerow(self.headers + ['Latest Close','Colour','Gap','Candle Size','Gap Size'])
            for stock in stocks.fetchall():
                end_date = datetime.now()
                days = 5
                start_date = end_date - timedelta(days=days)
                try:
                    candles = yf.download(stock[1],start=start_date,end=end_date,interval='1d',prepost=False)
                    latest = candles.iloc[-1]
                    secondlatest = candles.iloc[-2]
                    color = 'Green'
                    if red_candle(latest):
                        color = 'Red'
                    gap = 'Up'
                    if latest['Open']<secondlatest['Close']:
                        gap = 'Down'
                    gapsize = latest['Open'] - secondlatest['Close']
                    writer.writerow(stock + tuple([latest['Close'],color,gap,candle_size(latest),gapsize]))
                except Exception as exp:
                    print("Processing ",stock[1]," got error:",exp)
        dlg = QMessageBox(self)
        dlg.setWindowTitle("Export complete")
        dlg.setText("Done export")
        dlg.exec()
        print("Done export")
        cursor.close()

    def update_list(self):
        cursor = con.cursor()
        stocks = cursor.execute("select name,ticker,price,bear_score,bear_steps,bounce_score,bounce_steps,vol_score,pullbackswallow from stocks where bear_steps > 0 and bounce_steps > 0 order by bear_steps desc, bear_score desc, vol_score  desc, bounce_steps desc, bounce_score desc")
        self.clear()
        self.setRowCount(0)
        for stock in stocks:
            print("Stock:",stock[2])
            curpos = self.rowCount()
            self.insertRow(curpos)
            self.setItem(curpos,0,QTableWidgetItem(stock[1]))
            self.setItem(curpos,1,QTableWidgetItem(stock[0]))
            self.setItem(curpos,2,QTableWidgetItem(str(stock[2])))
            self.setItem(curpos,3,QTableWidgetItem(str(stock[3])))
            self.setItem(curpos,4,QTableWidgetItem(str(stock[4])))
            self.setItem(curpos,5,QTableWidgetItem(str(stock[5])))
            self.setItem(curpos,6,QTableWidgetItem(str(stock[6])))
            self.setItem(curpos,7,QTableWidgetItem(str(stock[7])))
            self.setItem(curpos,8,QTableWidgetItem(str(stock[8])))
        self.setHorizontalHeaderLabels(self.headers)
        cursor.close()


class ScanWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.list = ScanListTable()
        self.list.cellDoubleClicked.connect(self.goto_purchase)
        layout = QVBoxLayout()
        layout.addWidget(self.list)
        self.update_db_button = QPushButton("Update")
        self.export_db_button = QPushButton("Export")
        layout.addWidget(self.update_db_button)
        layout.addWidget(self.export_db_button)
        self.update_db_button.clicked.connect(self.refresh_db)
        self.export_db_button.clicked.connect(self.export_db)
        self.setLayout(layout)

    @Slot()
    def goto_purchase(self,row,column):
        print("Row:",row," Column:",column)
        self.buywindow = BuyWindow()
        self.buywindow.caller = self
        self.buywindow.resize(800,600)
        self.buywindow.ticker_text.setText(self.list.item(row,0).text())
        self.buywindow.pressed_update()
        self.buywindow.showMaximized()
        self.buywindow.activateWindow()

    @Slot()
    def export_db(self):
        self.list.export_csv()

    @Slot()
    def refresh_db(self):
        cursor = con.cursor()
        stocks = pd.read_csv('zacks_list.csv',header=0)
        end_date = datetime.now()
        days = 90
        start_date = end_date - timedelta(days=days)
        con.execute("delete from stocks")
        con.commit()
        start_time = datetime.now()
        for i in range(len(stocks.index)-1):
            if isinstance(stocks.iloc[i]['Ticker'], str):
                ticker = stocks.iloc[i]['Ticker'].upper()
                print("Testing ",ticker)
                candles = yf.download(ticker,start=start_date,end=end_date,interval='1d',prepost=False)
            else:
                continue

            if not candles.empty and len(candles.index)>3 and latest_price(ticker)>0.1:
                print("Got size sample ",len(candles.index))
                bear_score = 0
                vol_score = 0
                bounce_score = 0
                bear_steps = 0
                bounce_steps = 0
                endpos = -1
                stages = 0      # 0 - pullback, 1 - bear
                pullbackhigh = None
                pullbacklow = None
                pullbackswallow = None
                bearhigh = None
                bearlow = None
                while endpos>(len(candles.index)*-1)+2 and stages<2:
                    if stages == 0:
                        if clean_bull_movement(candles.iloc[endpos - 1],candles.iloc[endpos]) and green_candle(candles.iloc[endpos]):
                            bounce_steps += 1
                            if not pullbackhigh:
                                pullbackhigh = candles.iloc[endpos]['Close']
                        else:
                            if green_candle(candles.iloc[endpos]) and bounce_steps==0:
                                bounce_steps += 1
                                pullbackhigh = candles.iloc[endpos]['Close']
                            stages = 1
                            if pullbackhigh and not pullbacklow:
                                pullbacklow = candles.iloc[endpos]['Open']
                    elif stages == 1:
                        if clean_bear_movement(candles.iloc[endpos -1],candles.iloc[endpos]) and red_candle(candles.iloc[endpos]):
                            bear_steps += 1
                            if not bearlow:
                                bearlow = candles.iloc[endpos]['Close']
                        else:
                            stages = 2
                            if bearlow and not bearhigh:
                                bearhigh = candles.iloc[endpos]['Open']
                    if pullbackhigh and pullbackhigh > candles.iloc[endpos]['Close']:
                        if pullbackswallow:
                            pullbackswallow += 1
                        else:
                            pullbackswallow = 1
                    if bounce_steps>2 and stages<1:     # we don't want any extended bull run
                        stages = 1
                    endpos -= 1
                
                if bear_steps>0 and bearhigh and bearlow:
                    bear_score = (bearhigh - bearlow) / bear_steps
                if bounce_steps>0 and pullbackhigh and pullbacklow:
                    bounce_score = (pullbackhigh - pullbacklow) / bounce_steps
                    
                if bear_steps > 0:
                    end_vol = candles.iloc[-1:-5:-1]['Volume'].mean()
                    all_vol = candles['Volume'].mean()
                    vol_score = end_vol / all_vol

                    print("Found bear end for ",ticker," score of ",bear_score," end vol:",end_vol," all vol:",all_vol," vol score:",vol_score)
                    query = "insert into stocks (name,ticker,price,bear_score,bear_steps,vol_score,bounce_score,bounce_steps,pullbackswallow) values (:name,:ticker,:price,:bear_score,:bear_steps,:vol_score,:bounce_score,:bounce_steps,:pullbackswallow)"
                    con.execute(query,{
                        'name':stocks.iloc[i]['Company Name'],
                        'ticker':ticker,
                        'price':latest_price(ticker),
                        'bear_score':bear_score,
                        'bear_steps':bear_steps,
                        'vol_score':vol_score,
                        'bounce_score':bounce_score,
                        'bounce_steps':bounce_steps,
                        'pullbackswallow':pullbackswallow
                        })
                    con.commit()
        print("Done scanning")
        cursor.close()
        end_time = datetime.now()
        diff_time = end_time - start_time
        print("Took ", diff_time)
        self.list.update_list()
        dlg = QMessageBox(self)
        dlg.setWindowTitle("Scan complete")
        dlg.setText("Scan complete in " + str(diff_time) + " time")
        dlg.exec()

class TriggerListTable(QTableWidget):
    headers = ['Date','Ticker','Status','Type','Price','P&L','Close Date','Action']
    combo_selection = ['Active','Filled','Cancel']
    type_selection = ['Above','Below']
    ticker = None

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
        self.setHorizontalHeaderLabels(self.headers)
    
    def update_list(self):
        cursor = con.cursor()
        if self.ticker:
            print("Filter by:",self.ticker)
            trades = cursor.execute("select * from trigger where ticker=:ticker order by trade_date desc",{'ticker':self.ticker})
        else:
            trades = cursor.execute("select * from trigger order by trade_date desc")
        self.clear()
        self.setRowCount(0)
        i = 0
        self.row_id = []
        self.type_combo = []
        self.status_combo = []
        self.price_widget = []
        self.update_trigger_button = []
        for trade in trades:
            curpos = self.rowCount()
            self.row_id.append(trade[0])
            self.insertRow(curpos)
            self.setItem(curpos,0,QTableWidgetItem(trade[1]))
            self.setItem(curpos,1,QTableWidgetItem(trade[2]))
            cur_status_combo = QComboBox()
            cur_status_combo.addItems(self.combo_selection)
            cur_status_combo.setCurrentText(trade[3])
            self.status_combo.append(cur_status_combo)
            self.setCellWidget(curpos,2,self.status_combo[i])
            cur_type_combo = QComboBox()
            cur_type_combo.addItems(self.type_selection)
            cur_type_combo.setCurrentText(trade[4])
            self.type_combo.append(cur_type_combo)
            self.setCellWidget(curpos,3,self.type_combo[i])
            self.price_widget.append(QTableWidgetItem(str(trade[5])))
            self.setItem(curpos,4,self.price_widget[i])
            self.setItem(curpos,5,QTableWidgetItem(str(trade[6])))
            self.setItem(curpos,6,QTableWidgetItem(trade[7]))

            trigger_button = QPushButton("Update")
            trigger_button.clicked.connect(self.update_row)
            self.update_trigger_button.append(trigger_button)

            self.setCellWidget(curpos,7,self.update_trigger_button[i])
            i += 1
        self.setHorizontalHeaderLabels(self.headers)
        cursor.close()

    @Slot(int)
    def update_row(self):
        print("Will update row",self.row_id[self.currentRow()])
        cursor = con.cursor()
        data = {
            'price':float(self.price_widget[self.currentRow()].text()),
            'status':str(self.status_combo[self.currentRow()].currentText()),
            'type':str(self.type_combo[self.currentRow()].currentText()),
            'id':self.row_id[self.currentRow()]
        }
        print("Data to update:",data)
        cursor.execute("update trigger set price=:price,status=:status,trigger_type=:type where trigger_id=:id",data)
        con.commit()
        cursor.close()

class TriggerListWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.list = TriggerListTable()
        layout = QVBoxLayout(self)
        layout.addWidget(self.list)
        self.setLayout(layout)

    def create_trade_info_box(self):
        self._trade_info_group = QGroupBox("Buy")
        layout = QFormLayout()
        layout.addRow(QLabel("Trade Limit: "), self.trade_limit_label )
        layout.addRow(QLabel("Ticker: "), self.ticker_label )
        layout.addRow(QLabel("Setup: "), self.setup_label )
        layout.addRow(QLabel("Price: "), self.price_label )
        layout.addRow(QLabel("Stop Loss: "), self.stop_label )
        layout.addRow(QLabel("R1: "), self.r1_label ) 
        layout.addRow(QLabel("R2: "), self.r2_label )
        layout.addRow(QLabel("Amount: "), self.amount_label )
        self._trade_info_group.setLayout(layout)

    def update_list(self,ticker=None):
        if ticker:
            self.list.ticker = ticker
        self.list.update_list()

class TradeListTable(QTableWidget):
    headers = ['Date','Ticker','Setup','Price','Units','Loss Limit','R1','R2','P&L']
    def __init__(self):
        super().__init__()
        self.setColumnCount(len(self.headers))
        self.setAlternatingRowColors(True)
        self.update_list()
        self.cellDoubleClicked.connect(self.open_trigger)
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

    @Slot()
    def open_trigger(self):
        self.triggerwindow = TriggerListWindow()
        item = self.item(self.currentRow(),1)
        curticker = item.text()
        self.triggerwindow.update_list(curticker)
        self.triggerwindow.resize(800,600)
        self.triggerwindow.showMaximized()
        self.triggerwindow.activateWindow()

class TradeListWindow(QWidget):
    def __init__(self):
        super().__init__()
        connect_ib()

        self.list = TradeListTable()
        layout = QVBoxLayout(self)
        layout.addWidget(self.list)

        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.checkprice)
        self.timer.start(60000)

        actionrow = QHBoxLayout(self)
        self.ticker_text = QTextEdit("BBBY")
        self.ticker_text.setMaximumHeight(30)
        self.buy_button = QPushButton("Buy")
        self.scan_button = QPushButton("Scan")
        self.trigger_button = QPushButton("Trigger")
        actionrow.addWidget(self.ticker_text)
        actionrow.addWidget(self.buy_button)
        actionrow.addWidget(self.scan_button)
        actionrow.addWidget(self.trigger_button)
        self.buy_button.clicked.connect(self.open_buy)
        self.scan_button.clicked.connect(self.open_scan)
        self.trigger_button.clicked.connect(self.open_trigger)

        layout.addLayout(actionrow)
        self.setLayout(layout)
    
    @Slot()
    def checkprice(self):
        if current_ib.isConnected():
            curtime = datetime.now(newYorkTz)
            print("At New York:",curtime)
            print("At New York Hour:",curtime.hour)
            print("At New York Minute:",curtime.minute)
            print("Minute test:",(curtime.hour==9 and curtime.minute>45)," Hour test:",curtime.hour>9)
            open_counter = (curtime.hour>9 or (curtime.hour==9 and curtime.minute>45)) and curtime.hour<16
            selloff_time = curtime.hour>=15 and curtime.minute>=40
            print("Open counter:",open_counter," Sell off time:",selloff_time)
            print("Checking prices")
            cursor = con.cursor()
            cur_pos = current_ib.positions()
            for cps in cur_pos:  # Loop over stock we own according to ib
                ticker = cps[1].localSymbol
                amount = cps[2]
                print("Checking price for ",ticker)
                price = latest_price(ticker)
                triggers = cursor.execute("select * from trigger where status='Active' and ticker=:ticker and trigger_type=:trigger_type order by price",
                {'ticker':ticker,'trigger_type':'Above'})
                trigger = triggers.fetchone()
                if trigger:
                    print("Comparing above price ",price," to trigger ",trigger[5])
                    trigger_price = float(trigger[5])
                    if price>trigger_price:
                        print("Price ",price," is higher than trigger ",trigger_price)
                        divide = len(triggers.fetchall())
                        if divide==0:
                            divide = 1
                        to_sell = math.floor(amount/divide)
                        stock = ib.Stock(ticker,'SMART','USD')
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
                            cursor.execute("update trigger set status='Filled',close_date=:close_date where trigger_id=:id",
                                {
                                    'id':trigger[0],
                                    'close_date':datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                })
                            if divide==1:
                                cursor.execute("update trigger set status='Cancel',close_date=:close_date where ticker=:ticker and status='Active'",
                                    {
                                        'ticker':ticker,
                                        'close_date':datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                    })
                                prev_trade = cursor.execute("select buy_price,amount from trades where status='New' and ticker=:ticker",{'ticker':ticker}).fetchone()
                                cursor.execute("update trades set status='Complete',sell_price=:sell_price,pnl=:pnl,close_date=:close_date where ticker=:ticker and status='New'",
                                    {
                                        'ticker':ticker,
                                        'sell_price':price,
                                        'close_date':datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                        'pnl': prev_trade[0]*prev_trade[1] - price*prev_trade[1]
                                    })
                            status = True
                        else:
                            status = False
                triggers = cursor.execute("select * from trigger where status='Active' and ticker=:ticker and trigger_type=:trigger_type order by price desc",
                {'ticker':ticker,'trigger_type':'Below'})
                trigger = triggers.fetchone()
                if trigger:
                    print("Comparing below price ",price," to trigger ",trigger[5])
                    trigger_price = float(trigger[5])
                    if price<trigger_price:
                        print("Price ",price," is lower than trigger ",trigger_price)
                        divide = len(triggers.fetchall())
                        if divide==0:
                            divide = 1
                        to_sell = math.floor(amount/divide)
                        stock = ib.Stock(ticker,'SMART','USD')
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
                            cursor.execute("update trigger set status='Filled',close_date=:close_date where trigger_id=:id",
                                {
                                    'id':trigger[0],
                                    'close_date':datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                })
                            if divide==1:
                                cursor.execute("update trigger set status='Cancel',close_date=:close_date where ticker=:ticker and status='Active'",
                                    {
                                        'ticker':ticker,
                                        'close_date':datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                    })
                                prev_trade = cursor.execute("select buy_price,amount from trades where status='New' and ticker=:ticker",{'ticker':ticker}).fetchone()
                                cursor.execute("update trades set status='Complete',sell_price=:sell_price,pnl=:pnl,close_date=:close_date where ticker=:ticker and status='New'",
                                    {
                                        'ticker':ticker,
                                        'sell_price':price,
                                        'close_date':datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                        'pnl': prev_trade[0]*prev_trade[1] - price*prev_trade[1] 
                                    })
                            status = True
                        else:
                            status = False
                if selloff_time:
                    if amount>0:
                        to_sell = amount
                        stock = ib.Stock(ticker,'SMART','USD')
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
                            cursor.execute("update trigger set status='Cancel',close_date=:close_date where ticker=:ticker and status='Active'",
                                {
                                    'ticker':ticker,
                                    'close_date':datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                })
                            prev_trade = cursor.execute("select buy_price,amount from trades where status='New' and ticker=:ticker",
                                {
                                    'ticker':ticker
                                }).fetchone()
                            cursor.execute("update trades set status='Complete',sell_price=:sell_price,pnl=:pnl,close_date=:close_date where ticker=:ticker and status='New'",
                                {
                                    'ticker':ticker,
                                    'sell_price':price,
                                    'close_date':datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                    'pnl': prev_trade[0]*prev_trade[1] - price*prev_trade[1] 
                                })
                            status = True
                        else:
                            status = False
                con.commit()
            cursor.close()

    @Slot()
    def open_scan(self):
        self.scanwindow = ScanWindow()
        self.scanwindow.caller = self
        self.scanwindow.resize(800,600)
        self.scanwindow.showMaximized()
        self.scanwindow.activateWindow()

    @Slot()
    def open_trigger(self):
        self.scanwindow = TriggerListWindow()
        self.scanwindow.caller = self
        self.scanwindow.resize(800,600)
        self.scanwindow.showMaximized()
        self.scanwindow.activateWindow()

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
        self.trade_limit_text = QLineEdit("150")
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
        data = {
            "trade_date":datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "ticker":self.ticker_text.text().upper(),
            "setup":self.setup_text.toPlainText(),
            "buy_price":self.price_text.text(),
            "sell_price":None,
            "amount":self.amount_text.text(),
            "stop_loss":self.stop_text.text(),
            "r1":self.r1_text.text(),
            "r2":self.r2_text.text(),
            "total":self.total_amount_label.text(),
            "status":"New",
            "pnl":None
        }
        print("Query:",query)
        print("Data:",data)
        cursor.execute(query,data)
        con.commit()
        query = "insert into trigger(trade_date,ticker,status,trigger_type,price) values (:trade_date,:ticker,:status,:trigger_type,:price)"
        data = [
            {
                "trade_date":datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "ticker":self.ticker_text.text().upper(),
                "status":"Active",
                "trigger_type":"Above",
                "price":float(self.r1_text.text())
            },
            {
                "trade_date":datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "ticker":self.ticker_text.text().upper(),
                "status":"Active",
                "trigger_type":"Below",
                "price":float(self.stop_text.text())
            }
        ]
        if len(self.r2_text.text()):
            data.append({
                "trade_date":datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "ticker":self.ticker_text.text().upper(),
                "status":"Active",
                "trigger_type":"Above",
                "price":float(self.r2_text.text())
            })
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
            amount = self.amount
            if len(self.r2_text.text()):
                amount = math.floor(amount/2)
            total_r1 = (amount * float(self.r1_text.text())) # - self.total_amount
            pnl_r1 = (amount * float(self.r1_text.text())) - self.total_amount
            self.total_r1_label.setText(str(total_r1))
            self.pnl_r1_label.setText(str(pnl_r1))
        else:
            self.total_r1_label.setText("0")
            self.pnl_r1_label.setText("0")

        if len(self.r2_text.text()):
            amount = self.amount
            if len(self.r1_text.text()):
                amount = math.floor(amount/2)
            total_r2 = (amount * float(self.r2_text.text())) # - self.total_amount
            pnl_r2 = (amount * float(self.r1_text.text())) + (amount * float(self.r2_text.text())) - self.total_amount
            self.total_r2_label.setText(str(total_r2))
            self.pnl_r2_label.setText(str(pnl_r2))
        else:
            self.total_r2_label.setText("0")
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
        self.total_r1_label = QLabel("float")
        self.total_r2_label = QLabel("float")
        layout.addRow(QLabel("Float: "), self.stockfloat_label)
        layout.addRow(QLabel("24h Volume: "), self.volume24h_label)
        layout.addRow(QLabel("Levels: "), self.levels_label)
        layout.addRow(QLabel("Size Mean: "), self.size_mean_label)
        layout.addRow(QLabel("Total Amount: "), self.total_amount_label)
        layout.addRow(QLabel("Stop Loss P&L: "), self.pnl_stop_label)
        layout.addRow(QLabel("R1 Total: "), self.total_r1_label)
        layout.addRow(QLabel("R2 Total: "), self.total_r2_label)
        layout.addRow(QLabel("R1 P&L: "), self.pnl_r1_label)
        layout.addRow(QLabel("R2 P&L: "), self.pnl_r2_label)
        self._info_box_group.setLayout(layout)

    @Slot()
    def pressed_update(self):
        self.update_chart()

    def update_chart(self):
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
        lastcandle = candles.iloc[-1]
        self.price = latest_price(self.ticker_text.text().upper())
        self.size_mean_label.setText(str(size_mean) + " ----- " + str(size_mean+self.price))
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
        acmeSeries = QCandlestickSeries()
        acmeSeries.setName(self.ticker_text.text())
        acmeSeries.setIncreasingColor(QColor(Qt.green))
        acmeSeries.setDecreasingColor(QColor(Qt.red))

        volumeSeries = QBarSeries()
        vset = QBarSet('Volume')

        categories = []
        for idx in range(len(candles)):
            candle = candles.iloc[idx]
            candlestickSet = QCandlestickSet(candle['Open'],candle['High'],candle['Low'],candle['Close'],QDateTime(candle['timestamp']).toMSecsSinceEpoch())
            acmeSeries.append(candlestickSet)
            categories.append(QDateTime(candle['timestamp']).toMSecsSinceEpoch())
            vset.append(candle['Volume'])

        volumeSeries.append(vset)

        self.chart.removeAllSeries()
        self.chart.addSeries(acmeSeries)
        self.chart.createDefaultAxes()
        self.chart.axisX().setLabelsAngle(-90)
        self.chart.axisY().setMax(ymax * 1.1)
        self.chart.axisY().setMin(ymin * 0.9)

        self.volchart.removeAllSeries()
        self.volchart.addSeries(volumeSeries)
        self.volchart.createDefaultAxes()
    
    def create_chart(self):
        self.ticker_text.setText("BBBY")
        self._chart_group = QGroupBox("Chart")
        self.chart = QChart()
        self.volchart = QChart()
        self.update_chart()
        self.chart.setTitle("Historical Data")
        self.chart.setAnimationOptions(QChart.SeriesAnimations)
        self.chart.legend().setVisible(True)
        self.chart.legend().setAlignment(Qt.AlignBottom)
        self.volchart.setTitle("Volume Data")
        self.volchart.setAnimationOptions(QChart.SeriesAnimations)
        self.volchart.legend().setVisible(True)
        self.volchart.legend().setAlignment(Qt.AlignBottom)
        layout = QVBoxLayout()
        self.chartview = QChartView(self.chart)
        self.chartview.setRenderHint(QPainter.Antialiasing)
        self.volchartview = QChartView(self.volchart)
        self.volchartview.setRenderHint(QPainter.Antialiasing)
        tab = QTabWidget()
        tab.addTab(self.chartview,'Chart')
        tab.addTab(self.volchartview,'Volume')
        layout.addWidget(tab)
        self._chart_group.setLayout(layout)

if __name__=="__main__":
    update_table()
    app = QApplication([])
    widget = TradeListWindow()
    widget.resize(800,600)
    widget.showMaximized()

    sys.exit(app.exec())
