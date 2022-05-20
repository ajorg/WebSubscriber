## Complete
- [ ] Renew subscriptions
- [ ] Unsubscribe
- [x] Forward content to `target`
- [ ] Clean up function order
- [ ] Improve logging

## Future / Maybe
- [ ] One callback URL (and subscription) per topic
- [ ] CloudFormation
- [ ] NanoID for callback URL
- [ ] Are the secrets "cryptographically random"?

To have one URL per topic we'd need to generate a secret and use it to create an HMAC
