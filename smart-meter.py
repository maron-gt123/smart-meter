#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import serial
import configparser
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

# シリアルポートデバイス名
serialPortDev = '/dev/ttyUSB_power'

# 瞬時電力計測値取得コマンドフレーム
echonetLiteFrame = b'\x10\x81\x00\x01\x05\xFF\x01\x02\x88\x01\x62\x01\xE7\x00'

# 設定情報読み出し
inifile = configparser.ConfigParser()
#inifile.read('./root/meter/SmartMeter.ini', 'utf-8')
inifile.read('/root/meter/SmartMeter.ini', 'utf-8')
Broute_id = inifile.get('settings', 'broute_id')
Broute_pw = inifile.get('settings', 'broute_pw')
Channel = inifile.get('settings', 'channel')
PanId = inifile.get('settings', 'panid')
Address = inifile.get('settings', 'address')
INFLUXDB_URL = inifile.get('settings', 'INFLUXDB_URL')
INFLUXDB_TOKEN = inifile.get('settings', 'INFLUXDB_TOKEN')
INFLUXDB_ORG = inifile.get('settings', 'INFLUXDB_ORG')
INFLUXDB_BUCKET = inifile.get('settings', 'INFLUXDB_BUCKET')

# InfluxDBの接続
client = InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG)
write_api = client.write_api(write_options=SYNCHRONOUS)

# シリアルポート初期化
ser = serial.Serial(serialPortDev, 115200)  # シリアルポートオープン
ser.timeout = 2  # シリアル通信のタイムアウトを設定

# Bルート認証パスワード設定
ser.write(str.encode("SKSETPWD C " + Broute_pw + "\r\n"))
ser.readline()  # エコーバック
ser.readline()  # 成功ならOKを返す

# Bルート認証ID設定
ser.write(str.encode("SKSETRBID " + Broute_id + "\r\n"))
ser.readline()  # エコーバック
ser.readline()  # 成功ならOKを返す

# Channel設定
ser.write(str.encode("SKSREG S2 " + Channel + "\r\n"))
ser.readline()  # エコーバック
ser.readline()  # 成功ならOKを返す

# PanID設定
ser.write(str.encode("SKSREG S3 " + PanId + "\r\n"))
ser.readline()  # エコーバック
ser.readline()  # 成功ならOKを返す

# PANA 接続シーケンス
ser.write(str.encode("SKJOIN " + Address + "\r\n"))
ser.readline()  # エコーバック
ser.readline()  # 成功ならOKを返す

# PANA 接続完了待ち
bConnected = False
while not bConnected:
    line = ser.readline().decode(encoding='utf-8')
    if line.startswith("EVENT 24"):
        print("PANA 接続失敗")
        sys.exit()  # 接続失敗した時は終了
    elif line.startswith("EVENT 25"):
        print('PANA 接続成功')
        bConnected = True

ser.readline()  # インスタンスリストダミーリード

# コマンド送信
command = "SKSENDTO 1 {0} 0E1A 1 {1:04X} ".format(Address, len(echonetLiteFrame))
ser.write(str.encode(command) + echonetLiteFrame)

# コマンド受信
ser.readline()  # エコーバック
ser.readline()  # EVENT 21
ser.readline()  # 成功ならOKを返す

# 返信データ取得
Data = ser.readline().decode(encoding='utf-8')

# データチェック
if Data.startswith("ERXUDP"):
    cols = Data.strip().split(' ')
    res = cols[8]  # UDP受信データ部分
    seoj = res[8:8 + 6]
    ESV = res[20:20 + 2]
    # スマートメーター(028801)から来た応答(72)なら
    if seoj == "028801" and ESV == "72":
        EPC = res[24:24 + 2]
        # 瞬時電力計測値(E7)なら
        if EPC == "E7":
            hexPower = Data[-8:]  # 最後の4バイトが瞬時電力計測値
            intPower = int(hexPower, 16)
            print(u"瞬時電力計測値:{0}[W]".format(intPower))


            # InfluxDBにデータを書き込み
            point = Point("power").field("weight", intPower)
            write_api.write(bucket=INFLUXDB_BUCKET, org=INFLUXDB_ORG, record=point)

# ガード処理
ser.close()
