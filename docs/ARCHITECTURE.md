# Macro architecture

Design for the free all-in-one macro. Built on what was measured in
`docs/GAME.md` (screens, controls, camera, walking) and `docs/WIKI.md`
(modes and mechanics). Python + OpenCV + RapidOCR stays: the game's
animations are the bottleneck, and every hot path below fits in a few ms.

## The core idea: see → decide → act → verify

One loop, ~10–20 times a second while waiting, faster when it matters:

1. **Grab** a frame (wlr-screencopy, ~17 ms).
2. **Classify** where we are: a few small template matches in fixed regions
   (≤ 1 ms each). Only the states that make sense next are checked first; the
   full set only when lost.
3. **Read** the numbers the current step needs (wave, Yen, timer) from fixed
   regions.
4. The active **runner** decides one action.
5. **Act**, then **verify**: every action names what it expects to see next
   and a timeout ("click Start → expect Loading within 10 s"). A missed
   expectation goes to recovery, never to blind retry clicking.

Nothing is "click and hope". That's the main thing that makes it accurate.

## Layers

```
macro/
  io/       screen + pointer + keys (wl.py), Hyprland events, Sober process
  vision/   frame cache, template library, number reader, OCR, state classifier,
            map alignment (homography)
  control/  buttons, camera, walking, placing, unit panel / Unit Manager
  nav/      screen graph (lobby → menus → party → match → results), recovery
  match/    in-match controllers: Layout, AutoPlay, Hybrid + per-mode add-ons
  modes/    one runner per mode/event
  sched/    queue and timers ("farm X until Y, then Z", hourly rift, ...)
  stats/    SQLite run history, JSONL event log, failure snapshots
  supervisor.py  main loop, safety guard, watchdog
  cli.py         xm run / record / status / stop / calibrate
data/
  screens.yaml   every state: anchors (template + region), buttons, read-outs
  maps/<map>/    overhead reference image, alignment mask, layouts
  queue.yaml     what to farm
refs/            raw reference frames (refs/frames) and cut templates (refs/tpl)
```

### io — hands and eyes
- `Screen` (exists): grab, absolute pointer, **relative pointer and
  `turn()` (new)**, scroll, keys via wtype with hold time.
- **Hyprland event socket** (`.socket2.sock`) instead of polling `hyprctl`:
  we hear `workspace>>`/`activewindow>>` the moment it changes.
- Sober watcher: is the process alive, is the window fullscreen on 13.

### vision — knowing where we are
- **States are defined in data, not code**: each state in `screens.yaml` has
  1–3 anchors (a small template cut from a reference frame + the region to
  look in + a threshold), its buttons (template + fallback coordinate), and
  its read-outs (regions for wave, Yen, timer, stage name).
  Example anchors: the "Victory"/"Defeat" header, the health/wave pills,
  the "Progressive" banner of the Play menu, the stage-picker frame.
- Template matching in grayscale inside a small padded region is exact for
  this game (fixed resolution, pixel-stable UI) and costs well under 1 ms.
  No neural detector needed; it would be slower and less certain.
- **Numbers** (Yen, wave x/N, timers, enemies): fixed fonts in fixed spots, so
  a digit-glyph matcher reads them in ~1 ms. RapidOCR checks it when a value
  looks odd and reads anything free-form (stage names, popup text, "Rises in
  28:25"). RapidOCR only ever runs on small crops.
- **Unknown screen** → OCR the frame once and look for known words
  (Reconnect, Disconnected, Close, Claim, OK, Continue) to pick a recovery.
- **Map alignment**: for placing and walking, the live overhead view is
  matched to the map's stored overhead reference (ORB/AKAZE features on the
  ground, RANSAC homography, ~15 ms). Layout points are stored in reference
  pixels and mapped through it, so a camera that's a few pixels or degrees off
  still puts units on the right spot.

### control — doing things in the world
- **Buttons**: found by template near their expected spot, then clicked;
  the fixed coordinate is only a fallback. Survives small UI shifts.
- **Camera** (`camera.py`): `overhead()` = tilt down 3000 counts (clamps) +
  zoom fully out (clamps) + relative nudge to release the pointer lock, then
  verify by alignment. Yaw only when a map needs another angle: 0.157°/count,
  exact and reversible. All measured; see GAME.md.
- **Walking** (`move.py`): `walk(dx, dy)` in overhead-view pixels → W/A/S/D
  holds (~260 px/s, calibrated per map), then re-align and correct the small
  drift. Also `walk_to(landmark)` for lobby portals, rifts, gates, doors, and
  `dodge(region)` for mechanics like the Ancient One's eruption circles.
- **Placing** (`place.py`): slot key → move → click → verify (Yen dropped by
  about the cost, or slot count went up). On the red "cannot place" toast,
  try the next point of a small spiral around the target. Hands back a
  `PlacedUnit` (where, which slot).
