# Appendix E: Example Knowledge Documents (Full Text)

## About these documents

The following eight documents are the exact, complete, real content ingested by `seed/seed_knowledge_base.py` and used throughout this manual's examples and the retrieval evaluation dataset (the evaluation chapter). Each is reproduced here in full -- not summarized -- as phase7.md's final-deliverables list explicitly asks for example documents to be included. Every one of these was actually ingested through the real pipeline during this implementation and reached `status: READY`.

## VPN Troubleshooting Guide

*File: `seed/knowledge_docs/vpn_troubleshooting_guide.md` -- category: `VPN`*

### Overview

The university VPN (Virtual Private Network) lets students and staff
reach on-campus resources -- the library research databases, department
file shares, and internal web applications -- from off-campus networks.
All university VPN traffic runs through Cisco AnyConnect. This guide
covers installation, connection, and the most common failure modes.

### Installing Cisco AnyConnect

1. Go to the IT Services software portal and download Cisco AnyConnect
   for your operating system (Windows, macOS, or Linux).
2. Run the installer with administrator privileges.
3. Launch AnyConnect and enter the connection address: `vpn.university.edu`.
4. Sign in with your university username and password when prompted.

### Connecting to the VPN

1. Open Cisco AnyConnect.
2. Confirm the address field shows `vpn.university.edu`.
3. Click **Connect**.
4. Enter your university credentials, then approve the multi-factor
   authentication (MFA) push notification on your phone.
5. Once connected, the AnyConnect icon in your system tray turns green.

### Common VPN Errors

#### VPN-ERR-403: Authentication Failed

This is the single most common VPN support ticket. It means the VPN
server rejected your credentials. Causes, in order of likelihood:

- **Expired password.** If your university password recently expired,
  the VPN will keep failing even though other services (email, etc.)
  still accept the old password briefly due to caching. Reset your
  password (see the Password Reset Procedure document) and try again.
- **MFA push not approved in time.** The MFA prompt times out after 60
  seconds. If you missed it, reconnect and approve the push immediately
  when it arrives.
- **Account not yet provisioned for VPN access.** New student accounts
  can take up to 24 hours after activation before VPN access is enabled.
  If this is a brand-new account, wait and try again the next day before
  opening a ticket.
- **Account locked after failed attempts.** Five consecutive failed
  logins locks the account for 30 minutes as a security measure.

#### VPN client says "Connection attempt has failed"

Usually a network issue, not a credentials issue:

- Restart the AnyConnect client and try again.
- Confirm you have working internet access outside the VPN first (load
  any external website).
- Some hotel and public WiFi networks block the ports AnyConnect needs
  (UDP 443). Try switching to TLS-only mode in AnyConnect's advanced
  settings, or use a different network.
- Corporate/employer networks sometimes block outbound VPN traffic
  entirely -- there is no client-side fix for this; use a different
  network.

#### VPN connects but internal sites are still unreachable

- Confirm the AnyConnect icon shows green (connected), not yellow
  (connecting) or red (disconnected).
- DNS can take up to 30 seconds to update after connecting. Wait, then
  retry.
- Some browsers cache a "site not found" result. Clear the browser's DNS
  cache or try a private/incognito window.

### When to Escalate

If a student has confirmed their password is current, MFA was approved
promptly, and the account is more than 24 hours old, and VPN-ERR-403
still occurs, escalate to network engineering -- this can indicate the
account was not correctly added to the VPN authorization group during
provisioning.

## WiFi Troubleshooting Guide

*File: `seed/knowledge_docs/wifi_troubleshooting_guide.md` -- category: `WIFI`*

### Overview

Campus WiFi is provided under two network names (SSIDs): `CampusSecure`
(802.1X encrypted, requires university login, recommended for all
personal devices) and `CampusGuest` (open, rate-limited, no login,
intended for visitors only). This guide covers connecting and the most
common disconnection issues.

