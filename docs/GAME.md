# Anime Expeditions — the game as the macro sees it

Mapped live on 9 Nov 2026 (UPD 5, Hallows Eve), on a level 110 account.
Coordinates are full-screen pixels at 1920×1080 with Sober fullscreen.
Reference frames are in `refs/frames/` (named below). The wiki side of things
(rewards, stage effects, mechanics) is in `docs/WIKI.md`.

## Where things are

### Lobby (`lobby.png`)
- Left column buttons: Store, Units (H), Items (J), Quests, Summon, Areas,
  **Play (171, 660)**, **Events (118, 752)**.
- Right column: Battlepass (season), Battlepass Halloween, Guild, Profile,
  Calendar. Top bar: Roblox menu, chat, Settings ≈ (230, 33).
- Above the hotbar: gems, gold, two event currencies. Hotbar = the 6 equipped
  units with their in-match costs. Level + XP bar under it.
- Lobby world: Trick-or-Treat doors, Summon/Showcase/Upgrades NPCs, the hourly
  Demonic Rift spawns here.

### Play menu (`play_menu_top.png`, `play_menu_bottom.png`)
Cards; scroll with the pointer at (1350, 700), 150 = most of a page.
| Card | Click | Notes |
|---|---|---|
| Story | (1100, 230) | shows current map + acts cleared |
| Raid | (1620, 230) | |
| Boss Rush | (1100, 470) | |
| Challenge | (1620, 470) | shows daily/weekly reset timers |
| Expedition | (1100, 700) | |
| Trials | (1620, 700) | opens Quests → Trial tab |
| Tournament | (1100, 200) after scroll | |
| Global Tournament | (1620, 200) after scroll | |
| Tower | (1100, 430) after scroll | |
| Sandbox | (1100, 790) after scroll | |
Back (150, 1014). Invite Players / Join Party bottom right.

### Story map select (`story_maps.png`, `story_maps_end.png`)
Horizontal row of islands, wheel scrolls it (150 ≈ 1000 px). Order:
School Grounds, Flower Forest, Rose Kingdom, Fairy King Forest, King's Tomb,
East Town (all 100%), Crimson Shore, Flaming Monastery, Hollow Desert (0%).
Scrolled fully left, School Grounds is at (340, 450); islands are ~590 px apart.
Each island shows completion % and its drops.

### Stage picker (Story / Raid / Soul Furnace share it) (`story_act_picker.png`)
- Header colour tells the kind: blue Story, green Infinite, purple Mastery,
  red Raid, purple-orange Halloween.
- Left tabs at x = 412: Act 1 y 296, 2 388, 3 480, 4 572, 5 664, ∞ 756,
  M 848 (Raid has 1–4). Locked tabs show a padlock; stars under each tab.
- Difficulty: Normal (520, 440), Hard (608, 440).
- Middle: stage effects icons, rewards. Right: star missions with ★ when done,
  star rewards, **Fastest Clear**, **Total Clears** (Infinite: Highest Wave).
- **Select Stage (642, 852)** = private party. **Enter Matchmaking
  (1010, 852)** = public. Close X (1538, 198).

### Party room (`party_room.png`)
Stage card, rewards, Private Party lock, 4 member slots.
**Start (1138, 752)**, Change Map (1396, 752), Disband (1652, 752),
Leave Party (1766, 1024).

### Loading (`roblox_teleport.png`, `game_loading.png`)
Start → Roblox teleport screen (blurred art + game icon), black frames, then
the game's loading screen reading "Teleporting… <Map> - <Act> / <Mode> /
<Difficulty>". About 15–20 s from Start to wave 1.

### In match (`match_hud.png`, `match_autoplaying.png`)
- Top centre pills: **health** (stocks) ≈ (690, 32), **wave x / N** ≈ (840, 32),
  **enemies** ≈ (1030, 32), **time** ≈ (1210, 32). A "Wave N" banner with a
  countdown appears between waves; "Wave N Started" toast.
- **Yen** above the hotbar ≈ (960, 886); "+¥N next wave" pill next to it;
  "+¥N" pops when farms pay.
- Hotbar slots at y ≈ 975, x ≈ 670, 780, 890, 1000, 1110, 1220 (keys 1–6).
  Price turns red when unaffordable; selected slot shows placed/limit (e.g. 2/3).
- Right side: stage name + mode, **Unit Manager (F) (1803, 552)**,
  **Stage Info (C) (1803, 612)**, **Auto Play (1803, 672)** with its gear
  (1724, 674). Left: Pinned Objectives.
- Camera: third person behind the avatar. WASD walks (works through wtype
  key holds). Right-drag turns, wheel zooms.

