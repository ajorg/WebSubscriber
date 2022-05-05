import json
from html.parser import HTMLParser
from os import environ
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from xml.etree.ElementTree import XMLParser

import boto3

HEADERS = {"User-Agent": "WebSubscriber/0.0 (AWS Lambda) ajorg 2022"}
LAMBDA_URL = environ.get("LAMBDA_URL")
TABLE_NAME = environ.get("TABLE_NAME", "WebSubscriber")
DDB = boto3.client("dynamodb")


class HTMLLinksParser(HTMLParser):
    links = {}
    __in_head = False

    def handle_starttag(self, tag, attrs):
        if tag == "head":
            self.__in_head = True

        if self.__in_head and tag == "link":
            _attrs = dict(attrs)
            if "rel" in _attrs and "href" in _attrs:
                for rel in _attrs["rel"].split(" "):
                    self.links[rel] = _attrs["href"]

    def handle_endtag(self, tag):
        if tag == "head":
            self.__in_head = False


class AtomLinksParser:
    links = {}

    def start(self, tag, attrs):
        print(f"start: {tag}")
        if tag in ("link", "{http://www.w3.org/2005/Atom}link"):
            print(f"link! {attrs}")
            _attrs = dict(attrs)
            if "rel" in _attrs and "href" in _attrs:
                for rel in _attrs["rel"].split(" "):
                    self.links[rel] = _attrs["href"]

    def end(self, tag):
        pass

    def data(self, data):
        pass

    def close(self):
        pass


# SNS = boto3.client("sns")
def parse_link_header(link_header):
    # <https://websub.rocks/blog/100/4C0exJVR7SZfRD2aNRDF/hub>; rel="hub"
    # TODO: Could have multiple links per header?
    link_, param_ = link_header.split(";", 1)
    link = link_.strip("< >")
    # TODO: Could have multiple parameters per link
    _, rel_ = param_.split("=", 1)
    if _.strip() != "rel":
        raise KeyError(link_header)
    rel = rel_.strip('" ')
    return link, rel


def parse_html(response):
    html_parser = HTMLLinksParser()
    while True:
        chunk = response.read(16384)
        if not chunk:
            break
        # TODO: Use Content-Encoding to decode?
        html_parser.feed(chunk.decode())
    return html_parser.links


def parse_atom(response):
    atom_parser = AtomLinksParser()
    xml_parser = XMLParser(target=atom_parser)
    while True:
        chunk = response.read(16384)
        if not chunk:
            break
        # TODO: Use Content-Encoding to decode?
        xml_parser.feed(chunk.decode())
    return atom_parser.links


def discover(url):
    """Discovers the hub and topic URLs for the provided URL"""
    links = {}
    # Redirects are handled for GET and HEAD requests
    request = Request(url, headers=HEADERS, method="HEAD")
    with urlopen(request) as response:
        # TODO: Consider status, redirect, etc.
        for link_header in response.headers.get_all("Link") or ():
            link, rel = parse_link_header(link_header)
            links[rel] = link
    if "hub" not in links or "self" not in links:
        request = Request(url, headers=HEADERS, method="GET")
        with urlopen(request) as response:
            content_type = response.headers.get_content_type()
            if content_type in ("text/xml", "application/atom+xml"):
                links = parse_atom(response)
            elif content_type in ("text/html", "application/xhtml+xml"):
                links = parse_html(response)

    print(json.dumps({"discover": links}))
    return links


def subscribe(topic, hub):
    query = {
        "hub.mode": "subscribe",
        "hub.topic": topic,
        # TODO: Use a specific callback path per subscription
        "hub.callback": LAMBDA_URL,
    }
    data = urlencode(query).encode()
    # Redirects are not handled for POST
    request = Request(hub, data, headers=HEADERS, method="POST")
    try:
        with urlopen(request) as response:
            print(response.status)
    except HTTPError as e:
        if e.code in (301, 302, 307, 308):
            request.full_url = e.headers.get("Location")
            with urlopen(request) as response:
                print(response.status)
    return


def verify(mode, topic, challenge, lease_seconds):
    item = DDB.get_item(
        TableName=TABLE_NAME,
        Key={"topic": {"S": topic}},
        AttributesToGet=["pending-subscribe", "pending-unsubscribe"],
    )
    print(json.dumps(item))
    pending = item.get("Item", {}).get(f"pending-{mode}", {}).get("BOOL", False)

    if mode in ("subscribe", "unsubscribe") and pending:
        response = {
            "statusCode": 200,
            "headers": {"content-type": "text/plain"},
            "body": challenge,
        }
        DDB.update_item(
            TableName=TABLE_NAME,
            Key={"topic": {"S": topic}},
            UpdateExpression="SET #p = :p",
            ExpressionAttributeNames={"#p": f"pending-{mode}"},
            ExpressionAttributeValues={":p": {"BOOL": False}},
        )
    else:
        response = {"statusCode": 404}
    return response


def lambda_handler(event, context):
    print(json.dumps(dict(environ), sort_keys=True))
    print(json.dumps(event, sort_keys=True))

    target = environ.get("TARGET_ARN")

    if "sub.topic" in event and "sub.mode" in event:
        mode = event["sub.mode"]
        if mode not in ("subscribe",):
            return {"statusCode": 400}
        links = discover(event["sub.topic"])
        topic = links.get("self")
        DDB.update_item(
            TableName=TABLE_NAME,
            Key={"topic": {"S": topic}},
            UpdateExpression="SET #p = :p",
            ExpressionAttributeNames={"#p": f"pending-{mode}"},
            ExpressionAttributeValues={":p": {"BOOL": True}},
        )
        subscribe(links.get("self"), links.get("hub"))

    body = None
    if "requestContext" in event:
        if "queryStringParameters" in event:
            q = event["queryStringParameters"]
            if "hub.mode" in q:
                return verify(
                    q["hub.mode"],
                    q["hub.topic"],
                    q["hub.challenge"],
                    q.get("hub.lease_seconds"),
                )

    print(json.dumps({"body": body}, sort_keys=True))

    return {"statusCode": 200, "headers": {"content-type": "text/plain"}, "body": body}
