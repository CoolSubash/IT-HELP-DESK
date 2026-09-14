# Printer Troubleshooting

## Overview

This document covers the campus print system (`PrintSmart`), used in
libraries, computer labs, and department printers. Students print by
sending a job from any registered device; the job releases when the
student badges in at any printer with their student ID.

## Setting Up PrintSmart

1. Install the PrintSmart client from the software portal (same portal
   used for Cisco AnyConnect -- see the VPN Troubleshooting Guide).
2. Sign in with your university credentials.
3. Print from any application as normal; select the `PrintSmart` printer.
   The job is held on the server, not sent directly to a printer.
4. At any campus printer, tap your student ID card on the badge reader.
   All held jobs for your account appear on the printer's screen; select
   which to print.

## "The library printer says paper jam but there's no paper stuck"

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

## Job Stuck "Pending" and Never Appears at the Printer

- Confirm the printer you badged at is online (a red or amber light
  usually indicates an offline/error state).
- Held jobs expire after 24 hours if never released -- if it's been
  longer than that, the job is gone and needs to be resent.
- Confirm you badged with the correct ID -- a student with two cards
  (e.g. a replacement issued after a lost card) occasionally still
  carries the deactivated old one.

## Print Quota

Each student receives 500 pages/semester at no charge; additional pages
are billed to the student account at $0.10/page. Quota resets at the
start of each semester and does not roll over. Quota balance is visible
in the PrintSmart client.

## When to Escalate

Any hardware fault confirmed after a full power cycle (persistent jam
error with a visibly clear paper path, print quality defects like
repeating marks/streaks, unusual noises) should be escalated to
facilities/printer maintenance with the printer's asset tag number
(printed on a sticker on the printer's side).