### Placing by hand
- Press the slot key (1–6): a ghost of the unit follows the cursor and a hint
  box shows **Click Place, R Rotate, Z Cancel, L-Shift Quick Place**.
- Click the ground to place; Yen drops by the cost.
- Hover a placed unit: tooltip with name, rarity, upgrade level (0/3),
  stats, trait, owner.
- Click a placed unit: **unit panel** on the left with stats and next-level
  stats, **Priority (R)**, **Sell (X)** with refund, **Upgrade (T)** with
  cost, close X (614, 344).

### Auto Play (built in) (`autoplay_settings.png`, `autoplay_slot_*.png`)
- Toggle (1803, 672): "Auto Play" ↔ "Auto Playing". It stays on between
  repeats.
- Settings (gear): Set Shared Area Position, Auto Play Enabled, Shared Unit
  Radius (5), Shared Farm Radius (85), six Slots each with a gear, Presets
  (Share Selected, Import Code, Preset 1, +).
- Slot settings, Placement tab: Slot Enabled, Targeting (First), Place From
  Wave, Place Through Wave, Placement Limit, **Placement Zones · Current Map**
  (Add Zone). Upgrades & Abilities tab: Auto Upgrade, Auto Abilities,
  Upgrade Priority, Maximum Upgrade, Abilities From Wave.
- With it on, School Grounds Act 1 cleared in 2m 27s (record was 2:45).
- Limits: it only places and upgrades. It can't walk, buy at the Soul Forge,
  pick Boss Rush gates, dodge Ancient One circles or make Expedition choices,
  and we can't count on it for every map/mode or for tight layouts.

### Results (`victory.png`)
"Game Won!" toast at the top, then a **Victory** window: stage, Game Stats
(Clear Time, Total Yen, Total Kills, Total Damage), Gained Rewards, unit EXP
column. Buttons: **Next Stage (472, 852)**, **Repeat Stage (722, 852)**,
View Party (974, 852), red exit to lobby (1150, 852), close X (1558, 198).
Repeat Stage restarts on the spot with no teleport (a few seconds).
**Defeat** (`defeat.png`): red "Defeat" header, same stats, no rewards,
buttons Repeat Stage (534, 852), View Party (912, 852), exit (1150, 852).
Exit asks **"Exit Confirmation — Return to Lobby (822, 592) / Cancel"**
(`exit_confirm.png`); the trip back takes ~8 s and can land in a different
lobby server and spawn spot.

### Unit Manager (F) (`unit_manager.png`)
Right-hand panel listing every placed unit: upgrade level (e.g. 3/3 Maxed),
Priority, sell button with refund, per-unit Auto Upgrade, lock. Top toggles
**Auto Upgrading** and **Phantom Placing** (both Active), a gear, and at the
bottom Close (1374, 1036), Unit Stats, Sell All. Good for upgrading and
checking units without clicking them in 3D.

### Sandbox controls (`sandbox_controls.png`)
Game tab: Yen (starts 1,000,000), Base Health, Base Shield, Player Count
Scaling, Wave, Skip Wave, **Waves Enabled** (off by default), Game Speed.
Other tabs: Units, Enemies, Modifiers, Maps. Close (1628, 200). Sandbox
Controls button replaces Stage Info at (1803, 674).

### Found on Windows (9 Nov)
- Graphics level: Esc → Settings (760, 132) → scroll 150 → Graphics Quality minus
  (882, 410), with Graphics Mode already Manual. It was at 10; now 1.
- Sandbox picker: School Grounds (570, 400), **Select Map (1134, 856)**. Its party
  room is shorter than the normal one: **Start (1138, 688)**.
- In a match, top bar: **Back to Lobby door (393, 42)** opens Exit Confirmation with
  **Return to Lobby (822, 602)**. That's lower than on the Results screen, whose
  version is at (822, 592).
- Esc menu keys: L is Leave and R is Respawn. Never send them while it's open.

## Movement and camera (measured 9 Nov in Sandbox, School Grounds)
These are the Linux numbers. Windows is in `docs/WINDOWS.md`, and yaw differs by
about half.

All measured with `tools/probe_camera.py`, `probe_cam2.py`, `probe_walk.py`
(ORB feature matching between frames; numbers in full-res pixels).

- **Spawn pose is fixed.** A solo Story match and a Sandbox on the same map
  start with the identical frame: avatar on the path, camera behind it.
- **Zoom** (wheel, 15 = one notch) is clamped both ways. From spawn about
  6 notches reach fully out, about 10 more reach fully in. Fully in is first
  person (Roblox then steers the camera with the mouse — avoid). Fully out at
  the default tilt can leave the camera inside scenery (School Grounds: in the
  bushes behind the avatar) — useless on its own.
