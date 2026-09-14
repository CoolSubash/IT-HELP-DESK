# VPN Troubleshooting Guide

## Overview

The university VPN (Virtual Private Network) lets students and staff
reach on-campus resources -- the library research databases, department
file shares, and internal web applications -- from off-campus networks.
All university VPN traffic runs through Cisco AnyConnect. This guide
covers installation, connection, and the most common failure modes.

## Installing Cisco AnyConnect

1. Go to the IT Services software portal and download Cisco AnyConnect
   for your operating system (Windows, macOS, or Linux).
2. Run the installer with administrator privileges.
3. Launch AnyConnect and enter the connection address: `vpn.university.edu`.
4. Sign in with your university username and password when prompted.

## Connecting to the VPN

1. Open Cisco AnyConnect.
2. Confirm the address field shows `vpn.university.edu`.
3. Click **Connect**.
4. Enter your university credentials, then approve the multi-factor
   authentication (MFA) push notification on your phone.
5. Once connected, the AnyConnect icon in your system tray turns green.

## Common VPN Errors

### VPN-ERR-403: Authentication Failed

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

### VPN client says "Connection attempt has failed"

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

### VPN connects but internal sites are still unreachable

- Confirm the AnyConnect icon shows green (connected), not yellow
  (connecting) or red (disconnected).
- DNS can take up to 30 seconds to update after connecting. Wait, then
  retry.
- Some browsers cache a "site not found" result. Clear the browser's DNS
  cache or try a private/incognito window.

## When to Escalate

If a student has confirmed their password is current, MFA was approved
promptly, and the account is more than 24 hours old, and VPN-ERR-403
still occurs, escalate to network engineering -- this can indicate the
account was not correctly added to the VPN authorization group during
provisioning.
