# Stanza IM namespace specifications

This directory documents wire formats used by Stanza IM that are **not**
covered by a published XEP. They are written so another client can implement
the same behaviour without reading the Python code.

| Namespace | Transport | Access | Specification |
|-----------|-----------|--------|---------------|
| `urn:xmpp:omemo:aliases:0` | XEP-0060 private PEP node | `whitelist` | [omemo-aliases.md](omemo-aliases.md) |
| `urn:xmpp:notification-priority:0` | XEP-0060 private PEP node | `whitelist` | [notification-priority.md](notification-priority.md) |
| `http://miranda-im.org/storage#notes` | XEP-0049 private XML storage | account-private | [notes-private-storage.md](notes-private-storage.md) |

## Scope

These documents describe the payloads and the state rules. Standard XEP
semantics (IQ addressing, pubsub publish-options, private XML storage) apply
unchanged.

The following are deliberately **not** duplicated here:

- `urn:xmpp:sxe:0` — XEP-0284 Shared XML Editing.
- `urn:xmpp:jingle:apps:svg-whiteboard:0` and
  `urn:xmpp:jingle:transports:sxe` — the collaborative whiteboard has its own
  repository and specification; the Jingle transport binding is part of that
  specification, not XEP-0284.
- Standard or experimental XEPs such as MDS, Muji, JET/JET-OMEMO, Hats, OMEMO
  0.3/2 and SXE.

## Conventions

- `jid` values are bare JIDs unless a document says otherwise.
- A namespace ending in `:0` is version 0. A breaking wire change needs a new
  namespace rather than an in-place version bump.
- XML examples use single quotes for attributes only for readability; the wire
  format is ordinary XML.
- A client that does not know a namespace must ignore the node/payload and keep
  its local defaults.

## Change policy

A change to a payload, merge rule or deletion rule must update the matching
document in the same commit as the code.
