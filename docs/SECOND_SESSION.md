# Farm in a second session

xpedite plays Roblox with the real mouse and keyboard, so while it farms the PC is its. A
**second session** gives it a Windows account of its own: you connect to that account with
Remote Desktop, start the farm there, and minimize the window. The farm has its own screen and
cursor in there, and your PC stays yours.

It's optional. Farming in your own account works on every PC and needs none of this. The
second session is for people who want to keep using the PC while it farms, and who are happy to
install one third-party tool.

In xpedite: **Setup > Farm in a second session.** The window checks everything below, does what
it can with a button, and says what's left. Open it again whenever something stops working.

---

## Is it for you?

| | Needed | Notes |
|---|---|---|
| Windows | 10 or 11, Home or Pro | Home has no Remote Desktop host; Pro has one but allows only one session at a time. Both need the wrapper (step 2). |
| Memory | 8 GB at least, 16 GB is comfortable | Two sessions running Roblox use about 3 GB more than one. With 8 GB, close other apps while it farms. |
| Graphics | Any card with its driver installed | Measured on an RTX 5060 laptop. Integrated graphics should manage Roblox at its lowest graphics, but that hasn't been measured. |
| A Roblox account for the farm | Yes | One Roblox account plays in one place at a time. To play yourself while it farms, the farm needs a second Roblox account. |
| Admin rights on the PC | Once | For installing the wrapper and one settings step. |

**What you do and what xpedite does:**

- **You:** install the wrapper, make the farm account, sign in to Roblox in there.
- **xpedite:** checks everything, turns on what Windows needs (one admin prompt), writes the
  connection file, and makes the shortcut inside the session.

---

## Before you start: the wrapper, honestly

Windows lets one person use a home PC at a time. A **wrapper** lifts that limit so a second
account can sign in beside you. Microsoft doesn't make it, and xpedite never ships or installs
it: you download it yourself.

- Antivirus programs, Windows Defender included, often flag these tools, because they patch how
  Remote Desktop works. If yours quarantines it, that's its call and yours.
- Windows' licence for Home and Pro is for one user at a time. Using a wrapper is your decision.
- If either worries you, skip all of this and farm in your own account.

---

## Step 1: put xpedite where both accounts can reach it

The farm account runs the same copy of xpedite and saves its settings and logs there, so the
folder must be open to every account on the PC.

- **Fine:** a folder at the top of a drive, like `C:\xpedite` or `D:\xpedite`.
- **Not fine:** anywhere inside `C:\Users\<you>`, like your Desktop or Downloads. Those are yours
  only.

The checker's **Files** rows tell you. If it says *Python reachable: yours only*, Python is
installed for your account only. Reinstall it with **Install for all users** ticked, or use a
copy kept inside the xpedite folder.

Both accounts share that folder's settings (queue, plans, Discord), so whatever you set up in one
works in the other.

## Step 2: install the wrapper

**RDPWrapKit** is the one xpedite was measured with (`github.com/cpdx4/RDPWrapKit`). It finds what
to patch by itself, so Windows updates don't break it.

1. Download `RDPWrapKit-Setup.exe` from the project's latest release (the checker's **Open its
   page** button goes there).
2. Run it and choose **Typical Setup**. Keep the defaults (**Install**, **Create RDP shortcuts**).
   You can let it create the farm account too, which saves step 3.
3. Restart the PC if it asks.

The checker's **Windows: Wrapper** row should then say *TermWrap (RDPWrapKit)*, and
**Remote Desktop** should say *listening*.

**The classic RDP Wrapper also works** (`github.com/stascorp/rdpwrap`): run `install.bat` as
administrator, then `RDPConf.exe` should say *fully supported*. It reads the Windows build it
supports from `rdpwrap.ini`, so a Windows update can break it. The checker notices (*doesn't
know termsrv ...*); see Troubleshooting.

## Step 3: make the farm account

A second Windows account, used only by the farm.

- **Windows 11:** Settings > Accounts > Other users > **Add account** > *I don't have this
  person's sign-in information* > *Add a user without a Microsoft account*.
- **Windows 10:** Settings > Accounts > Family & other users > **Add someone else to this PC**,
  then the same two choices.

Give it any name (for example `farm`) and **a password**: Remote Desktop refuses accounts
without one. A standard account is enough. The checker's **Make one** button opens that settings
page.

Then pick the account in the window's **The farm account** box.

## Step 4: the admin settings (one click, Windows asks)

Press **Apply (Windows asks)** and say yes to Windows' prompt. The window lists exactly what
will change before you press it, and changes only what isn't set already:

| Setting | Why |
|---|---|
| Remote Desktop on | The wrapper needs it to accept the connection. |
| Sessions use the graphics card (`bEnumerateHWBeforeSW` = 1) | Without it, Remote Desktop sessions draw on the CPU and Roblox crawls. |
| Hardware H.264 off (`AVCHardwareEncodePreferred` = 0) | With it on, pink, purple and green smears covered the picture. |
| The farm account in *Remote Desktop Users* | Only if it's a standard account: otherwise it isn't allowed to connect. |

The two graphics settings take effect from the next connection. If the farm account was already
signed in, sign it out first (Start > your picture > Sign out, inside the session).

