from dataclasses import dataclass
from datetime import datetime


@dataclass
class Item:
    title: str
    attrs: dict
    body: str
    url: str
    thumbnail: str
    price: float
    published: datetime
    floor: str
    address: str
    size: float
    roomCnt: str
    isPrivate: bool
    pricePerSqm: float


def getOpt(d: dict, key: str, default=None):
    return d.get(key, [default])[0]


def parseItems(js) -> list[Item]:
    items: list[Item] = []
    for item in js:
        title = item["description"]
        attrs = {
            attr["name"]: attr["values"] for attr in item["attributes"]["attribute"]
        }

        body = attrs["BODY_DYN"]
        url = "https://www.willhaben.at/iad/" + attrs["SEO_URL"][0]
        price = float(attrs["PRICE"][0])
        published = datetime.fromtimestamp(int(attrs["PUBLISHED"][0]) / 1000)
        floor = getOpt(attrs, "FLOOR")
        address = getOpt(attrs, "ADDRESS")
        size = float(getOpt(attrs, "ESTATE_SIZE/LIVING_AREA", -1))
        roomCnt = getOpt(attrs, "NUMBER_OF_ROOMS")
        isPrivate = True if getOpt(attrs, "ISPRIVATE") == "1" else False
        pricePerSqm = price / size
        thumbnail = item["advertImageList"]["advertImage"][0]["mainImageUrl"]

        items.append(
            Item(
                title,
                attrs,
                body,
                url,
                thumbnail,
                price,
                published,
                floor,
                address,
                size,
                roomCnt,
                isPrivate,
                pricePerSqm,
            )
        )

    return sorted(items, key=lambda i: i.published, reverse=True)