### Connecting to CampusSecure

1. Select `CampusSecure` from your device's WiFi list.
2. When prompted for a certificate or security type, choose
   **WPA2-Enterprise** / **802.1X**.
3. Username: your full university email address.
4. Password: your university password.
5. If prompted to trust a certificate, accept the university's
   certificate (issued by "University IT Services Root CA").

### "Campus WiFi keeps disconnecting"

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

### CampusGuest Limitations

`CampusGuest` is intentionally rate-limited and blocks VPN, SSH, and some
streaming protocols. Students and staff should not use `CampusGuest` for
day-to-day use -- always prefer `CampusSecure`, which does not have these
restrictions.

### Forgetting and Re-adding a Network

**Windows:** Settings > Network & Internet > WiFi > Manage known
networks > select `CampusSecure` > Forget.

**macOS:** System Settings > WiFi > (i) next to `CampusSecure` > Forget
This Network.

After forgetting, reconnect from the WiFi list and re-enter credentials
as described above.

### When to Escalate

If disconnects happen constantly (multiple times per minute) in a single
specific location, and are not resolved by forgetting/re-adding the
network, escalate to network engineering with the building name and room
number -- this may indicate a failing access point rather than a
device-side issue.

## Password Reset Procedure

*File: `seed/knowledge_docs/password_reset_procedure.md` -- category: `PASSWORD`*

### Overview

University accounts use a single password across email, WiFi
(CampusSecure), VPN, and the student portal. This document covers
self-service password reset and multi-factor authentication (MFA) device
changes.

### Self-Service Password Reset

1. Go to `password.university.edu` from any browser.
2. Click **Forgot Password**.
3. Enter your university username (not your full email address).
4. Verify your identity using one of:
   - An MFA push notification to your registered phone, or
   - A one-time code sent to your personal recovery email (set during
     account setup), or
   - Your security questions (if configured).
5. Choose a new password. Requirements: at least 12 characters, at least
   one number, at least one symbol, and it must not match any of your
   last 5 passwords.
6. Allow up to 15 minutes for the new password to propagate to all
   systems (email, WiFi, VPN). Signing in immediately after a reset may
   briefly still fail on some systems while this propagates.

### "I forgot my student password"

Direct the student to `password.university.edu` and the steps above. If
they cannot complete identity verification (no MFA device registered,
recovery email inaccessible, no security questions set), this requires
in-person identity verification at the IT Services help desk with a
photo ID -- self-service reset cannot bypass identity verification.

### Resetting MFA (Multi-Factor Authentication)

If a student has a new phone, lost their phone, or their MFA app was
uninstalled, their old MFA device needs to be de-registered and a new one
added.

1. Go to `mfa.university.edu` and sign in with username and password
   (not MFA -- signing in to the MFA portal itself only requires the
   password).
2. Under **My Devices**, remove the old/lost device.
3. Click **Add a Device** and follow the QR code enrollment flow with an
   authenticator app (Microsoft Authenticator or Google Authenticator are
   both supported).
4. Test the new device immediately by triggering a push (the portal has
   a **Send Test Push** button) before leaving the page.

If a student cannot sign in to `mfa.university.edu` at all because they
also forgot their password, the password must be reset FIRST (see
above), then MFA re-enrollment can proceed.

### Account Lockout

Five consecutive failed password attempts locks the account for 30
minutes. This is a fixed security policy and cannot be manually
unlocked early by IT staff -- advise the student to wait out the lockout
window rather than continuing to retry, since each attempt during
lockout resets the 30-minute timer.

### Related Issues

A locked-out or recently-reset account can also cause VPN-ERR-403 (see
the VPN Troubleshooting Guide) for up to 15 minutes after a reset while
the new password propagates -- this is expected and not a separate VPN
problem.

## Student Account Setup

*File: `seed/knowledge_docs/student_account_setup.md` -- category: `ACCOUNT`*

