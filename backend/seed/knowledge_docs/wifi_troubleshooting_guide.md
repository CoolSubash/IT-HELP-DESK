# WiFi Troubleshooting Guide

## Overview

Campus WiFi is provided under two network names (SSIDs): `CampusSecure`
(802.1X encrypted, requires university login, recommended for all
personal devices) and `CampusGuest` (open, rate-limited, no login,
intended for visitors only). This guide covers connecting and the most
common disconnection issues.

## Connecting to CampusSecure

1. Select `CampusSecure` from your device's WiFi list.
2. When prompted for a certificate or security type, choose
   **WPA2-Enterprise** / **802.1X**.
3. Username: your full university email address.
4. Password: your university password.
5. If prompted to trust a certificate, accept the university's
   certificate (issued by "University IT Services Root CA").

## "Campus WiFi keeps disconnecting"

This is the most frequently reported WiFi issue. Causes, roughly ordered
by frequency:

- **Roaming between access points.** Campus buildings have many WiFi
  access points; walking between them can cause a brief (1-3 second)
  disconnect while the device's radio switches access points. This is
  normal and not a fault -- if the reconnect is fast and automatic, no
  action is needed.
- **Saved network profile out of date.** If your device saved
  `CampusSecure` with an old password, forget the network and reconnect
  from scratch rather than just re-entering the password over the old
  profile.
- **Power-saving WiFi mode.** Many laptops aggressively power down the
  WiFi radio when the screen is dimmed to save battery, which can look
  like random disconnects. Disable WiFi power-saving in the device's
  network adapter settings.
- **Too many saved networks with the same SSID name.** If a personal
  hotspot or another network is also named `CampusSecure` (rare, but
  happens with default router names), the device may repeatedly try
  the wrong one. Rename any personal networks to avoid collisions.
- **Interference in dense areas.** Lecture halls with hundreds of
  connected devices during class time can see degraded WiFi performance.
  This is a known capacity issue in a small number of buildings, tracked
  separately (see the Known IT Issues document).

## CampusGuest Limitations

`CampusGuest` is intentionally rate-limited and blocks VPN, SSH, and some
streaming protocols. Students and staff should not use `CampusGuest` for
day-to-day use -- always prefer `CampusSecure`, which does not have these
restrictions.

## Forgetting and Re-adding a Network

**Windows:** Settings > Network & Internet > WiFi > Manage known
networks > select `CampusSecure` > Forget.

**macOS:** System Settings > WiFi > (i) next to `CampusSecure` > Forget
This Network.

After forgetting, reconnect from the WiFi list and re-enter credentials
as described above.

## When to Escalate

If disconnects happen constantly (multiple times per minute) in a single
specific location, and are not resolved by forgetting/re-adding the
network, escalate to network engineering with the building name and room
number -- this may indicate a failing access point rather than a
device-side issue.
