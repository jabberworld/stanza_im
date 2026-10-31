# OMEMO device aliases

- **Namespace:** `urn:xmpp:omemo:aliases:0`
- **Node:** `urn:xmpp:omemo:aliases:0`
- **Transport:** XEP-0060 publish-subscribe (private PEP node on the account's
  bare JID)
- **Access model:** `whitelist`
- **Item id:** `current`
- **Owner:** Stanza IM

## Purpose

OMEMO device ids are opaque. A user-assigned display name (for example
`Laptop` or `Phone`) is useful on every client of the same account. This node
stores that name set so another client can show the same labels after login.

The node is display metadata only. It never affects trust, encryption or
device selection.

## Payload

```xml
<omemo-aliases xmlns='urn:xmpp:omemo:aliases:0'>
  <device jid='alice@example.com'
          id='123456789'
          alias='Laptop'
          last_seen='1700000000'/>
  <device jid='alice@example.com'
          id='987654321'
          alias='Phone'/>
</omemo-aliases>
```

| Attribute | Required | Meaning |
|-----------|----------|---------|
| `jid` | yes | Bare JID of the device owner. |
| `id` | yes | OMEMO device id, decimal. |
| `alias` | no | Display name, UTF-8. An absent or empty value means no stored name. |
| `last_seen` | no | Unix time in seconds when the device was last observed. |

The `(jid, id)` pair is the key. A payload with an empty `jid` or `id` is
invalid and must be ignored.

## Publish options

The item is published with a `publish-options` data form:

```xml
<publish-options>
  <x xmlns='jabber:x:data' type='submit'>
    <field var='FORM_TYPE' type='hidden'>
      <value>http://jabber.org/protocol/pubsub#publish-options</value>
    </field>
    <field var='pubsub#persist_items'><value>true</value></field>
    <field var='pubsub#max_items'><value>1</value></field>
    <field var='pubsub#send_last_published_item'><value>never</value></field>
    <field var='pubsub#access_model'><value>whitelist</value></field>
  </x>
</publish-options>
```

The whole set is one item. A publish replaces the previous set.

## Fetch

```xml
<iq type='get' to='alice@example.com'>
  <pubsub xmlns='http://jabber.org/protocol/pubsub'>
    <items node='urn:xmpp:omemo:aliases:0'/>
  </pubsub>
</iq>
```

Rules:

- `item-not-found` means the node does not exist yet; treat it as an empty set.
- Any other error (timeout, transport error, forbidden, …) means the server
  state is **unknown**. Do not treat it as an empty set and do not publish an
  empty replacement.
- An empty `<items/>` also means an empty set.

No `+notify` subscription is required for the login fetch. Clients fetch the
node on login and after enabling alias synchronization.

## Live updates

A client should subscribe its own resource to the node so another of the
account's resources receives a PEP notification after a publish:

```xml
<iq type='set'>
  <pubsub xmlns='http://jabber.org/protocol/pubsub'>
    <subscribe node='urn:xmpp:omemo:aliases:0'
               jid='alice@example.com'/>
  </pubsub>
</iq>
```

An incoming notification is accepted only when its `from` (or XEP-0033
`replyto` address) is the account's bare JID. For a live notification the
server set is authoritative: the client replaces its alias set with the
payload, so a rename and a deletion made on another client are applied. A
client that does not support subscriptions still works after the next login
fetch.

## Merge rules

Local state is the source of truth for the user's own names:

1. A local user alias wins over the server value for the same `(jid, id)`.
2. A server name fills a local gap when the local client has no alias.
3. A name learned from a device's resource/client (XEP-0092 or XEP-0115) only
   fills a gap; it never overwrites a user alias or a server name.
4. `last_seen` is the maximum of the local and server values.
5. The next publish is the union of local aliases, server names and learned
   names, with the priority above.
6. Deleting a local alias removes the key from the local store **and** from the
   last server snapshot, so a later whole-set publish cannot resurrect it. If a
   learned name exists, it may become the published name.

## Migration and failures

- If the node is absent and the local client has aliases or learned names, it
  publishes them on the first successful sync.
- If a fetch fails, the client must not publish: the node may contain names
  written by another client.
- A failed publish is retried on the next alias change or the next login. It is
  never silently treated as success.

## Example publish

```xml
<iq type='set'>
  <pubsub xmlns='http://jabber.org/protocol/pubsub'>
    <publish node='urn:xmpp:omemo:aliases:0'>
      <item id='current'>
        <omemo-aliases xmlns='urn:xmpp:omemo:aliases:0'>
          <device jid='alice@example.com' id='123456789' alias='Laptop'/>
        </omemo-aliases>
      </item>
    </publish>
    <!-- publish-options as above -->
  </pubsub>
</iq>
```

## Privacy

The node is readable only by the account owner (`whitelist`). The server can
still read and store the names; they are not end-to-end encrypted.
