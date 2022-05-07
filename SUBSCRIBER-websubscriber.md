This file is a template implementation report for WebSub subscribers. Copy this file to a new .md file and change the name to `SUBSCRIBER-project-name.md`, your project name (lowercase with hyphens between words). Fill out the information based on the details of your implementation. It's okay to not check all the boxes, we are more interested in knowing how much of the spec is implemented than getting everyone to tick every box. When you are finished, submit a pull request or link to your file in a [new issue](https://github.com/w3c/websub/issues).

For items that have a number next to the checkbox, the number corresponds with the test number on websub.rocks. You can use that tool to check whether you support the feature properly. To mark a statement as true, add an x between the brackets, e.g. [x]. If the statement does not apply to your implementation, use [na] and add a sentence explaining why it does not apply.

Delete the section above when filling out your copy of this file.

# WebSubscriber for AWS

> just a hobby, won't be big and professional

Implementation Home Page URL: https://github.com/ajorg/<TBD>

Source code repo URL(s) (optional): https://github.com/ajorg/<TBD>
* [x] 100% open source implementation

Programming Language(s): Python 3 (standard library only) using AWS Lambda

Developer(s): [Andrew Jorgensen](https://andrew.jorgensenfamily.us)

Answers are:
* [x] Confirmed via websub.rocks (for applicable results)
* [x] All results are self-reported

## Discovery

* [x] 100: HTTP header discovery - discovers the hub and self URLs from HTTP headers
* [x] 101: HTML tag discovery - discovers the hub and self URLs from the HTML `<link>` tags
* [x] 102: Atom feed discovery - discovers the hub and self URLs from the XML `<link>` tags
* [x] 103: RSS feed discovery - discovers the hub and self URLs from the XML `<atom:link>` tags
* [x] 104: Discovery priority - prioritizes the hub and self in HTTP headers over the links in the body

## Subscription

* [x] 1xx: Successfully creates a subscription
* [x] 200: Subscribing to a URL that reports a different rel=self
* [x] 201: Subscribing to a topic URL that sends an HTTP 302 temporary redirect
* [x] 202: Subscribing to a topic URL that sends an HTTP 301 permanent redirect
* [x] 203: Subscribing to a hub that sends a 302 temporary redirect
* [x] 204: Subscribing to a hub that sends a 301 permanent redirect
* [x] 205: Rejects a verification request with an invalid topic URL
* [x] 1xx: Requests a subscription using a secret (optional)
  * Please select the signature method(s) that the subscriber recognizes. All methods listed below are currently acceptable for the hub to choose:
  * [x] sha1
  * [x] sha256
  * [x] sha384
  * [x] sha512
* [ ] 1xx: Requests a subscription with a specific `lease_seconds` (optional, hub may ignore)
* [x] Callback URL is unique per subscription (should)
* [x] Callback URL is an unguessable URL (should)
* [ ] 1xx: Sends an unsubscription request

## Distribution

* [x] 300: Returns HTTP 2xx when the notification payload is delivered
* [x] 1xx: Verifies a valid signature for authenticated distribution
* [x] 301: Rejects a distribution request with an invalid signature
* [x] 302: Rejects a distribution request with no signature when the subscription was made with a secret

(1xx denotes that you can can use any of the 100-104 tests to confirm this feature)