## Step 5: the connection file

Press **Write it to the Desktop**. It puts `afkami xpedite farm.rdp` on your Desktop:

- **1920x1080**, whatever your own screen is: every picture xpedite looks for was measured at
  that size.
- **Scaled into any window size**, and the session doesn't resize when you resize the window.
- Connects to `127.0.0.2`, this PC itself. Windows refuses Remote Desktop to `127.0.0.1`, but any
  other `127.x` address reaches the same PC.

The same button turns on **keep drawing when minimized** for your account. Without it, a
minimized Remote Desktop window stops drawing the session and the farm goes blind.

## Step 6: connect, and set up the farm account (first time only)

1. Press **Connect now**, or double-click the file. Sign in with the farm account's password and
   tick **Remember me**.
2. The first sign-in takes a minute while Windows sets the account up.
3. In there, install **Roblox** (roblox.com) and sign in with the farm's Roblox account.
4. Open **xpedite** from its folder (step 1), then **Setup**: it sets the game's settings and
   reads the team in this account's Roblox.
5. **Setup > Farm in a second session** inside the session shows this session's own checks.
   Press **Make the desktop shortcut**: it puts *afkami xpedite* on this account's desktop, which
   starts the farm.

## Step 7: every day

1. Connect (the file on your Desktop).
2. Double-click **afkami xpedite** in there. The farm starts.
3. **Minimize** the Remote Desktop window. **Don't close it**: closing disconnects the session,
   and a disconnected session has no screen, so the farm stops seeing the game.

While it's minimized, your mouse and keyboard don't reach it. Use the PC normally.

- **To look in:** restore the window and watch, but don't move the mouse over it: over Remote
  Desktop that moves the farm's pointer too. The Discord bot (`/status`, `/screenshot`) shows
  you without touching it.
- **To stop:** F8 inside the session, or the Discord bot.
- **Sleep and restarts end it.** Set Windows not to sleep while plugged in (Settings > System >
  Power). A restart, Windows Update's included, closes both sessions: connect again afterwards.

**What xpedite does differently in a session**, by itself: it captures the game in a way that
works there; it doesn't pause on "touches" (Remote Desktop makes every click look like a person's,
and your own input can't reach a minimized session anyway); and it turns the camera with the
arrow keys, because mouse-drag turns arrive garbled over Remote Desktop.

---

## Troubleshooting

Open **Setup > Farm in a second session** first: the row that isn't ticked is usually the answer.

| What you see | Why | What to do |
|---|---|---|
| *Remote Desktop can't connect to the remote computer* | The wrapper isn't running, or Remote Desktop is off. | Check the **Wrapper** and **Remote Desktop** rows. Restart the PC; if it stays, reinstall the wrapper. |
| Connecting signs you out, or says *another user is signed in* | Two sessions at once aren't allowed: the wrapper isn't working on this Windows build. | RDPWrapKit: reinstall the newest release. Classic RDP Wrapper: see the next row. |
| Wrapper row: *doesn't know termsrv ...* (classic RDP Wrapper) | A Windows update moved past what its `rdpwrap.ini` lists. | Download the whole newest `rdpwrap.ini` (the community keeps one at `github.com/sebaxakerhtc/rdpwrap.ini`), replace the old file entirely, restart the PC. Or switch to RDPWrapKit. |
| *Your credentials did not work* | Wrong name or password. | Use the account's name as Windows shows it, for example `.\farm`. It must have a password. |
| *The connection was denied because the user account is not authorized for remote login* | A standard account outside *Remote Desktop Users*. | Step 4 (Apply) adds it. |
| Roblox is slow in the session, the CPU is busy | The session draws on the CPU. | Step 4, then sign the farm account out and connect again. |
| Pink, purple or green smears over the picture | Hardware H.264 encoding. | Step 4 turns it off; connect again. Still there: set `AVC444ModePreferred` to 0 in the same registry key (admin). |
| The farm sees a frozen or black picture while minimized | *Keep drawing when minimized* is off for your account. | Step 5 sets it. Connect again. |
| The game looks the wrong size, buttons aren't found | The session isn't 1920x1080. | Connect with the file from step 5, not another one. |
| Roblox: *Same account launched experience from different device* (Error 273) | Your own Roblox uses the same Roblox account as the farm. | xpedite stops the run rather than throw you out. Give the farm its own Roblox account. |
| Antivirus removed the wrapper | It flags these tools. | Restore and allow it if you trust it, or farm in your own account instead. |

---

## Undo it all

1. **Undo admin settings** in the window takes the two graphics settings back out.
2. Uninstall the wrapper: Settings > Apps > Installed apps > **RDPWrapKit** > Uninstall (classic
   RDP Wrapper: its `uninstall.bat` as administrator). Restart.
3. Delete the farm account: Settings > Accounts > Other users. Its files go with it, including
   its Roblox.
4. Delete `afkami xpedite farm.rdp` from your Desktop.

Remote Desktop stays on until the wrapper's uninstaller or you turn it off (Settings > System >
Remote Desktop, on Pro). *Keep drawing when minimized* changes nothing once you stop using Remote
Desktop.
