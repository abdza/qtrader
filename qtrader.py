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
    cursor.execute("create table if not exists stocks(stocks_id INTEGER PRIMARY KEY,name,ticker,price,bear_score,vol_score,bounce_score,bear_steps,bounce_steps,pullbackswallow,opt_size,volume)")
    con.commit()
    cursor.close()

def find_levels(candles):
    levels = []
    size_mean = np.mean(candles['high']-candles['low'])
    for i in range(2,len(candles)-2):
        if is_support(candles,i):
            val = candles['low'][i]
            if is_far_from_levels(val,size_mean,levels):
                levels.append(val)
        elif is_resistance(candles,i):
            val = candles['high'][i]
            if is_far_from_levels(val,size_mean,levels):
                levels.append(val)
    return size_mean,levels

def is_support(candles,i):     # i is at lowest low
    cond1 = candles['low'][i] <= candles['low'][i-1]
    cond2 = candles['low'][i] <= candles['low'][i+1]
    cond3 = candles['low'][i+1] < candles['low'][i+2]
    cond4 = candles['low'][i-1] < candles['low'][i-2]
    return cond1 and cond2 and cond3 and cond4

def is_resistance(candles,i):  # i is at highest high
    cond1 = candles['high'][i] >= candles['high'][i-1]
    cond2 = candles['high'][i] >= candles['high'][i+1]
    cond3 = candles['high'][i+1] > candles['high'][i+2]
    cond4 = candles['high'][i-1] > candles['high'][i-2]
    return cond1 and cond2 and cond3 and cond4

def highest_low(candles,i):  # i is at highest low
    cond1 = candles['low'][i] >= candles['low'][i-1]
    cond2 = candles['low'][i] >= candles['low'][i+1]
    cond3 = candles['low'][i+1] > candles['low'][i+2]
    cond4 = candles['low'][i-1] > candles['low'][i-2]
    return cond1 and cond2 and cond3 and cond4

def lowest_high(candles,i):  # i is at lowest high
    cond1 = candles['high'][i] <= candles['high'][i-1]
    cond2 = candles['high'][i] <= candles['high'][i+1]
    cond3 = candles['high'][i+1] < candles['high'][i+2]
    cond4 = candles['high'][i-1] < candles['high'][i-2]
    return cond1 and cond2 and cond3 and cond4

def is_far_from_levels(val,size_mean,levels):
    return np.sum([abs(val-x) < size_mean for x in levels]) == 0

def candle_size(candle):
    return candle['high'] - candle['low']

def red_candle(candle):
    if candle['open'] > candle['close']:
        return True
    elif candle['open'] < candle['close']:
        return False
    else:
        if candle['high'] - candle['close'] > candle['close'] - candle['low']:
            return True
        else:
            return False

def green_candle(candle):
    return not red_candle(candle)

def clean_bear_movement(first,second):
    score = 0
    if second['high']<=first['high']:
        score += 1
    if second['low']<=first['low']:
        score += 1
    if second['open']<=first['open']:
        score += 1
    if second['close']<=first['close']:
        score += 1
    return score

def clean_bull_movement(first,second):
    score = 0
    if second['high']>=first['high']:
        score += 1
    if second['low']>=first['low']:
        score += 1
    if second['open']>=first['open']:
        score += 1
    if second['close']>=first['close']:
        score += 1
    return score