### Overview

Every admitted student receives a university account after enrollment
deposit confirmation. This document covers first-time activation and
initial configuration.

### First-Time Activation

1. Within 48 hours of enrollment confirmation, an activation email is
   sent to the personal email address provided on the application. It
   contains a one-time activation link (valid for 7 days).
2. Click the activation link and set an initial password (12+
   characters, at least one number and one symbol).
3. Register for multi-factor authentication (MFA) immediately -- the
   activation flow will not let you skip this step. Use an authenticator
   app (Microsoft Authenticator or Google Authenticator).
4. Set a personal recovery email address (used later for self-service
   password resets -- see the Password Reset Procedure document).

### "How do I set up my new student account?"

Walk the student through First-Time Activation above. If they never
received the activation email, check:

- Spam/junk folder of the personal email on file.
- Whether the enrollment deposit has actually cleared (activation emails
  only send after deposit confirmation, which can lag 24-48 hours behind
  payment processing).
- That the personal email on file is spelled correctly in the admissions
  system -- a typo there means the activation email went nowhere; this
  requires an admissions office correction, not an IT fix, and should be
  escalated to the registrar's office.

### What Gets Provisioned on Activation

- University email address (`firstname.lastname@university.edu`)
- Access to the student portal
- WiFi access (CampusSecure -- see the WiFi Troubleshooting Guide)
- Access to Microsoft 365 (Office apps, OneDrive) -- see the Microsoft
  Office Installation document
- VPN access -- note this can take up to 24 hours AFTER activation to
  become active; a VPN-ERR-403 in the first day is often just this delay,
  not a real problem (see the VPN Troubleshooting Guide)

### Changing Your Preferred Name

Students may set a preferred first name, which appears on class rosters,
email display name, and the student portal, separate from their legal
name (which remains on official transcripts and financial documents).
This is done at `portal.university.edu` under Profile > Preferred Name,
and takes up to 24 hours to propagate to all systems.

### Deactivation

Accounts are automatically deactivated 180 days after a student's last
active term with no new enrollment, per university data retention policy.
A deactivated account can be reactivated by the registrar's office if the
student re-enrolls; IT Services cannot reactivate an account directly.

## Microsoft Office Installation

*File: `seed/knowledge_docs/microsoft_office_installation.md` -- category: `SOFTWARE`*

### Overview

All active students and staff are entitled to a free Microsoft 365
subscription (Word, Excel, PowerPoint, OneNote, and 1TB of OneDrive
storage) for the duration of their enrollment/employment, installable on
up to 5 personal devices.

### "How do I install Microsoft Office on my laptop?"

1. Go to `portal.office.com` and sign in with your full university email
   address and password.
2. Click **Install Office** in the top-right corner of the Office portal.
3. Choose **Office 365 apps** (not "Office 2021" or any one-time-purchase
   option -- those are not covered by the university license).
4. Run the downloaded installer. Installation typically takes 10-20
   minutes depending on internet speed.
5. Open any Office app (e.g. Word) and sign in again with your university
   email when prompted -- this activates the license on this specific
   device.

### Common Installation Issues

#### "Something went wrong" during activation

Usually means the sign-in step (step 5) used a personal Microsoft
account instead of the university account. Sign out of any personal
Microsoft account on the device first, then retry activation with the
university email.

#### Installer hangs at a specific percentage

Corporate/campus network proxies occasionally interrupt the Office
installer's connection. Try again on CampusSecure WiFi (not
CampusGuest, which rate-limits large downloads) or a home network.

#### "You've reached the device limit"

The license allows 5 devices. To free up a slot, go to
`portal.office.com` > Account settings > find "Install status" and
deactivate an old/unused device from the list, then retry installation
on the new device.

#### Office apps show "Unlicensed Product" after working previously

