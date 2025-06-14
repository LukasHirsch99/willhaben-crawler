from enum import Enum
from dataclasses import dataclass
import json
import sys
import os
from datetime import datetime
import time
from collections import namedtuple
import csv

import requests
from requests_file import FileAdapter

from bs4 import BeautifulSoup

import base64
from urllib.parse import urlparse
import socket
import re
import fnmatch
import ast

import myemail
from item import Item, parseItems


class Operator(Enum):
    IN = "in"
    NOT_IN = "not in"
    LIKE = "like"
    NOT_LIKE = "not like"
    MATCH = "match"
    NOT_MATCH = "not match"
    GT = ">"
    GTE = ">="
    LT = "<"
    LTE = "<="


try:
    ltsFile = open("lastTimeStamp.txt", "r")
    content = ltsFile.readline()
    lastTimeStamp = datetime.fromtimestamp(float(content))
    ltsFile.close()
except Exception:
    lastTimeStamp = datetime.fromtimestamp(0)


SCRIPT_START = '<script id="__NEXT_DATA__" type="application/json">'
SCIRIPT_END = "</script>"


def CompressString(s):
    s = s.strip()
    s = s.replace("\r", "")
    s = s.replace("\n", "")
    # while '  ' in s:
    #  s = s.replace('  ', ' ')
    s = " ".join(s.split())
    return s


def GetPriceWillhaben(script):
    ss = script.string.split(";")[1].split(",")[1]
    encs = ss[ss.find("(") + 2 : ss.find(")") - 1]
    s = base64.b64decode(encs)
    soup = BeautifulSoup(s, "html.parser")
    e = soup.find("span", {"class": "info-2-price"})
    if e is None:
        return ""
    # 2.500,-
    p = e.text.strip()
    if p.find(",") >= 0:
        sl = p.split(",")
        p = sl[0]
    if p.find(".") >= 0:
        p = p.replace(".", "")
    return p


def GetText(cfg, tag):
    tn = cfg.get("tagname", True)
    if "attrs" in cfg.attrs:
        attrDict = ast.literal_eval(cfg["attrs"])
        foundTags = tag.find_all(tn, attrDict)
    else:
        foundTags = tag.find_all(tn)

    text = ""
    if len(foundTags) == 0:
        return text

    valueSrc = cfg.get("valueSrc", "text")
    if valueSrc == "text":
        for ft in foundTags:
            if len(text) > 0:
                text += " "
            text += CompressString(ft.text)
    elif valueSrc == "attribute":
        attributeName = cfg.get("attributename")
        if attributeName is not None:
            ft = foundTags[0]
            text = ft.get(attributeName)
    elif valueSrc == "GetPriceWillhaben":
        script = foundTags[0]
        text = GetPriceWillhaben(script)
    return text


def listsTohtml(data, withHeader=True):
    html = "<table border=1>"
    for i, row in enumerate(data):
        if withHeader and i == 0:
            tag = "th"
        else:
            tag = "td"
        tds = "".join("<{}>{}</{}>".format(tag, cell, tag) for cell in row)
        html += "<tr>{}</tr>".format(tds)
    html += "</table>"
    return html


class Filter:
    oper: Operator
    propValue: str

    def __init__(self, filterCfg) -> None:
        self.prop = filterCfg.get("prop")
        operStr = filterCfg.get("oper")
        self.compValue = filterCfg.get("compValue")
        self.valueType = filterCfg.get("valueType")
        if self.prop is None:
            raise ValueError("prop is not set")
        if operStr is None:
            raise ValueError("oper is not set")
        if self.compValue is None:
            raise ValueError("compValue is not set")

        self.oper: Operator = Operator(operStr.casefold())

        if self.oper is None:
            raise ValueError(f"operator {operStr} not supported.")

    def handleInLikeMatch(self) -> bool:
        propValue = self.propValue.casefold()
        sl = self.compValue.split(",")
        sl = [s.strip().casefold() for s in sl]
        for s in sl:
            if self.oper == Operator.IN or self.oper == Operator.NOT_IN:
                if propValue.find(s) >= 0:
                    return self.oper == Operator.IN

            elif self.oper == Operator.LIKE or self.oper == Operator.NOT_LIKE:
                if fnmatch.fnmatch(propValue, self.compValue):
                    return self.oper == Operator.LIKE

                if re.search(self.compValue, propValue, re.IGNORECASE) is not None:
                    return self.oper == Operator.MATCH

        return self.oper.name.find("NOT") != -1

    def handleComparison(self) -> bool:
        if self.valueType == "int":
            propValue = int(self.propValue)
            self.compValue = int(self.compValue)

        elif self.valueType == "float":
            if self.propValue.find(",") >= 0:
                self.propValue = self.propValue.replace(",", ".")
            propValue = float(self.propValue)

            if self.compValue.find(",") >= 0:
                self.compValue = self.compValue.replace(",", ".")
            self.compValue = float(self.compValue)

        if self.oper == Operator.GT:
            return propValue > self.compValue
        elif self.oper == Operator.GTE:
            return propValue >= self.compValue
        if self.oper == Operator.LT:
            return propValue < self.compValue
        else:
            return propValue <= self.compValue

    def evaluate(self, item: Item) -> bool:
        self.propValue = item.__getattribute__(self.prop)

        if (
            self.oper == Operator.IN
            or self.oper == Operator.NOT_IN
            or self.oper == Operator.LIKE
            or self.oper == Operator.NOT_LIKE
            or self.oper == Operator.MATCH
            or self.oper == Operator.NOT_MATCH
        ):
            return self.handleInLikeMatch()
        elif (
            self.oper == Operator.GT
            or self.oper == Operator.GTE
            or self.oper == Operator.LT
            or self.oper == Operator.LTE
        ):
            return self.handleComparison()


