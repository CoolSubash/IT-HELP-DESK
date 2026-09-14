# Password Reset Procedure

## Overview

University accounts use a single password across email, WiFi
(CampusSecure), VPN, and the student portal. This document covers
self-service password reset and multi-factor authentication (MFA) device
changes.

## Self-Service Password Reset

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

## "I forgot my student password"

Direct the student to `password.university.edu` and the steps above. If
they cannot complete identity verification (no MFA device registered,
recovery email inaccessible, no security questions set), this requires
in-person identity verification at the IT Services help desk with a
photo ID -- self-service reset cannot bypass identity verification.

## Resetting MFA (Multi-Factor Authentication)

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

## Account Lockout

Five consecutive failed password attempts locks the account for 30
minutes. This is a fixed security policy and cannot be manually
unlocked early by IT staff -- advise the student to wait out the lockout
window rather than continuing to retry, since each attempt during
lockout resets the 30-minute timer.

## Related Issues

A locked-out or recently-reset account can also cause VPN-ERR-403 (see
the VPN Troubleshooting Guide) for up to 15 minutes after a reset while
the new password propagates -- this is expected and not a separate VPN
problem.