- **Units**: upgrade / ability / priority / sell through the unit panel
  (click unit; T, R, X) or the Unit Manager list (F), whichever is surer.
  In-match selling is only used if a layout asks for it.

### nav — getting anywhere and back
- A **screen graph**: nodes are states, edges are actions with expected
  results (Lobby –Play→ PlayMenu –Story card→ StoryMaps –island→ ActPicker
  –Select Stage→ PartyRoom –Start→ Loading → Match → Results …). "Go to the
  Story picker for Crimson Shore Act 2 Hard" is a path search plus the
  map/act parameters.
- **Recovery ladder** when the state is unknown or an expectation fails:
  1. close a known popup (X templates, Close/OK/Claim by OCR);
  2. back out along the graph toward the lobby;
  3. in a match that's stuck (timer frozen) → exit to lobby;
  4. Roblox **disconnect** dialog → Reconnect;
  5. Sober gone or frozen for minutes → restart it (only if you allow it for
     unattended runs) and wait for the lobby;
  6. still lost → stop, save the last frames, tell you why.

### match — what happens inside a match
One controller per match, chosen per task:
- **LayoutController** (our own): canonical overhead camera, then a
  **layout** = ordered steps, each with conditions:
  `place <unit> at <point>` / `upgrade <unit> to <n>` / `ability <unit>` /
  `walk to <point>`, gated by `wave >= N`, `yen >= cost`, `time`. Upgrades can
  be left to the game's Auto-Upgrade or driven per unit.
- **AutoPlayController**: switch the game's Auto Play on, watch, step in only
  if it stalls. Cheap fallback for maps without a layout.
- **Hybrid**: our placements for the opening/key spots, Auto Play or Auto
  Upgrade for the rest.
- **Mode add-ons** run alongside: Soul Forge buying (Souls read-out, recipe
  buttons), Boss Rush gate choice, Rift gates, Ancient One dodging and
  "break the gaze", Expedition node/route choices, Tower floor rules.
- Every controller reports progress (wave, stocks, Yen, time) to the
  watchdog and the stats.

### modes — runners
Each runner = `enter()` (navigate + choose stage + start), `play()` (pick a
controller), `finish()` (read results, record stats, then Repeat / Next /
Lobby). Planned in this order, each tested with you:
Story (+ Infinite, Mastery) → Challenge (regular, daily, weekly) → Raid →
Demonic Rift (hourly) → Soul Furnace → Tower → Boss Rush → Ancient One →
Tournament / Global Tournament → Expedition (most decisions, last).

### sched — what to do when
- `queue.yaml`: tasks like
  `story: Crimson Shore Act 1-5 hard, next`,
  `farm: School Grounds Mastery until 10 clears today`,
  `challenge: regular every rotation`, `rift: hourly at :00, 2 clears`,
  `soul_furnace: until wave 50 quest x10`.
- Stop conditions: count, time, a quest done, a currency reached, a wave
  reached, a drop obtained (read from the results screen).
- **Timed tasks preempt farming between matches**, never mid-match (unless
  a task says so). Timers come from the game's own read-outs (challenge
  reset, "Rises in 28:25", rift window) with the clock as a fallback.

### stats — what happened
- SQLite `runs` (start, end, mode, map, act, difficulty, result, clear time,
  waves, stocks lost, Yen, kills, damage, rewards read off the results) and
  `events` (state changes, recoveries, errors).
- JSONL log you can tail. On any failure the last ~10 s of frames (kept in
  memory) are written to `logs/fail-<time>/` on disk, not /tmp.
- `xm status` / a small local page for totals per hour and per mode.

## Safety: stopping the instant you take the laptop back
- **Workspace guard**: from Hyprland's event socket. Workspace ≠ 13 or Sober
  not the active window → pause at once: release any held key/button, stop
  the loop. Every single input also checks the flag first.
- **Mouse takeover**: we know where we last put the pointer. If it's
  somewhere else (you moved the mouse), pause.
- **Kill hotkey**: a Hyprland bind (e.g. Super+Esc) that runs `xm stop`.
  Needs a line in your Lua config — your call.
- Resume only on `xm resume` (or optionally when 13 comes back).
- Spending guard: the action layer refuses any button that isn't on an
  allow-list per state; Summon, Store, Robux prompts, shops, gem/gold
  spends (portal augments, banners) are not on any list. A Roblox purchase
  prompt detected on screen → close it and stop.