This means the subscription lapsed -- almost always because the
student's account was deactivated (see Student Account Setup document's
Deactivation section) or the employee's employment status changed. If
the account itself is active in the student/staff portal, this may be a
sync delay of up to 24 hours; if it persists beyond that, escalate to
software licensing.

### Mac vs. Windows

The installer and activation steps above are identical on macOS and
Windows -- both are covered by the same university Microsoft 365
license. Office for Mac does have some minor feature differences from
Office for Windows (mainly in advanced Excel macros), which is a
Microsoft product limitation, not something IT Services can change.

## Campus Network Guide

*File: `seed/knowledge_docs/campus_network_guide.md` -- category: `NETWORK`*

### Overview

This document covers wired (ethernet) networking in dorms and campus
buildings, network naming conventions, and general network architecture
that other troubleshooting guides (WiFi, VPN) reference.

### Wired Ethernet in Dorms

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

### Network Names (SSIDs) Reference

- `CampusSecure` -- primary WiFi network, 802.1X encrypted, requires
  university login (see the WiFi Troubleshooting Guide).
- `CampusGuest` -- open guest WiFi, rate-limited, visitors only.
- `CampusIoT` -- separate network for smart devices (game consoles,
  smart speakers, printers) that can't do 802.1X login; requires
  pre-registering the device's MAC address at `iot.university.edu`.

### VPN and Off-Campus Access

The VPN (`vpn.university.edu`, via Cisco AnyConnect -- see the VPN
Troubleshooting Guide) is the only supported way to reach internal
campus resources (file shares, internal web apps) from outside the
campus network. Off-campus students should expect anything that requires
VPN access on-campus to also require it off-campus.

### Network Architecture Notes (For Escalation Context)

The campus network is split into building-level VLANs; a device
physically moved between buildings on wired ethernet will receive a new
IP address on reconnect (this is normal, not a fault). WiFi access
points are managed centrally and roam a device between physical access
points transparently within `CampusSecure`, which is why brief 1-3
second WiFi drops while walking are expected and not a bug (see the WiFi
Troubleshooting Guide).

### When to Escalate

Any report of a fully dead ethernet jack (no link light with a known-good
cable and device) should be escalated to facilities/network engineering
with the building, room number, and jack label (printed on the wall
plate) -- this cannot be diagnosed or fixed remotely.

## Printer Troubleshooting

*File: `seed/knowledge_docs/printer_troubleshooting.md` -- category: `HARDWARE`*

### Overview

This document covers the campus print system (`PrintSmart`), used in
libraries, computer labs, and department printers. Students print by
sending a job from any registered device; the job releases when the
student badges in at any printer with their student ID.

### Setting Up PrintSmart

1. Install the PrintSmart client from the software portal (same portal
   used for Cisco AnyConnect -- see the VPN Troubleshooting Guide).
2. Sign in with your university credentials.
3. Print from any application as normal; select the `PrintSmart` printer.
   The job is held on the server, not sent directly to a printer.
4. At any campus printer, tap your student ID card on the badge reader.
   All held jobs for your account appear on the printer's screen; select
   which to print.

### "The library printer says paper jam but there's no paper stuck"

This is one of the most common printer complaints and is almost always
one of the following, in order of likelihood:

- **A jam earlier in the paper path that isn't visible from the tray.**
  Open every access panel/door on the printer (not just the main tray) --
  most jams are in the fuser area or a roller further inside, not
  visible without opening the internal doors. The printer's screen
  usually shows a diagram indicating which door to open.
- **A torn corner of paper left behind from a previous jam.** Even after
  a jam looks cleared, a small torn piece can remain lodged in a roller
  and keep triggering the sensor. Run a hand along the visible paper path
  to check for a torn fragment.
- **Humidity-swollen paper.** In humid weather, paper from an opened ream
  can swell slightly and jam a sensor that a fresh ream wouldn't. Try a
  fresh ream if available.