class Agent:
    def __init__(self, cfg):
        self.cfg = cfg
        self.name = self.cfg.get("name")
        self.url = None
        self.foundNew = 0

    def BuildUrl(self, s):
        u = urlparse(s)
        if u.scheme != "" and u.netloc != "":
            return s
        myUrl = urlparse(self.url)
        validUrl = myUrl.scheme
        validUrl += "://"
        validUrl += myUrl.netloc
        validUrl += s
        return validUrl

    def Evaluate(self) -> list[Item]:
        global lastTimeStamp
        print("Evaluate " + self.name)
        res: list[Item] = []
        if self.cfg.name != "Agent":
            return res
        if "url" in self.cfg.attrs:
            self.url = self.cfg["url"]

        if "file" in self.cfg.attrs:
            fileName = self.cfg["file"]

        # test
        if socket.gethostname().upper() == "X2236PCHIRSMAN":
            sess = requests.Session()
            sess.mount("file://", FileAdapter())
            resp = sess.get("file:///c:/temp/wh_t1.html")
        else:
            if self.url is None:
                print("E: url not set")
                return res
            resp = requests.get(self.url)

        print((str)(datetime.now()) + " request.get len=" + str(len(resp.content)))

        # save response to file
        if "saveresponse" in self.cfg.attrs and self.cfg["saveresponse"] == "True":
            fileName = r"C:\temp\WC_Resp_Agent_" + self.name + ".html"
            try:
                fh = open(fileName, "w+", encoding="utf-8")
                try:
                    fh.write(resp.text)
                except Exception:
                    fh.write(str(resp.content))
                fh.close()
            except IOError:
                print("E: can't create file " + fileName)

        if resp.status_code != 200:
            print("Invalid status code")
            print(self.url)
            print(resp.status_code)

        scriptStart = resp.content.find(str.encode(SCRIPT_START))
        scriptEnd = resp.content.find(str.encode(SCIRIPT_END), scriptStart)

        js = json.loads(resp.content[scriptStart + len(SCRIPT_START) : scriptEnd])
        js = js["props"]["pageProps"]["searchResult"]["advertSummaryList"][
            "advertSummary"
        ]

        items: list[Item] = parseItems(js)

        runs = RunHist()
        runs.Load()
        self.foundNew = 0

        searchl = self.cfg.find_all("Search")

        newlastTimeStamp = lastTimeStamp
        for sea in searchl:
            searchName = sea.get("name", "noName")
            print("do search", searchName)

            for item in items:
                if item.published < lastTimeStamp:
                    break

                filters = sea.find_all("Filter")
                for filter in filters:
                    f = Filter(filter)
                    if not f.evaluate(item):
                        break
                else:
                    if item.published > newlastTimeStamp:
                        newlastTimeStamp = item.published
                    res.append(item)
                    self.foundNew += 1

            if newlastTimeStamp > lastTimeStamp:
                lastTimeStamp = newlastTimeStamp
                ltsFile = open("lastTimeStamp.txt", "w")
                ltsFile.write(str(lastTimeStamp.timestamp()))
                ltsFile.close()

        print(
            (str)(datetime.now()) + " Agent " + self.name + " res len=" + str(len(res))
        )
        return res


