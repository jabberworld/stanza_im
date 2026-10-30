# Per-contact notification priority

- **Namespace:** `urn:xmpp:notification-priority:0`
- **Node:** `urn:xmpp:notification-priority:0`
- **Transport:** XEP-0060 publish-subscribe (private PEP node on the account's
  bare JID)
- **Access model:** `whitelist`
- **Item id:** `current`
- **Owner:** Stanza IM

## Purpose

A user can mark a contact's notifications as `high` or `low`. `normal` is the
absence of an entry. The map is stored locally and mirrored to a private PEP
node so the choice follows the account to another client.

This is a client-side notification policy. It is not a message priority on the
wire and it does not change delivery.

## Payload

```xml
<notification-priorities xmlns='urn:xmpp:notification-priority:0'>
  <contact jid='alice@example.com' priority='high'/>
  <contact jid='bob@example.com' priority='low'/>
</notification-priorities>
```

| Attribute | Required | Meaning |
|-----------|----------|---------|
| `jid` | yes | Bare JID of the contact. A resource part is ignored. |
| `priority` | yes | `high` or `low`. Any other value is ignored. |

`normal` is represented by removing the contact from the set. A duplicate
`jid` is invalid; the last occurrence wins.

## Publish options

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
    <items node='urn:xmpp:notification-priority:0'/>
  </pubsub>
</iq>
```

Rules:

- `item-not-found` means the node does not exist yet; treat it as an empty set.
- Any other error means the server state is **unknown**. Do not treat it as an
  empty set and do not publish an empty replacement.
- An empty `<items/>` also means an empty set.

No `+notify` subscription is required. Clients fetch the node on login.

## Merge rules

On login:

1. For a contact present in both stores, the server value wins.
2. A local contact missing from the server is kept and uploaded, so a change
   made while an earlier publish failed is not lost.
3. If the node is absent and the local map is non-empty, publish the local map.
4. If both are empty, do nothing.

A local change publishes the whole set. Setting a contact to `normal` removes
it from the set before publishing, which deletes the entry from the node.

## Effective priority

The user setting is applied before any XEP-0131 SHIM `Urgency` header:

1. `high` or `low` from this node wins.
2. Otherwise `Urgency: high` / `Urgency: low` applies.
3. `Urgency: medium`, a missing header or an unknown value means `normal`.

Only message notifications are affected. Typing and status notifications are
not.

## Example publish

```xml
<iq type='set'>
  <pubsub xmlns='http://jabber.org/protocol/pubsub'>
    <publish node='urn:xmpp:notification-priority:0'>
      <item id='current'>
        <notification-priorities xmlns='urn:xmpp:notification-priority:0'>
          <contact jid='alice@example.com' priority='high'/>
        </notification-priorities>
      </item>
    </publish>
    <!-- publish-options as above -->
  </pubsub>
</iq>
```

## Privacy

The node is readable only by the account owner (`whitelist`). The server can
still read and store the contact list and priorities; they are not end-to-end
encrypted.
