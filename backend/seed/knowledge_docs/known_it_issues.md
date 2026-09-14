# Known IT Issues

## Overview

This document tracks currently known, ongoing issues that affect
multiple students/staff, so that a ticket about a widespread issue can be
answered immediately ("this is a known issue, here is the status")
instead of independently re-investigated. This document is updated by IT
Services as issues are confirmed and resolved -- an admin should
re-upload a new version (see the knowledge-base versioning behavior in
the RAG manual) when an issue's status changes rather than editing
history silently.

## "Is there a known outage affecting campus email today?"

Check this section first before investigating an individual email
complaint as a one-off account issue. As of this document's most recent
version, there are no active, ongoing email outages. If a student reports
email being down, treat it as an individual account issue (see the
Password Reset Procedure document) unless multiple independent reports
arrive within a short window, in which case escalate to infrastructure
immediately and update this document.

## Currently Known Issues

### Lecture hall WiFi capacity (multiple buildings, ongoing)

Several large lecture halls see degraded `CampusSecure` WiFi performance
during peak class-change times (a few minutes before/after the hour) due
to a high concentration of simultaneously-connecting devices. This is a
known capacity limitation being addressed by a phased access-point
upgrade; the WiFi Troubleshooting Guide's "interference in dense areas"
section reflects this. No individual-device fix resolves this; do not
have students repeatedly forget/re-add the network for this specific
symptom.

### VPN slow during finals week (seasonal, recurring)

VPN throughput is measurably slower during finals week each semester due
to elevated concurrent usage (students working on projects/theses from
off-campus). This is a known, expected, seasonal load pattern -- not a
fault -- and does not require escalation on its own; only escalate if a
student sees the connection actually fail (VPN-ERR-403 or "Connection
attempt has failed") rather than just being slow.

## Resolved Issues (Recent History)

### Office 365 licensing sync delay (resolved)

For a period, newly activated student accounts saw up to a 48-hour delay
before Microsoft 365 licensing activated (longer than the normal 24-hour
window described in the Microsoft Office Installation document). This
was traced to a licensing sync job running only once daily instead of
hourly, and was resolved by increasing the sync frequency. If a
student describes exactly this symptom now, it should be treated as a
new individual issue, not this resolved one -- do not assume it has
recurred without checking current sync job health first.

## How to Use This Document During Triage

1. Check whether the student's symptom matches an entry under "Currently
   Known Issues" above.
2. If it matches, respond with the known cause/status/ETA rather than
   re-diagnosing from scratch, and do not open a duplicate infrastructure
   ticket for it -- link the student's ticket to the existing tracking
   ticket instead.
3. If it does NOT match anything here, proceed with the relevant
   individual troubleshooting guide (VPN, WiFi, Password Reset, etc.)
   as normal.