class RunHist:
    def __init__(self):
        self.hl = []
        self.added = 0
        self.MyRow = namedtuple("LastRun", "agentName, seaName, maxId")

    def Clear(self):
        self.hl.clear()
        self.added = 0

    def Add(self, agentName, seaName, idMax):
        r = self.MyRow._make([agentName, seaName, idMax])
        self.hl.append(r)
        self.added += 1

    def Save(self):
        with open(r"c:\temp\WCRuns.csv", "w+", newline="") as csvfile:
            csvw = csv.writer(
                csvfile, delimiter=",", quotechar='"', quoting=csv.QUOTE_MINIMAL
            )
            csvw.writerow(self.MyRow._fields)
            for r in self.hl:
                csvw.writerow(r)

    def Load(self):
        self.Clear()
        fileName = r"c:\temp\WCRuns.csv"
        if not os.path.isfile(fileName):
            return
        with open(fileName, "r", newline="") as csvfile:
            csvr = csv.reader(
                csvfile, delimiter=",", quotechar='"', quoting=csv.QUOTE_MINIMAL
            )
            isFirst = True
            for r in csvr:
                if isFirst:
                    isFirst = False
                    continue
                mr = self.MyRow._make(r)
                self.hl.append(mr)

    def AddIfNew(self, agentName, seaName, idMax):
        if len(self.hl) > 0:
            foundMax = "0"
            for i, r in enumerate(self.hl):
                if r.agentName != agentName:
                    continue
                if r.seaName != seaName:
                    continue
                if r.maxId > foundMax:
                    foundMax = r.maxId
            if idMax <= foundMax:
                return False
        self.Add(agentName, seaName, idMax)
        return True

    def FindMax(self, agentName, seaName):
        foundMax = "0"
        for r in self.hl:
            if r.agentName != agentName:
                continue
            if r.seaName != seaName:
                continue
            if r.maxId > foundMax:
                foundMax = r.maxId
        return foundMax


class WebCrawler:
    def __init__(self, cfg):
        self.cfg = cfg
        self.agents = self.cfg.find("Agents")
        if self.agents is None:
            # print('E: invalif config, agents missing')
            raise ValueError("E: invalif config, agents missing")
        self.agentsList = self.agents.find_all("Agent")
        if len(self.agentsList) == 0:
            # print('E: invalif config, agent missing')
            raise ValueError("E: invalif config, agent missing")

    def Crawl(self) -> None:
        resList: list[str] = []
        combineResults = self.agents.get("combineresults", "False") == "True"
        mailCfg = None

        for a in self.agentsList:
            agent = Agent(a)
            res = agent.Evaluate()
            if len(res) == 0:
                continue

            cvtRes = CvtResult(self.cfg, agent, res)
            # combine results
            for row in cvtRes:
                resList.append(row)

        if mailCfg is not None and len(resList) > 0 and combineResults:
            mail = myemail.Email(mailCfg)
            mail.Send(resList)
            print(f"sent mail to: {mailCfg["to"]}")


def CvtResult(cfg, agent: Agent, res: list[Item]) -> str | list[str]:
    rows: list[list[str]] = []
    ret: str | list[list[str]] = rows

    resultName = agent.cfg.get("result")
    if resultName is None:
        return ""

    resTab = cfg.find("ResultTable", {"name": resultName})
    if resTab is None:
        return ""

    format = resTab.get("format")
    asHtml = format == "html"
    fileName = resTab.get("fileName")

    cl = resTab.find_all("ColumnVal")

    rows.append([str(c["name"]) for c in cl])

    for item in res:
        row = []

        for c in cl:
            prop = c["prop"]
            propValue = item.__getattribute__(prop)

            isLink = c.get("isLink")
            isImage = c.get("isImage")

            if isLink is not None:
                linkText = c.get("linkText", "Link")
                text = "<a href='{}'><div>{}</div></a>".format(propValue, linkText)

            elif isImage is not None:
                altText = c.get("altText", "Picture")
                imageLink = c.find("ImageLink")
                if imageLink is not None:
                    text = "<a href='{}'><img src='{}' alt='{}'/></a>".format(
                        item.url, propValue, altText
                    )
                else:
                    text = "<img src='{}' alt='{}'/>".format(propValue, altText)
            else:
                text = propValue

            # print(colName + ' = ' + text)
            row.append(text)

        if len(row) > 0:
            rows.append(row)

    if asHtml:
        html = listsTohtml(rows)
        ret = html
        # print(html)

    if fileName is not None:
        try:
            fh = open(fileName, "w+")
            fh.write(str(ret))
            fh.close()
        except IOError:
            print("E: can't create file " + fileName)

    return ret


# this is where all begins...

print((str)(datetime.now()) + " start crawl ...")

cfgFileName = "config/config.xml"
if not os.path.isfile(cfgFileName):
    cfgFileName = "config.xml"
    if not os.path.isfile(cfgFileName):
        path = os.path.dirname(sys.argv[0])
        cfgFileName = path + "/config/config.xml"
        if not os.path.isfile(cfgFileName):
            cfgFileName = path + "/config.xml"
            if not os.path.isfile(cfgFileName):
                print("E: can't find config file '" + cfgFileName)
                exit()

cfh = open(cfgFileName, "r")
cfg = BeautifulSoup(cfh, "xml")

scheduling = cfg.find("Scheduling")
cycleTime = -1
if scheduling is not None:
    cycleTime = int(scheduling.get("cycleTime", "-1"))

wc = WebCrawler(cfg)
wc.Crawl()

if cycleTime > 0:
    while True:
        time.sleep(cycleTime)
        wc.Crawl()

print((str)(datetime.now()) + " done")
