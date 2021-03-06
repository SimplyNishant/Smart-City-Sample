#!/usr/bin/python3

from db_ingest import DBIngest
import paho.mqtt.client as mqtt
from threading import Thread, Condition
import json
import time
import sys
import os

mqtthost = os.environ["MQTTHOST"]
scenario = os.environ["SCENARIO"]
dbhost = os.environ["DBHOST"]
office = list(map(float, os.environ["OFFICE"].split(",")))

class MQTT2DB(object):
    def __init__(self, algorithm):
        super(MQTT2DB,self).__init__()
        self._mqtt=mqtt.Client("feeder_" + algorithm)
        self._db=DBIngest(host=dbhost, index="analytics", office=office)
        self._cache=[]
        self._cond=Condition()

    def loop(self, topic):
        self._stop=False
        Thread(target=self.todb).start()

        while True:
            try:
                self._mqtt.connect(mqtthost)
                break
            except Exception as e:
                print("Exception: "+str(e), flush=True)
                time.sleep(10)

        self._mqtt.on_message = self.on_message
        self._mqtt.subscribe(topic)
        self._mqtt.loop_forever()

    def _add1(self, item=None):
        self._cond.acquire()
        if item: self._cache.append(item)
        self._cond.notify()
        self._cond.release()

    def stop(self):
        self._mqtt.disconnect()
        self._stop=True
        self._add1()

    def on_message(self, client, userdata, message):
        try:
            r=json.loads(str(message.payload.decode("utf-8", "ignore")))
            r.update(r["tags"])
            del r["tags"]
            if "real_base" not in r: r["real_base"]=0
            r["time"]=int((r["real_base"]+r["timestamp"])/1000000)

            if "objects" in r and scenario == "traffic": r["nobjects"]=int(len(r["objects"]))
            if "objects" in r and scenario == "stadium": r["count"]={"people":len(r["objects"])}
        except Exception as e:
            print("Exception: "+str(e), flush=True)

        self._add1(r)

    def todb(self):
        while not self._stop:
            self._cond.acquire()
            self._cond.wait()
            bulk=self._cache
            self._cache=[]
            self._cond.release()

            try:
                self._db.ingest_bulk(bulk)
            except Exception as e:
                print("Exception: "+str(e), flush=True)