- **Turning** needs the right button held plus **relative** mouse motion;
  absolute moves are ignored while it's held (that's why the old `drag()`
  never turned anything). `Screen.turn(dx, dy)` does it.
  - Yaw: **0.157° per count**, linear (100 → 15.2°, 200 → 30.9°, 400 →
    63.4°), no acceleration, fast or slow the same, and turning back returns
    to the exact same pixels. A full circle is ~2,300 counts.
  - Pitch: +dy tilts the camera down. It **clamps**: after +3000, another
    +500 changes nothing. So "tilt down 3000" is a repeatable pitch.
  - After a turn the game can keep the pointer locked: absolute moves don't
    reach it until one relative nudge. Always nudge, then check.
- **Overhead view** = tilt fully down + zoom fully out. Near top-down, the
  whole School Grounds lane in view (`overhead_view.png`); yaw then shows up
  as a plain image rotation. Every input to get there is clamped, so it's
  repeatable from any start. This is the view to place from.
- **Walking**: W/A/S/D move relative to the camera, through `wtype` key holds
  (hold timing is accurate to ~5 ms). In the overhead view the scene moves
  **~260 px per second held**, linear (4 × 0.25 s = 1 s). Walking back the
  same time returns within a few px; drift is ~2 px per key press and adds up,
  so long walks need correcting against the picture.
- **Placing from the overhead view** works anywhere valid on screen (tested
  ~420 px from the avatar). Rooftops etc. fail with a red toast **"You cannot
  place a unit there!"** at the top and placement mode ends. Success: Yen
  drops, slot shows n/limit. With Auto-Upgrade on and Yen to spare, every
  level is bought at once (Stone Alchemist: −¥8,350).
- Cursor and keys: placement hint box sits next to the cursor; hotbar keys
  1–6; Z cancels; R rotates the unit; L-Shift quick place.
- **Ctrl toggles a pointer lock** (found on Windows, 9 Nov). The pointer stays at
  screen centre (960, 540), every mouse move turns the camera, and clicks miss.
  A right click doesn't release it; tapping Ctrl again does. The sign is that
  the pointer isn't where it was sent, which `Platform.click` checks for.

## Modes found in game

| Mode | Where | State on this account |
|---|---|---|
| Story | Play → Story | 6/9 maps at 100%; Crimson Shore 0/5 next |
| Infinite | Story picker ∞ | School Grounds best wave 110 |
| Mastery | Story picker M | School Grounds 15 clears |
| Raid | Play → Raid | Spirit City 75% (acts 1–3, act 4 locked), Snowy Castle 0% |
| Boss Rush | Play → Boss Rush | District 7; reward tiers 1–6; Stage Buffs button |
| Challenge | Play → Challenge | Regular: 3 at a time, rotating ~30 min, each 10/10 daily limit; Daily: Flower Forest Act 1 Hard; Weekly: unavailable now |
| Expedition | Play → Expedition | "Payload Defense", maps School Grounds / Flower Forest / Rose Kingdom / East Town, difficulty −/+, Customize Payload |
| Trials | Play → Trials (= Quests → Trial) | ~20 unit/equipment trials, most done |
| Tournament | Play → Tournament | Solo: King's Tomb, Damage Dealt; Duo: Hollow Desert; weekly brackets; score 0 |
| Global Tournament | Play → Global | #1 Rose Kingdom … #4 Crimson Shore (+1), Waves Cleared, ends UPD 6 |
| Tower | Play → Tower | Floor 1 and Traitless Tower Floor 1; 225 gems + 225 gold a floor; Entry / Rewards / Leaderboard |
| Sandbox | Play → Sandbox | any map + act, free testing |
| Soul Furnace | Events → Halloween → Event Gamemode | Infinite, Hard; Select Stage / Matchmaking |
| Demonic Rift | Events / lobby portal, hourly | 25 waves, twice an hour, 15-min window |
| The Ancient One | Events → World Boss | one wave, 5 min, up to 4; start with ¥100k, farms off, +¥50k per 25% HP; dodge eruption circles, break gaze on marked units; rises on a timer (shown) |
| AFK Chamber | lobby | idle income from a cleared Story stage |

Quests (Daily tab) seen: Complete Mastery Stages 0/10, Complete Stages 5/10,
Complete Daily Quests 4/6, Infinite quests (e.g. Rose Kingdom wave 25).

## Still to capture
Disconnect / reconnect dialog, reward popups (level up, unit drop), unit
loadout (Units menu), lobby rift portal, Tower entry flow, Boss Rush gates in
a match, Soul Furnace forge UI, Ancient One fight, Expedition map. Each gets
captured when its mode is built.
