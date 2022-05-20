import hmac
import json
from base64 import urlsafe_b64encode as encode
from html.parser import HTMLParser
from os import environ, urandom
from urllib.error import HTTPError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen
from xml.etree.ElementTree import XMLParser

import boto3

HEADERS = {"User-Agent": "WebSubscriber/0.0 (AWS Lambda) ajorg 2022"}
LAMBDA_URL = environ.get("LAMBDA_URL")
TABLE_NAME = environ.get("TABLE_NAME", "WebSubscriber")
TARGET = environ.get("TARGET")

DDB = boto3.client("dynamodb")
SNS = boto3.client("sns")


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
        if tag in ("link", "{http://www.w3.org/2005/Atom}link"):
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


def subscribe(uid, secret, topic, hub):
    query = {
        "hub.mode": "subscribe",
        "hub.topic": topic,
        "hub.callback": urljoin(LAMBDA_URL, f"callback/{uid}"),
        "hub.secret": secret,
    }
    data = urlencode(query).encode()
    # Redirects are not handled for POST
    request = Request(hub, data, headers=HEADERS, method="POST")
    try:
        with urlopen(request) as response:
            print(response.status)
    except HTTPError as e:
        if e.code in (301, 302, 307, 308):
            print(f"HTTPError: {e.code}")
            request.full_url = e.headers.get("Location")
            with urlopen(request) as response:
                print(response.status)
    return


def verify(uid, mode, topic, challenge, lease_seconds, time_epoch):
    time = time_epoch // 1000
    item = DDB.get_item(
        TableName=TABLE_NAME,
        Key={"uid": {"S": uid}},
        AttributesToGet=["topic", "pending-subscribe", "pending-unsubscribe"],
    )
    _topic = item.get("Item", {}).get("topic", {}).get("S")
    pending = item.get("Item", {}).get(f"pending-{mode}", {}).get("BOOL", False)

    if mode in ("subscribe", "unsubscribe") and topic == _topic and pending:
        if mode == "subscribe":
            expires = time + int(lease_seconds)
        else:
            expires = time
        response = {
            "statusCode": 200,
            "headers": {"content-type": "text/plain"},
            "body": challenge,
        }
        DDB.update_item(
            TableName=TABLE_NAME,
            Key={"uid": {"S": uid}},
            UpdateExpression="SET #p = :p, #e = :e",
            ExpressionAttributeNames={"#p": f"pending-{mode}", "#e": "expires"},
            ExpressionAttributeValues={
                ":p": {"BOOL": False},
                ":e": {"N": str(expires)},
            },
        )
    else:
        response = {"statusCode": 404}
    return response


def http_handler(method, path, parameters, body, headers, time_epoch):
    response = {"statusCode": 400}

    if path.startswith("/callback/"):
        uid = path.split("/")[-1]
        if method == "POST":
            response = receive(uid=uid, headers=headers, body=body)
        elif method == "GET":
            mode = parameters.get("hub.mode")
            if mode in ("subscribe", "unsubscribe"):
                response = verify(
                    uid=uid,
                    mode=mode,
                    topic=parameters["hub.topic"],
                    challenge=parameters["hub.challenge"],
                    lease_seconds=parameters.get("hub.lease_seconds", 0),
                    time_epoch=time_epoch,
                )

    return response


def distribute(body, target):
    SNS.publish(TopicArn=target, Message=body)
    print(json.dumps({"target": target}))


def receive(uid, headers, body):
    response = {"statusCode": 400}
    item = DDB.get_item(
        TableName=TABLE_NAME,
        Key={"uid": {"S": uid}},
        AttributesToGet=["secret", "target"],
    )
    secret = item.get("Item", {}).get("secret", {}).get("S")
    target = item.get("Item", {}).get("target", {}).get("S")

    method, signature = headers.get("x-hub-signature", "=").split("=", 1)
    if method in ("sha1", "sha256", "sha384", "sha512"):
        h = hmac.new(key=secret.encode(), msg=body.encode(), digestmod=method)
        if hmac.compare_digest(h.hexdigest(), signature):
            distribute(body, target)
            response = {"statusCode": 200}
            print(json.dumps({"uid": uid, "method": method, "signature": signature}))
        else:
            print(
                json.dumps(
                    {
                        "error": "Invalid signature",
                        "uid": uid,
                        "signature": signature,
                        "method": method,
                        "should-be": h.hexdigest(),
                    }
                )
            )
    return response


def lambda_handler(event, context):
    print(json.dumps(dict(environ), sort_keys=True))
    print(json.dumps(event, sort_keys=True))

    response = {"statusCode": 400}

    # Raw invocation
    if "sub.topic" in event and "sub.mode" in event:
        uid = encode(urandom(12)).decode().rstrip("=")
        secret = encode(urandom(24)).decode().rstrip("=")

        mode = event["sub.mode"]
        if mode not in ("subscribe",):
            return {"statusCode": 400}

        links = discover(event["sub.topic"])
        topic = links.get("self")
        target = event.get("sub.target", TARGET)

        DDB.update_item(
            TableName=TABLE_NAME,
            Key={"uid": {"S": uid}},
            UpdateExpression="SET #t = :t, #T = :T, #p = :p, #s = :s",
            ExpressionAttributeNames={
                "#t": "topic",
                "#T": "target",
                "#p": f"pending-{mode}",
                "#s": "secret",
            },
            ExpressionAttributeValues={
                ":t": {"S": topic},
                ":T": {"S": target},
                ":p": {"BOOL": True},
                ":s": {"S": secret},
            },
        )
        subscribe(
            uid=uid,
            secret=secret,
            topic=links.get("self"),
            hub=links.get("hub"),
        )
        return True

    # Webhook invocation
    if "http" in event.get("requestContext", {}):
        response = http_handler(
            method=event["requestContext"]["http"]["method"],
            path=event["requestContext"]["http"]["path"],
            parameters=event.get("queryStringParameters", {}),
            body=event.get("body"),
            headers=event.get("headers", {}),
            time_epoch=event["requestContext"]["timeEpoch"],
        )
        print(json.dumps(response, sort_keys=True))

    return response
