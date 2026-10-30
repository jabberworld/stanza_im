# Tagged notes in private XML storage

- **Namespace:** `http://miranda-im.org/storage#notes`
- **Transport:** XEP-0049 Private XML Storage (`jabber:iq:private`)
- **Owner:** Miranda IM compatible payload (not a Stanza IM namespace)
- **Item model:** one `<storage/>` element holding the whole note set

## Purpose

The Notes feature stores short tagged text notes on the account so they follow
the user to another client. The wire format is the Miranda IM notes payload,
kept for compatibility with existing private-storage data.

This is not PEP and it has no node/item ids. The server stores one private XML
document per account.

## Payload

```xml
<storage xmlns='http://miranda-im.org/storage#notes'>
  <note tags='work, urgent'>
    <title>Shopping list</title>
    <text>Milk, bread, coffee</text>
  </note>
  <note tags=''>
    <title/>
    <text>An untitled note</text>
  </note>
</storage>
```

| Element/attribute | Required | Meaning |
|-------------------|----------|---------|
| `note` | yes | One note. Order is the storage order; there is no stable id. |
| `note/@tags` | no | Free-form tag string. Stanza IM treats commas as separators and trims whitespace; other clients may store a different convention. |
| `title` | no | Note title, UTF-8. An empty title is valid and must be preserved. |
| `text` | no | Plain-text body, UTF-8. Line breaks are preserved. |

An empty `<storage/>` means no notes. Missing `title`/`text` children are
equivalent to empty strings. Unknown child elements must be ignored by a
reader, but a whole-set write replaces the document and therefore drops them.

## Fetch

```xml
<iq type='get'>
  <query xmlns='jabber:iq:private'>
    <storage xmlns='http://miranda-im.org/storage#notes'/>
  </query>
</iq>
```

The result carries the `<storage/>` document inside the same `query`. A
missing or empty storage means an empty note list. A server error means the
local set must not be treated as the complete server state.

## Write

```xml
<iq type='set'>
  <query xmlns='jabber:iq:private'>
    <storage xmlns='http://miranda-im.org/storage#notes'>
      <note tags='work'>
        <title>Shopping list</title>
        <text>Milk, bread, coffee</text>
      </note>
    </storage>
  </query>
</iq>
```

Rules:

1. A write replaces the **whole** set. There is no per-note update or delete.
2. Because there are no stable ids, a client that adds or edits one note must
   first fetch the current set, merge its change, and then write the result
   back. Writing a local-only set would delete notes created by another client.
3. Concurrent writers are last-write-wins at the document level. A client
   should serialize its own note operations.
4. Deleting a note rewrites the set without it.
5. An empty set is written as an empty `<storage/>` (or the document is
   removed, depending on the server); readers treat both as no notes.

## Compatibility

- Miranda IM and clients that understand this payload can read the same notes.
- A client that does not know the namespace leaves the private document
  untouched.
- The namespace is versionless. A breaking change needs a new namespace.

## Privacy

XEP-0049 private storage is scoped to the account and readable by the server.
Notes are stored in plain text and are not end-to-end encrypted.
