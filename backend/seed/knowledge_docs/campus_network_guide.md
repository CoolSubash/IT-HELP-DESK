# Campus Network Guide

## Overview

This document covers wired (ethernet) networking in dorms and campus
buildings, network naming conventions, and general network architecture
that other troubleshooting guides (WiFi, VPN) reference.

## Wired Ethernet in Dorms

Every dorm room has at least one active ethernet wall jack, providing a
faster and more stable connection than WiFi -- recommended for gaming,
large downloads, and video calls.

1. Connect an ethernet cable from your device to the wall jack.
2. Most devices configure automatically via DHCP -- no manual setup is
   needed. If the connection doesn't come up automatically:
   - Confirm the device's network adapter is set to "Obtain an IP address
     automatically" (DHCP), not a static/manual IP.
   - Try a different ethernet cable -- damaged cables are a very common
     cause of "no connection" reports in dorms.
3. Wired connections do not require 802.1X sign-in the way CampusSecure
   WiFi does -- registration happens automatically based on the port and
   device the first time it connects each semester.

If a dorm room's ethernet jack shows no link light at all on both ends,
the jack itself may be inactive (not all jacks in a room are always
enabled) or the in-wall cabling may be faulty -- this requires a physical
inspection by facilities/network engineering, not something resolvable
remotely.

## Network Names (SSIDs) Reference

- `CampusSecure` -- primary WiFi network, 802.1X encrypted, requires
  university login (see the WiFi Troubleshooting Guide).
- `CampusGuest` -- open guest WiFi, rate-limited, visitors only.
- `CampusIoT` -- separate network for smart devices (game consoles,
  smart speakers, printers) that can't do 802.1X login; requires
  pre-registering the device's MAC address at `iot.university.edu`.

## VPN and Off-Campus Access

The VPN (`vpn.university.edu`, via Cisco AnyConnect -- see the VPN
Troubleshooting Guide) is the only supported way to reach internal
campus resources (file shares, internal web apps) from outside the
campus network. Off-campus students should expect anything that requires
VPN access on-campus to also require it off-campus.

## Network Architecture Notes (For Escalation Context)

The campus network is split into building-level VLANs; a device
physically moved between buildings on wired ethernet will receive a new
IP address on reconnect (this is normal, not a fault). WiFi access
points are managed centrally and roam a device between physical access
points transparently within `CampusSecure`, which is why brief 1-3
second WiFi drops while walking are expected and not a bug (see the WiFi
Troubleshooting Guide).

## When to Escalate

Any report of a fully dead ethernet jack (no link light with a known-good
cable and device) should be escalated to facilities/network engineering
with the building, room number, and jack label (printed on the wall
plate) -- this cannot be diagnosed or fixed remotely.