class ScanListTable(QTableWidget):
    headers = ['Ticker','Name','Price','Opt Size','Volume','Bear Score','Bear Steps','Bounce Score','Bounce Steps','Vol Score','Swallow']
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
        header.setSectionResizeMode(9,QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(10,QHeaderView.ResizeMode.Stretch)
        self.setHorizontalHeaderLabels(self.headers)

    def export_csv(self):
        cursor = con.cursor()
        stocks = cursor.execute("select ticker,name,price,opt_size,volume,bear_score,bear_steps,bounce_score,bounce_steps,vol_score,pullbackswallow from stocks where bear_steps > 0 and bounce_steps > 0 order by opt_size desc,volume desc,bear_steps desc, bear_score desc, vol_score  desc, bounce_steps desc, bounce_score desc")
        with open('shortlist_' + datetime.now().strftime("%Y_%m_%d_%H_%M_%S") + '.csv','w') as f:
            writer = csv.writer(f)
            writer.writerow(self.headers + ['Latest close','Colour','Gap','Candle Size','Gap Size'])
            for stock in stocks.fetchall():
                end_date = datetime.now()
                days = 5
                start_date = end_date - timedelta(days=days)
                try:
                    ticker = yq.Ticker(stock[1])
                    candles = ticker.history(start=start_date,end=end_date)
                    latest = candles.iloc[-1]
                    secondlatest = candles.iloc[-2]
                    color = 'Green'
                    if red_candle(latest):
                        color = 'Red'
                    gap = 'Up'
                    if latest['open']<secondlatest['close']:
                        gap = 'Down'
                    gapsize = latest['open'] - secondlatest['close']
                    writer.writerow(stock + tuple([latest['close'],color,gap,candle_size(latest),gapsize]))
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
        stocks = cursor.execute("select name,ticker,price,bear_score,bear_steps,bounce_score,bounce_steps,vol_score,pullbackswallow,opt_size,volume from stocks where bear_steps > 0 and bounce_steps > 0 order by opt_size desc, bear_steps desc, bear_score desc, vol_score  desc, bounce_steps desc, bounce_score desc")
        self.clear()
        self.setRowCount(0)
        for stock in stocks:
            curpos = self.rowCount()
            self.insertRow(curpos)
            tickertxt = stock[1]
            if tickertxt:
                tickertxt = tickertxt.strip()
            self.setItem(curpos,0,QTableWidgetItem(tickertxt))
            self.setItem(curpos,1,QTableWidgetItem(stock[0]))
            self.setItem(curpos,2,QTableWidgetItem(str(stock[2])))
            self.setItem(curpos,3,QTableWidgetItem(str(stock[9])))
            self.setItem(curpos,4,QTableWidgetItem(str(stock[10])))
            self.setItem(curpos,5,QTableWidgetItem(str(stock[3])))
            self.setItem(curpos,6,QTableWidgetItem(str(stock[4])))
            self.setItem(curpos,7,QTableWidgetItem(str(stock[5])))
            self.setItem(curpos,8,QTableWidgetItem(str(stock[6])))
            self.setItem(curpos,9,QTableWidgetItem(str(stock[7])))
            self.setItem(curpos,10,QTableWidgetItem(str(stock[8])))
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
        self.buywindow.ticker_text.setText(self.list.item(row,0).text().strip())
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
        days = 120
        start_date = end_date - timedelta(days=days)
        con.execute("delete from stocks")
        con.commit()
        start_time = datetime.now()
        for i in range(len(stocks.index)-1):
            if isinstance(stocks.iloc[i]['Ticker'], str):
                ticker = stocks.iloc[i]['Ticker'].upper()
                print("Testing ",ticker)
                dticker = yq.Ticker(ticker)
                candles = dticker.history(start=start_date,end=end_date)
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
                opt_size = 0
                while endpos>(len(candles.index)*-1)+2 and stages<2:
                    if stages == 0:
                        if clean_bull_movement(candles.iloc[endpos - 1],candles.iloc[endpos])>2 and green_candle(candles.iloc[endpos]):
                            bounce_steps += 1
                            if not pullbackhigh:
                                pullbackhigh = candles.iloc[endpos]['close']
                        else:
                            if green_candle(candles.iloc[endpos]) and bounce_steps==0:
                                bounce_steps += 1
                                pullbackhigh = candles.iloc[endpos]['close']
                            stages = 1
                            if pullbackhigh and not pullbacklow:
                                pullbacklow = candles.iloc[endpos]['open']
                    elif stages == 1:
                        if clean_bear_movement(candles.iloc[endpos -1],candles.iloc[endpos])>2 and red_candle(candles.iloc[endpos]):
                            bear_steps += 1
                            if not bearlow:
                                bearlow = candles.iloc[endpos]['close']
                        else:
                            stages = 2
                            if bearlow and not bearhigh:
                                bearhigh = candles.iloc[endpos]['open']
                    if pullbackhigh and pullbackhigh > candles.iloc[endpos]['close']:
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
                    size_mean,levels = find_levels(candles)
                    levels.sort()
                    end_vol = candles.iloc[-1:-5:-1]['volume'].mean()
                    all_vol = candles['volume'].mean()
                    vol_score = end_vol / all_vol
                    curprice = latest_price(ticker)
                    if len(levels)>0 and curprice<levels[-1]:
                        l = 0
                        while l<len(levels)-1 and curprice>levels[l]:
                            l+=1
                        opt_size = levels[l] - curprice

                    print("Found bear end for ",ticker," score of ",bear_score," end vol:",end_vol," all vol:",all_vol," vol score:",vol_score)
                    query = "insert into stocks (name,ticker,price,bear_score,bear_steps,vol_score,bounce_score,bounce_steps,pullbackswallow,opt_size,volume) values (:name,:ticker,:price,:bear_score,:bear_steps,:vol_score,:bounce_score,:bounce_steps,:pullbackswallow,:opt_size,:volume)"
                    con.execute(query,{
                        'name':stocks.iloc[i]['Company Name'],
                        'ticker':ticker,
                        'price':curprice,
                        'bear_score':bear_score,
                        'bear_steps':bear_steps,
                        'vol_score':vol_score,
                        'bounce_score':bounce_score,
                        'bounce_steps':bounce_steps,
                        'pullbackswallow':pullbackswallow,
                        'opt_size':opt_size,
                        'volume':dticker.summary_detail[ticker]['volume'],
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
    headers = ['Date','Ticker','Status','Type','Price','P&L','close Date','Action']
    combo_selection = ['Active','Filled','Cancel','Submitted']
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
        self.refresh_button = QPushButton("Refresh")
        actionrow.addWidget(self.ticker_text)
        actionrow.addWidget(self.buy_button)
        actionrow.addWidget(self.scan_button)
        actionrow.addWidget(self.trigger_button)
        actionrow.addWidget(self.refresh_button)
        self.buy_button.clicked.connect(self.open_buy)
        self.scan_button.clicked.connect(self.open_scan)
        self.trigger_button.clicked.connect(self.open_trigger)
        self.refresh_button.clicked.connect(self.refresh_list)

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
            print("open counter:",open_counter," Sell off time:",selloff_time)
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
                        order.action = 'SELL'
                        order.orderType = 'TRAIL'
                        order.totalQuantity = float(to_sell)
                        order.trailingPercent = 0.5
                        order.transmit = True
                        sell = current_ib.placeOrder(stock,order)
                        current_ib.sleep(5)
                        print("Trail status:",sell.orderStatus.status)
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
                                print('prev trade:',prev_trade)
                                cursor.execute("update trades set status='Complete',sell_price=:sell_price,pnl=:pnl,close_date=:close_date where ticker=:ticker and status='New'",
                                    {
                                        'ticker':ticker,
                                        'sell_price':price,
                                        'close_date':datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                        'pnl': float(prev_trade[0])*float(prev_trade[1]) - price*float(prev_trade[1])
                                    })
                            status = True
                        elif sell.orderStatus.status=='PreSubmitted':
                            cursor.execute("update trigger set status='Submitted',close_date=:close_date where trigger_id=:id",
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
                                print('prev trade:',prev_trade)
                                cursor.execute("update trades set status='Complete',sell_price=:sell_price,pnl=:pnl,close_date=:close_date where ticker=:ticker and status='New'",
                                    {
                                        'ticker':ticker,
                                        'sell_price':price,
                                        'close_date':datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                        'pnl': float(prev_trade[0])*float(prev_trade[1]) - price*float(prev_trade[1])
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
                                        'pnl': float(prev_trade[0])*float(prev_trade[1]) - price*float(prev_trade[1])
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
    def refresh_list(self):
        self.list.update_list()

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
        self.place_order = QCheckBox("Place Order")
        layout.addRow(QLabel("Trade Limit: "), self.trade_limit_text )
        layout.addRow(QLabel("Ticker: "), tickerbox )
        layout.addRow(QLabel("Setup: "), self.setup_text )
        layout.addRow(QLabel("Price: "), self.price_text )
        layout.addRow(QLabel("Stop Loss: "), self.stop_text )
        layout.addRow(QLabel("R1: "), self.r1_text ) 
        layout.addRow(QLabel("R2: "), self.r2_text )
        layout.addRow(QLabel("Amount: "), self.amount_text )
        layout.addRow(self.place_order,self.buy_button)
        self._buy_form_group.setLayout(layout)

    @Slot()
    def buy_action(self):
        if current_ib.isConnected():
            print("Connected to IB")
            nextId = current_ib.client.getReqId()
            print("Next ID:",nextId)
            stock = ib.Stock(self.ticker_text.text(),'SMART','USD')
            order = ib.Order()
            order.orderId = nextId
            order.action = 'BUY'
            order.orderType = 'LMT'
            order.totalQuantity = float(self.amount_text.text())
            order.lmtPrice = float(self.price_text.text())
            if self.place_order.isChecked():
                order.transmit = False
            else:
                order.transmit = True

            dps = str(current_ib.reqContractDetails(stock)[0].minTick + 1)[::-1].find('.') - 1
            order.lmtPrice = round(order.lmtPrice + current_ib.reqContractDetails(stock)[0].minTick * 2,dps)
            bought = current_ib.placeOrder(stock,order)

            if self.place_order.isChecked():
                takeProfit = ib.Order()
                takeProfit.orderId = order.orderId + 1
                takeProfit.action = 'SELL'
                takeProfit.orderType = 'LMT'
                takeProfit.totalQuantity = float(self.amount_text.text())
                takeProfit.lmtPrice = float(self.r1_text.text())
                takeProfit.parentId = nextId
                takeProfit.transmit = False
                takeProfit.tif = 'GTC'
                bought2 = current_ib.placeOrder(stock,takeProfit)

                stopLoss = ib.Order()
                stopLoss.orderId = order.orderId + 2
                stopLoss.action = 'SELL'
                stopLoss.orderType = 'STP'
                #Stop trigger price
                stopLoss.auxPrice = float(self.stop_text.text())
                stopLoss.totalQuantity = float(self.amount_text.text())
                stopLoss.parentId = nextId
                #In this case, the low side order will be the last child being sent. Therefore, it needs to set this attribute to True
                #to activate all its predecessors
                stopLoss.transmit = True
                stopLoss.tif = 'GTC'
                bought3 = current_ib.placeOrder(stock,stopLoss)

            current_ib.sleep(5)
            if bought.orderStatus.status=='Filled' or bought.orderStatus.status=='Submitted':
                print("Placed order for",self.ticker_text.text())
                status = True
            else:
                print("Not able to place order")
                status = False
        else:
            print("Not connected to IB")
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
        savestatus = 'Active'
        if self.place_order.isChecked():
            savestatus = 'Submitted'

        query = "insert into trigger(trade_date,ticker,status,trigger_type,price) values (:trade_date,:ticker,:status,:trigger_type,:price)"
        data = [
            {
                "trade_date":datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "ticker":self.ticker_text.text().upper(),
                "status":savestatus,
                "trigger_type":"Above",
                "price":float(self.r1_text.text())
            },
            {
                "trade_date":datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "ticker":self.ticker_text.text().upper(),
                "status":savestatus,
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
            total_r1 = (amount * float(self.r1_text.text())) 
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
            total_r2 = (amount * float(self.r2_text.text())) 
            pnl_r2 = (amount * float(self.r1_text.text())) + (amount * float(self.r2_text.text())) - self.total_amount
            self.total_r2_label.setText(str(total_r2))
            self.pnl_r2_label.setText(str(pnl_r2))
        else:
            self.total_r2_label.setText("0")
            self.pnl_r2_label.setText("0")

    def create_info_box(self):
        self._info_box_group = QGroupBox("Info")
        layout = QFormLayout()
        self.marketcap_label = QLabel("float")
        self.volume24h_label = QLabel("float")
        self.yearhigh_label = QLabel("float")
        self.yearlow_label = QLabel("float")
        self.levels_label = QLabel("float")
        self.size_mean_label = QLabel("float")
        self.total_amount_label = QLabel("float")
        self.pnl_stop_label = QLabel("float")
        self.pnl_r1_label = QLabel("float")
        self.pnl_r2_label = QLabel("float")
        self.total_r1_label = QLabel("float")
        self.total_r2_label = QLabel("float")
        layout.addRow(QLabel("Market Cap: "), self.marketcap_label)
        layout.addRow(QLabel("24h volume: "), self.volume24h_label)
        layout.addRow(QLabel("52 Week high: "), self.yearhigh_label)
        layout.addRow(QLabel("52 Week low: "), self.yearlow_label)
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
        candles = pd.DataFrame()
        levels = []
        tickertxt = self.ticker_text.text().strip().upper()
        print("Tickertxt:",tickertxt)
        try:
            ticker = yq.Ticker(tickertxt)
            print("Ticker:",ticker.summary_detail)
            self.marketcap_label.setText(str(ticker.summary_detail[tickertxt]['marketCap']))
            self.volume24h_label.setText(str(ticker.summary_detail[tickertxt]['volume']))
            self.yearhigh_label.setText(str(ticker.summary_detail[tickertxt]['fiftyTwoWeekHigh']))
            self.yearlow_label.setText(str(ticker.summary_detail[tickertxt]['fiftyTwoWeekLow']))
            candles = ticker.history(start=start_date,end=end_date)
            candles['timestamp'] = [ pd.Timestamp(dt[1]) for dt in candles.index.values ]
            ymin = candles['low'].min()
            ymax = candles['high'].max()
            size_mean,levels = find_levels(candles)
            levels.sort()
            self.levels_label.setText(','.join([ str(x) for x in levels]))
            lastcandle = candles.iloc[-1]
            self.price = latest_price(self.ticker_text.text().upper())
            self.size_mean_label.setText(str(size_mean) + " ----- " + str(size_mean+self.price))
            curend = -2
            endloop = len(candles) * -1
            while curend>endloop and candles.iloc[curend]['low']>self.price:
                curend -= 1
            if curend>endloop:
                self.stop_text.setText(str(round(candles.iloc[curend]['low'],4)))
            else:
                self.stop_text.setText(str(round(lastcandle['low'],4)))
            self.price_text.setText(str(round(self.price,4)))
            self.update_price()
            self.r2_text.setText("")
            if len(levels)>0 and self.price<levels[-1]:
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
            vset = QBarSet('volume')

            categories = []
            for idx in range(len(candles)):
                candle = candles.iloc[idx]
                candlestickSet = QCandlestickSet(candle['open'],candle['high'],candle['low'],candle['close'],QDateTime(candle['timestamp']).toMSecsSinceEpoch())
                acmeSeries.append(candlestickSet)
                categories.append(QDateTime(candle['timestamp']).toMSecsSinceEpoch())
                vset.append(candle['volume'])

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
        except Exception as exp:
            print("Exception for |","|","| (",tickertxt,") : ",exp)
            candles = pd.DataFrame()

    
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
        self.volchart.setTitle("volume Data")
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
        tab.addTab(self.volchartview,'volume')
        layout.addWidget(tab)
        self._chart_group.setLayout(layout)

if __name__=="__main__":
    update_table()
    app = QApplication([])
    widget = TradeListWindow()
    widget.resize(800,600)
    widget.showMaximized()

    sys.exit(app.exec())