- **A worn paper-feed sensor giving a false reading.** If the paper path
  is confirmed completely clear and the jam error persists after a full
  power cycle, this indicates a hardware sensor fault -- escalate to
  facilities/printer maintenance rather than continuing to open and close
  trays.

### Job Stuck "Pending" and Never Appears at the Printer

- Confirm the printer you badged at is online (a red or amber light
  usually indicates an offline/error state).
- Held jobs expire after 24 hours if never released -- if it's been
  longer than that, the job is gone and needs to be resent.
- Confirm you badged with the correct ID -- a student with two cards
  (e.g. a replacement issued after a lost card) occasionally still
  carries the deactivated old one.

### Print Quota

Each student receives 500 pages/semester at no charge; additional pages
are billed to the student account at $0.10/page. Quota resets at the
start of each semester and does not roll over. Quota balance is visible
in the PrintSmart client.

### When to Escalate

Any hardware fault confirmed after a full power cycle (persistent jam
error with a visibly clear paper path, print quality defects like
repeating marks/streaks, unusual noises) should be escalated to
facilities/printer maintenance with the printer's asset tag number
(printed on a sticker on the printer's side).

## Known IT Issues

*File: `seed/knowledge_docs/known_it_issues.md` -- category: `OTHER`*

### Overview

This document tracks currently known, ongoing issues that affect
multiple students/staff, so that a ticket about a widespread issue can be
answered immediately ("this is a known issue, here is the status")
instead of independently re-investigated. This document is updated by IT
Services as issues are confirmed and resolved -- an admin should
re-upload a new version (see the knowledge-base versioning behavior in
the RAG manual) when an issue's status changes rather than editing
history silently.

### "Is there a known outage affecting campus email today?"

Check this section first before investigating an individual email
complaint as a one-off account issue. As of this document's most recent
version, there are no active, ongoing email outages. If a student reports
email being down, treat it as an individual account issue (see the
Password Reset Procedure document) unless multiple independent reports
arrive within a short window, in which case escalate to infrastructure
immediately and update this document.

### Currently Known Issues

#### Lecture hall WiFi capacity (multiple buildings, ongoing)

Several large lecture halls see degraded `CampusSecure` WiFi performance
during peak class-change times (a few minutes before/after the hour) due
to a high concentration of simultaneously-connecting devices. This is a
known capacity limitation being addressed by a phased access-point
upgrade; the WiFi Troubleshooting Guide's "interference in dense areas"
section reflects this. No individual-device fix resolves this; do not
have students repeatedly forget/re-add the network for this specific
symptom.

#### VPN slow during finals week (seasonal, recurring)

VPN throughput is measurably slower during finals week each semester due
to elevated concurrent usage (students working on projects/theses from
off-campus). This is a known, expected, seasonal load pattern -- not a
fault -- and does not require escalation on its own; only escalate if a
student sees the connection actually fail (VPN-ERR-403 or "Connection
attempt has failed") rather than just being slow.

### Resolved Issues (Recent History)

#### Office 365 licensing sync delay (resolved)

For a period, newly activated student accounts saw up to a 48-hour delay
before Microsoft 365 licensing activated (longer than the normal 24-hour
window described in the Microsoft Office Installation document). This
was traced to a licensing sync job running only once daily instead of
hourly, and was resolved by increasing the sync frequency. If a
student describes exactly this symptom now, it should be treated as a
new individual issue, not this resolved one -- do not assume it has
recurred without checking current sync job health first.

### How to Use This Document During Triage

1. Check whether the student's symptom matches an entry under "Currently
   Known Issues" above.
2. If it matches, respond with the known cause/status/ETA rather than
   re-diagnosing from scratch, and do not open a duplicate infrastructure
   ticket for it -- link the student's ticket to the existing tracking
   ticket instead.
3. If it does NOT match anything here, proceed with the relevant
   individual troubleshooting guide (VPN, WiFi, Password Reset, etc.)
   as normal.