## The app window (user's requirement, 9 Nov 2026)
The macro is one good-looking **PyQt** window (user's choice): a 16:9 frame in the middle
showing the game, and a column each side with all the options, logs and everything
else. The user said "or another more optimal window relation", so the proportions are
open. Results are screenshotted and sent by webhook, to check on a run from far away.

**This decides the game's size, so settle it before more pictures are taken.**
Everything so far assumes the game fills a 1920x1080 screen, which leaves no room for
columns. Every reference picture, anchor, digit shape, button position and camera
number depends on that size.

Decided after testing (details in `docs/WINDOWS.md`):
- **A fixed game size of 1440x810** on every machine, because Roblox won't go below 797 px
  tall. That also solves the open "other screen sizes" problem for screens big enough:
  everyone gets identical pictures whatever their monitor, and rendering fewer pixels
  suits low-end PCs and low RAM. On a 1920x1080 screen it leaves two 240 px columns, a
  40 px title strip and a 230 px strip for logs.
- **Roblox stays its own normal window, placed in the frame's hole** (a PyQt window with
  `setMask`, or panels around it). Moving and sizing a window is ordinary; reparenting
  it into ours is riskier and needless. The guard's "fullscreen" check becomes "in
  front, in the frame, at exactly this size".
- **All coordinates relative to the game frame,** so nothing assumes the screen's corner.
- PyQt6 and Qt stylesheets for the look. Keep it out of `macro/` below the app layer:
  the macro must still run without a window.

Tested: the game's UI is the same layout scaled down, text is readable, and the window
can lose its title bar. `tools/live_screens.py --capture` and `find_anchors.py` make
retaking everything mostly automatic if the size ever changes.

The macro uses the real mouse, because Roblox needs it. So clicking a column while
it's running pauses it, the same as any touch. The columns can be watched at any time;
changing options means pausing, and Resume hands the mouse back. Input that doesn't
take the mouse isn't an option to rely on: it hasn't been tested, and may not reach Roblox.

Webhooks: results come from frames the macro already has, so sending one is cheap. The
screenshot can be cropped to the game frame. Each user supplies their own URL.

## Setup: easy by default, fully customizable (user's requirement, 9 Nov 2026)
The macro must be both easy to start and completely customizable, and it must
not be tied to one team. The current six are only the first preset: in future
any team combination has to work.

- **Map adjustment, one universal position per map.** Each map has one set
  position. Before anything is placed, the macro walks the character there and
  sets the camera, so every run on that map starts from the same view. The route
  and camera are the map's own data (`data/maps/<map>/`), and a user can adjust
  them.
- **A reference picture of that position.** Taken from the set position, it is
  what the user works on: every unit placement, and the macro's other per-map
  settings, is adjusted against that picture. Points are stored in the picture's
  pixels and mapped through the map alignment above.
- **Easy usage:** pick a map and a preset, press start. Nothing needs editing.
- **Custom usage:** everything a preset sets is editable, including positions,
  placement order, upgrade targets, wave and Yen conditions, targeting, ability
  use, and the map position itself. Nothing in this list may be hard-coded.
- **Presets for what needs careful thought,** such as abilities and passives:
  how a unit's ability is timed, or how a team's passives are set up, lives in
  named, shareable presets rather than in code. Layouts say *which slot goes
  where*; unit and team presets say *how that unit should be played*. Swapping a
  unit means changing data only.

- **Always the lowest graphics.** Roblox's graphics level at its lowest plus the
  game's Low Detail Mode and effects off, for three reasons: low-end PCs can run
  it, it uses less RAM, and the screen looks as alike as possible for everyone,
  so reference pictures and map alignment carry between machines. All reference
  pictures must be captured at these settings. The macro checks them at startup
  and tells the user (or sets them through the normal in-game menus). No Fast
  Flags or client tweaks: only the settings a player has. Resolution is a separate
  problem: everything here assumes 1920x1080, so other screens need a decision.

Still to design when this is built: the editor itself (a local page showing the
picture is the likely shape), and a look at how other macros present this.
Read their public pages only: don't download or run them.

## Recording layouts
`xm record <map>` in Sandbox (free Yen, waves off): the macro sets the
overhead camera and saves the reference image; you place units by hand; it
sees each new placement (Yen drop + slot count) and stores the cursor
position (`hyprctl cursorpos`, no input-device access) with the slot and
wave. You can also give positions by clicking on the saved overhead picture.
Layouts are plain YAML you can edit.

## Why this is the fast and accurate option
- Exact template matching on a fixed 1920×1080 UI: sub-millisecond, no false
  guesses, and easy to extend (cut a new crop from a reference frame).
- Clamped camera inputs (tilt, zoom) and a lossless yaw make the view
  repeatable; feature alignment absorbs what's left.
- Verify-after-every-action turns a miss into a quick, logged recovery instead
  of a run of wrong clicks.
- Data-driven screens and layouts: a game update usually means re-cutting a
  template or a coordinate, not new code.
- Everything heavy (OCR, alignment) runs only when needed; the loop idles at a
  few percent CPU.
