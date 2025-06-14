import requests
import json
from datetime import datetime
from dataclasses import dataclass

@dataclass
class Apartment:
    title: str
    attrs: dict
    body: str
    url: str
    price: float
    published: datetime
    floor: str
    address: str
    size: float
    roomCnt: str
    isPrivate: bool
    pricePerSqm: float


SCRIPT_START = '<script id="__NEXT_DATA__" type="application/json">'
SCIRIPT_END = "</script>"

url = "https://www.willhaben.at/iad/immobilien/mietwohnungen/mietwohnung-angebote?areaId=117223&areaId=117224&areaId=117225&areaId=117226&areaId=117227&areaId=117228&areaId=117229&areaId=117230&areaId=117231&areaId=117233&areaId=117234&areaId=117235&areaId=117236&areaId=117237&areaId=117238&areaId=117239&areaId=117240&areaId=117241&areaId=117242&NO_OF_ROOMS_BUCKET=4X4&NO_OF_ROOMS_BUCKET=2X2&NO_OF_ROOMS_BUCKET=3X3&sort=1&rows=30&isNavigation=true&sfId=4ac15ce2-b27e-46b7-9945-013cb4858b52&PROPERTY_TYPE=110&PROPERTY_TYPE=105&PROPERTY_TYPE=111&PROPERTY_TYPE=100&PROPERTY_TYPE=101&PROPERTY_TYPE=102&PROPERTY_TYPE=3&PROPERTY_TYPE=16&page=1&PRICE_FROM=0&ESTATE_SIZE/LIVING_AREA_FROM=45&PRICE_TO=950"

resp = requests.get(url)

if resp.status_code != 200:
    print(f"Invalid status code: {resp.status_code}")
    print(url)
    exit(1)


def getOpt(d: dict, key: str):
    return attrs.get(key, [None])[0]


scriptStart = resp.content.find(str.encode(SCRIPT_START))
scriptEnd = resp.content.find(str.encode(SCIRIPT_END), scriptStart)

js = json.loads(resp.content[scriptStart + len(SCRIPT_START) : scriptEnd])
js = js["props"]["pageProps"]["searchResult"]["advertSummaryList"]["advertSummary"]

apartments: list[Apartment] = []

for item in js:
    title = item["description"]
    attrs = {attr["name"]: attr["values"] for attr in item["attributes"]["attribute"]}

    body = attrs["BODY_DYN"]
    url = "https://www.willhaben.at/iad/" + attrs["SEO_URL"][0]
    price = float(attrs["PRICE"][0])
    published = datetime.fromtimestamp(int(attrs["PUBLISHED"][0]) / 1000)
    floor = getOpt(attrs, "FLOOR")
    address = getOpt(attrs, "ADDRESS")
    size = float(attrs["ESTATE_SIZE/LIVING_AREA"][0])
    roomCnt = getOpt(attrs, "NUMBER_OF_ROOMS")
    isPrivate = True if getOpt(attrs, "ISPRIVATE") == "1" else False
    pricePerSqm = price / size

    apartments.append(Apartment(title, attrs, body, url, price, published, floor, address, size, roomCnt, isPrivate, pricePerSqm))


for a in apartments:
    print(a.published)
