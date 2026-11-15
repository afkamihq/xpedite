# Expedition mode (looked at live from 15 Nov 2026)

Everything here was seen in the game at graphics level 1, docked at 1440x810, from the `macro`
account. Coordinates are the framed game's pixels (`tools/poke.py`). Reference pictures:
`refs/frames_win/expedition/`. The wiki (read 15 Nov) has only Expeditions, Checkpoint_Nodes,
Encounter_Nodes, Defense_Nodes, Expedition_Coin and Expedition_Center; nothing on costs, payload
upgrades or difficulties. Prior art: the user's August macro in `research/old-macro/` (screen
part only; never its memory readers).

## Getting in

- Lobby **Play** (128, 512) -> Play menu card **Expedition** (830, 530), which says "Current Map
  East Town, Expedition Center Level 3, Total Progress 100%".
- **Expedition picker** ("Payload Defense"): maps on the left, School Grounds (147, 190), Flower
  Forest (147, 322), Rose Kingdom (147, 454), East Town (147, 586); **Difficulty** `-` (354, 518)
  / `+` (552, 518), 1 to 3 (skulls: 1 green, 2 red, 3 purple; `+` greys out at 3); the choice
  stays when the map changes. **Rewards** row (six items); **Customize Payload** (1310, 685);
  **Select Stage** (452, 771); **Enter Matchmaking** (734, 771); **Back** (147, 771).
- Picker rewards (the most a run can give?), per difficulty 1 / 2 / 3, the same on every map
  except the map's material:

  | item | D1 | D2 | D3 |
  |---|---|---|---|
  | Equipment Scrap | 13 | 16 | 19 |
  | Fuel Cell | 13 | 16 | 19 |
  | Equipment Lock | 3 | 4 | 5 |
  | Equipment Reroll | 3 | 4 | 5 |
  | Expedition Coin | 13 | 16 | 19 |
  | map material | 26 | 31 | 36 |

  Map material: School Grounds **Cursed Timber**, Flower Forest **Lush Dirt**, Rose Kingdom
  **Aqua Shard**, East Town **Mechanical Scrap**.
- A red triangle on a reward = **"Inventory Limit: you've reached the max inventory limit! You
  will not receive this reward, even if it drops!"** On 15 Nov that's Equipment Scrap (250 held).
  The reroll settings must let a capped item count as nothing.
- **Customize Payload** is only skins: Standard Payload (Rare, equipped) and Futuristic Payload
  (Legendary, "Not Owned"). Nothing to automate.
- **Select Stage** -> party room ("School Grounds - Expedition, Difficulty 1", the rewards, Private
  Party, Start (854, 563) / Change Map / Disband). **Start** -> loading (~12 s) -> the run.
- Nothing on the picker or the party room shows a price. Inventory before the first start
  (15 Nov, Items menu): Mechanical Scrap 131, Aqua Shard 54, Lush Dirt 22, Cursed Timber 23,
  Expedition Coin 228, Gold 3,358, Equipment Scrap 250, Equipment Lock 42, Equipment Reroll 120,
  Stat Lock 301, Stat Reroll 7. **Fuel Cells aren't an Items entry** (search "fuel" finds nothing).

## In the run

- Start: standing on the payload at the start node. HUD: enemies, time, units `0 / 10` at the top;
  a node bar under it (start, then one icon per node of the route); payload HP `1,000 / 1,000`
  and **Yen 3,500** above the hotbar; hotbar slots 1-6 = the team, **7-10 empty (hires)**;
  `Payload Lvl 1 (0/35 XP)` under it. Right side: Hireable Units, a quest line ("The Drink"),
  **Unit Manager** (F), **Stage Info** (C), **Expedition Map** (1352, 519). **Continue**
  (720, 613) goes on to the next node.
- Hotbar prices differ from the lobby (slot 2 ¥2,000 here, ¥1,600 in the lobby).
- **One placement per unit** (`0/1` on the card); a placed unit's card leaves the hotbar.

## What a run costs: nothing

Checked 15 Nov: the first run started with **0 Fuel Cells** and took nothing. After a Defeat the
inventory had gained exactly the run's rewards (Expedition Coin 228 -> 250 = +22, Fuel Cell 0 ->
11) and nothing else moved (Cursed Timber 23, Gold 3,358, gems 0). Restarts (below) are free too.
**A Defeat still pays what the run had earned** (Fuel Cell 11, Expedition Coin 22, Player EXP 80).

## Rerolling: three ways to a fresh map

- **Settings gear** (289, 42) -> **Restart Game** (777, 422) -> "Restart Confirmation" ->
  **Restart** (617, 443): a new run in ~3 s, same map and difficulty, new map of nodes, new hires.
- **Repeat Stage** on the results (400, 639): the same, from a finished run.
- The old August macro's loop: gear -> restart icon -> Restart -> Expedition Map -> read -> Back,
  ~5.5 s a roll (157 rolls on East Town D3 logged: Mechanical Scrap 6-41, median ~19).
- The camera survives a restart (an overhead view stays overhead).

## The payload and where units go (user, 15 Nov)

- Camera for placing: `maps.set_overhead_camera` (tilt down, zoom fully out), then **4 notches
  in** (`scroll -15` x4): the payload fills x ~590-830, y ~220-590 of the frame, and the camera
  follows it.
- **The payload drives DOWN the screen in that view. Its TAIL is the TOP end (wide, spiked), its
  HEAD the BOTTOM end (cyan crystal and light bars).** Most enemies come at the tail, only a few at
  the head (user, twice: "you're placing in head, not tail"). Damage dealers go on the tail;
  the farm can go on the head.
- Valid spots seen (frame pixels): tail (705, 320), (655, 345), (755, 345), (705, 375), (655, 392);
  middle (650, 420), (715, 470), (660, 475); head (705, 515), (650, 530). Refused ("You cannot place
  a unit there!"): the four corners (650/770, 300) and (650/765, 545), and spots too close to a
  unit already there. The ghost is blue/white (or **yellow during a node**) where it can go, red
  where it can't.
- **Units can be placed at any time**, in or between nodes, on a valid spot (every failure on 15 Nov
  was a bad spot). A node opens with "NOTICE! Enemies Incoming! You can rearrange your unit
  placements before the game starts."
- Select-then-click too fast misses: key, 0.3 s, hover, 0.4 s, click.
- **Unit Manager (F) lists units in placement order**, three to a row: upgrade buttons at
  x 1032 / 1189 / 1347, y 266 (row 1) and 545 (row 2). "Maxed" when done. Each card also has
  Priority, Auto Upgrade, a lock and "..." (move?). Header toggles: Auto Upgrading / Phantom Placing.
- Costs seen: Atom upgrades ¥2,850, 4,150, 4,950 (Voidstep Strike), 5,850, 6,600 ... (8 in all);
  Stone Alchemist ¥1,100, 4,500 (3 in all); Black Heart ¥3,600 first (7); Forbidden Teacher ¥1,200 (5);
  8th Sword and Wolf (Starrk) 10 each (~¥2,200-7,400).

## The Expedition Map

- Title "Expedition Map", "Select nodes to map out your expedition route! Challenge harder nodes
  for greater rewards!", **Map Progress 1 / 10**. Start (gold wheel) at (85, 497), the Boss
  (skull) at the right (1356, 350). **Ten columns** of nodes, x = 225, 366, 507, 649, 790, 932,
  1073, 1214 (then the boss), 1-3 nodes per column, lines between neighbouring columns.
- Each node: its icon, **reward badges above** (icon + count, ~6 px digits), **two modifier
  icons below** (on fight nodes). The selected route is drawn green.
- **Clicking a node re-routes through it**: the game fills in the rest of the route itself, and
  **Route Rewards** (bottom strip, ~11 px digits) shows the route's total. Hovering shows a
  tooltip; hovering doesn't change the route.
- Route Rewards on the first School Grounds D1 map, default route: Fuel Cell 10, Equipment Scrap
  8, Equipment Reroll 4, Equipment Lock 2, Yen 8,016, Expedition Coin 16, Player EXP 280, Tome 1,
  Payload EXP 600, Cursed Timber 8. After clicking the top node of column 1: Equipment Scrap 14,
  Fuel Cell 11, Reroll 4, Lock 2, Yen 14,192, Coin 15, Player EXP 280, Tome 1, Payload EXP 675,
  Cursed Timber 8.
- **Back** (126, 732) closes the map.

### Node types (tooltips)

| icon | node | tooltip | modifiers | rewards seen (D1) |
|---|---|---|---|---|
| shield | **Defense** | "Defend off enemies at a traditional lane!" | 2 (e.g. 0.82x, 0.83x) | Equipment Scrap 3, Player EXP 40, Payload EXP 75 |
| crossed swords | **Elite** | "Defend off stronger enemies at a traditional lane!" | 2 (Gale-looking 0.8x, Light-looking 0.88x) | Fuel Cell 11, Yen 6,176, Player EXP 40, Payload EXP 150 |
| one sword | **Assault** | "Enemies constantly spawn around!" | none shown | Expedition Coin 3, Player EXP 40, Payload EXP 75 |
| coin stack | **Checkpoint** | "Safe area to strategize your next move!" | - | - |
| ! | **Encounter** | "A mysterious figure appears, offering to Speak, Barter, or Engage!" | - | - |
| skull | **Boss** | "A dangerous area where a special boss appears!" | - | Equipment Scrap 8, Reroll 4, Lock 2, Yen 8,016, Player EXP 40, Tome 1, Payload EXP 150, Cursed Timber 8 |

**Unknown** ("?"): "You don't know what type of encounter you'll get..."

Modifiers look like element multipliers (the wiki: "units can develop resistance to 2 random
Elements"), shown red below 1x: likely the damage those elements' units do there.

## Checkpoints (the start is one too)

- Beside the payload: three or four **Hireable Unit** NPCs (random each run: Jester, Sand
  (Alligator), Hollow (Blaze), Dead Melody (Solo), Prodigy (Rage), Vegetable (Prince), Silver
  Falcon, Puppet (Telekinetic), Sovereign (Djinn), Sharkfang (Abyssal), Toy Maker, Alchemy
  Brothers ...) and **Ramen Guy, Checkpoint Shop**. Clicking them does nothing: walk the character
  up (W/A/S/D; it steps off the payload, the camera follows) until **"E Interact"** shows, then E.
- **Hire dialog**: the unit's card (e.g. Jester, Exclusive, Neutral, Physical, Lvl 50, 681 DMG,
  6.2 s SPA, 17.5 range), "I've been at this checkpoint for too long, what do you say?",
  **Hire ¥3.69k** (red when short) / **Leave** (864, 699). Hires fill hotbar slots 7-10.
- **Checkpoint Shop** (Back (126, 739)): three Tomes ¥5,000 each (seen: Investor Tome, Precision 1
  Tome x2: "Apply the X trait to any unit!"), **Repair Hammer** ¥10,000 ("Add +500 Health to your
  Payload!"), **Anvil** ¥5,000 ("Gain a random Stat Anvil!"); **Buy All**; **Refresh Shop (1 Left)**.
  User's rule: buy only **Unbound Tomes for normal units and Investor Tomes for farm units**.
- Later checkpoints show **Extract** (644, 611) and **Continue** (800, 611) under the payload.
  Continue (or the start's Continue (720, 613)) asks "Are you sure you would like to leave this
  node? You will immediately begin traveling to the next node!" -> **Continue** (616, 452) /
  Cancel (822, 452).
- Nodes can also drop items into the hotbar: a **Limit Breaker Tome** ("Apply the Limit Breaker
  trait to any unit!", Use Item) turned up by the second checkpoint.

## Payload level-ups

Each payload level stops play with "Level N Reward, Select an upgrade!, Auto-selecting in 25s":
three cards, each with a level x/2 or x/3 and a "Select Upgrade" button (middle one (720, 560)).
Cards seen: Iron Flesh (summon health +10%), Fortified Cargo (payload health +100 and +¥2,000 now),
Relentless Pursuit (follow-up attacks +10% damage), Amplifier (buffs from other units +5% damage),
Yen Hunger (base Yen +10%), EXP Collector (EXP orbs drag toward you faster), Infectious (DoT +20%
chance of another DoT), Feral Cruelty (summons +145% crit damage, +25% crit chance), Venomous Edge
(DoT damage +10%), Gale Mastery / Flame Mastery (that element +10% damage). Taken ones show on the
left of the HUD by family (Buff, Summon, Follow-Up, DoT). Payload XP: Lvl 1 0/35, Lvl 2 /99,
Lvl 3 /182, Lvl 4 /280, Lvl 5 /391, Lvl 7 /648, Lvl 8 /792.

## How the first runs went (School Grounds D1, 15 Nov)

1. Atom + Alchemist from the start, the others never placed: Defense and Elite won easily, the
   first **Assault** lost (4:05). 108 kills.
2. 8th Sword, Black Heart, Alchemist on the payload's middle/head: lost 49 s into an Assault
   opener (1 kill: nothing reached).
3. Atom, Black Heart, Alchemist mid/head: lost in the Assault after the first Defense (2:47).
4. Atom on the head: lost seconds into the first Assault (the tail took the hits).
5. **Atom, Black Heart and Teacher on the tail, Alchemist on the head**, 8th Sword and Starrk
   added on the tail during the first Defense, upgrades through the Unit Manager (Alchemist first,
   then Atom): the Assault held at 1,000/1,000, ¥77k by the second checkpoint (9:28), Atom and
   Alchemist maxed. The tail is what wins.
- The Defense node draws its enemy lane in red on the ground; the payload sits at its end.
- In Assaults the payload rolls and enemies come mostly from behind (top of the view).

## Encounters

- An Encounter node is a stop with only **Continue** under the payload and an NPC labelled
  "Encounter" nearby (seen: **The Hero**, up and right of the payload). Walk up, "E Interact", E.
- Dialog: the NPC's line ("A hero always has time to spare for a chat.") and **Discuss** (432, 699),
  **Barter** (624, 699), **Engage** (816, 699), **Leave** (1008, 699).
- The Hero, **Barter**: "Hand over 500 Yen, and The Hero will stand ready to fight at full
  strength." -> click the line (720, 645) -> "Do you accept?" -> **Yes** (575, 700) / No (863, 700)
  -> "So be it." -> click. ¥500 gone, **The Hero (Legendary, Physical, 5/5 upgrades, 601 DMG, 4.5 s,
  range 24) in the next free hotbar slot**, ¥800 to place. The game moved on to the next node by
  itself as the dialog closed.
- Wiki options for the others: String Demon, Elf Mage, Crow (Black Fire), 8th Sword, The Drink
  (docs/WIKI.md has them). Default for anything but The Hero: Leave.

## How the mode is built (macro/modes/expedition.py)

- **Queue:** `{mode: expedition, map: <one of the four>, difficulty: 1-3, times: N}` (Tasks window,
  mode Expedition). `QueueRunner._play_expedition`: Repeat Stage from the last run's results when
  it was the same stage, else lobby -> Play -> Expedition -> map -> difficulty (read, not assumed)
  -> Select Stage -> party room -> Start; waits for the start's Continue.
- **Settings:** `data/expedition.yaml` (Tasks window, Expedition card). Per `"<map>|<difficulty>"`:
  reroll on/off, `match` all/any, `minimums` {resource: {on, min}}, `max_rerolls`, `when_none`
  (best / current / skip / stop), `capped_counts_zero`, `avoid_assault_first`. For every run:
  `placement` (layout name), `upgrade_order` (roles), `levelup_priority`, `hire`, `shop`,
  `encounters` {NPC: discuss/barter/engage/leave}, `extract` (never / hp_below / after_nodes).
- **Reroll:** open the map; click each first-column node (the game routes the rest), read Route
  Rewards (badge row by OCR, 'b' read as 1; item names by their white label, learned once into
  `data/expedition/items/`; the red Inventory Limit triangle marks a capped item); keep the best
  route that meets the rule, else Restart Game. ~7 s a roll.
- **Placement:** `data/maps/expedition_payload/layouts/tail.yaml` (Main window, mode Expedition,
  map "Expedition payload"): slot -> spot in the placing view. The camera is set overhead, then
  zoomed in a notch at a time until the payload matches its picture's size (`find_payload`, a
  multi-scale template); spots shift with the payload's measured offset. `Placer` checks each
  placement by the Yen drop and nudges a refused spot.
- **During a run:** level-up cards by `levelup_priority` (titles read once the cards stop
  moving); the Unit Manager's upgrade buttons in the user's role order, reading "Upgrade x/y" to
  know when a unit is maxed; pending units go down as the Yen allows.
- **At a stop (start, checkpoint, encounter):** place, upgrade, then OCR the NPC labels: an
  Encounter is walked to and answered from the table (The Hero: Barter); hires (if on) and the
  shop (tomes by the user's rule: Unbound for units that aren't, Investor for farms that aren't;
  Repair Hammer under the HP setting); Extract by the rule; then Continue and confirm.

## Auto Vote Start (15 Nov 2026, afternoon)

- The macro wants the game's **Auto Vote Start off** (`macro/setup/game_settings.py`: it starts
  each match itself once its camera is set). On 15 Nov it was found **on**: every Expedition test
  that morning ran with it on, and the Soul Furnace farm then failed every run from 11:14 to
  13:41 ("the match never showed Start Game": the match started before the phantoms went down).
  Turned off again in the lobby Settings (777, 485). Whether a reroll click flipped it or it was
  changed elsewhere isn't known; the reroll now checks the Settings list shows "Restart Game" and
  that the "Restart Confirmation" is up before each click (`restart_run`).
- With it off, an Expedition opens under the usual **"Start Game? Requires 50% to start the
  game."** window (Start Game (720, 248)); the start's Continue only comes after it. The mode
  rerolls and places its opening units under that window (the clock waits), then presses Start.
- **Units placed under the "Start Game?" window are phantoms** (units count up, the Yen and the
  cards stay; the game builds them later), and the window covers the payload's top (the zoom check
  misreads). So the mode presses Start Game first; the start is a checkpoint and waits for
  Continue. Every later node waits under the same window: the mode presses it each time.
- Under that window the hotbar is the lobby's six slots: prices are read after Start (they came out
  two slots off when read before).
- **Before Start, the in-run Settings has no Restart Game**; Back To Lobby sits at (777, 422) where
  Restart Game will be. The reroll presses Start first (`ensure_started`).

## Hires, tomes and items (15 Nov 2026, afternoon)

- Labels come back from OCR without spaces ("HireableUnit"); matching ignores spaces.
- Prompts: **Ramen Guy says "E Speak", hires and encounters "E Interact"**. Ramen Guy stands
  among the hires, so the walk to him waits for "Speak" (a walk stopped at a hire's prompt and
  opened its dialog instead of the shop).
- Hiring works: walk up, E, read "Hire ¥3.62k", Hire. Hired: Atom (Totality) ¥3,620, Wild Card
  (Ace) ¥1,750 (prices vary: 1.75k-7.5k). **The hired card lands in the first free hotbar slot,
  often one an own unit has left** (slot 2 after 8th Sword went down): units are tracked by
  placement order (= Unit Manager order), not by slot, and any priced card in the hotbar is an
  unplaced unit (a placed unit's card leaves).
- **Applying a tome**: open the Unit Manager, press the tome's hotbar key (apply mode), click the
  unit's portrait (upgrade button - (35, 66)); done when the tome's card leaves the hotbar. Seen:
  a dropped **Bolt Tome** onto Black Heart.

## Economy: Auto Upgrade, farms, Anvils (user, 15 Nov 2026)

- "Why can't you just use autoupgrade. Also the anvil system and yen is very important. Focus on
  farms if possible as well as buying anvils" (user). So: after each placement every card's
  **Auto Upgrade** goes on through the Unit Manager (`furnace.set_auto_upgrades`), priorities
  Stone Alchemist 1, Atom 2, other damage dealers 3, supports 5 (the game's Strict Auto-Upgrade
  Priority upgrades 1 fully before 2). Setting `upgrades: manual` brings back the macro's own clicks.
- At a Checkpoint Shop **Anvils come first** (5,000 Yen, "Gain a random Stat Anvil"), then the
  rule's tomes, then a Repair Hammer; then Refresh Shop and once more. Every buy is checked by the
  Yen falling by its price. A hire whose card says Farm is always taken and goes on the head.
- Summons get Unit Manager cards too (Starrk's two "Soul Wolf", Locked, 0/0), so cards are found by
  name (`furnace.unit_cards`), never counted by place.
- Two runs before these changes ended at the Boss (Cursed Summoner, ~1.58M HP, walks onto the
  tail) with ~400k Yen unspent and only 6 of 10 units placed.

## The "Start Game?" window at later nodes

- With Auto Vote Start off every node waits under "Start Game?". At some nodes its button is a
  darker green (G ~131 against ~200+), which the shared colour check doesn't take: a run sat 16
  minutes until the server sent the game back to its join screen. The window is now known by its
  title (`data/expedition/start_title.png`), whatever the button's shade.
- Out of the run (lobby / loading / black) for a minute: `play()` gives the run up so the runner's
  recovery takes over.

## Network trouble (15 Nov 2026, 15:00-15:25)

Twice the teleport into an Expedition server hung on Roblox's join splash for minutes, and a cold
start took 92 s to open a window. Roblox's log had the pattern docs/WINDOWS.md describes:
`ws ... 10.110.101.222:5052 error: HttpError: Timedout`, 503s from Roblox hosts; Cloudflare WARP
was connected (warp-svc running, in both sessions). Not the macro's doing; the user's to change.

## Anvils are items with cards (user + seen, 15 Nov 2026)

- A bought **Anvil** goes to the hotbar, and anvils **stack in one slot** ("4x"). Its key opens
  **"Stat Anvil: Select a stat upgrade! Auto-selecting in 25s"** with three cards in the level-up
  cards' places (Select Upgrade at (347/720/1093, 557)); seen: Follow-Up Damage +2.6% (Epic),
  Element Damage +3.5%, Range +2.6%. The mode uses every anvil at the stop it's bought at, taking
  cards by `anvil_priority` (default Damage, Attack Speed, SPA, Cooldown, Yen, Range).
- **Shop prices climb with each purchase in a run**: Anvil 5,000 -> 10,000 -> 15,000 -> 20,000;
  an Unbound Tome was 30,000 and a Repair Hammer 30,000 late in a run. Each buy is checked by the
  shop's own Yen display (bottom right, (1265, 722, 1400, 760)): the HUD's Yen is hidden there.
- The Yen bank (Auto Upgrading paused under 10,000 after 2.5 min) left 14,618 / 37,999 / 89,529
  Yen at three checkpoints of one run: 3 Anvils, an Unbound Tome and a Repair Hammer bought.
- A Repair Hammer's key at full payload HP only selects it (nothing used): it's kept for when the
  payload is hurt (under 60%).

## The Boss: not beaten yet (15 Nov 2026)

- School Grounds difficulty 1's last node is **Cursed Summoner**. Its health was 1.58M in one run
  and ~9.7M in another (it seems to scale with the run); it walks onto the tail with summons and
  takes ~1,000 payload HP in 20-40 s. Every full run so far lost there, including one with 10 Stat
  Anvils, an Unbound Tome on Atom, other tomes, Auto Upgrade maxing everything and 4 hammers bought.
- A Defeat still pays what the run had earned (results "Gained Rewards"), so farming works; a
  Victory needs a better answer to this Boss (asked the user).
- **Repair Hammer use isn't known yet**: its key at full HP only selects it; mid-Boss, key + a
  click on the payload didn't heal (both hammers stayed). `use_hammer` now counts a hammer as used
  only when the payload's health rises, and gives up after two tries.

## Placement pictures for players

Main window -> mode Expedition -> map **Expedition payload**: the overhead picture of the payload in
the placing view, with each slot's spot marked (`data/maps/expedition_payload/layouts/tail.yaml`).
Drag a mark to move it, click to add, right-click to remove. The spots are in that picture's
pixels; in a run the macro finds the payload (`find_payload`) and shifts the spots by where it is.

## Tomes are permanent (15 Nov 2026)

- A tome used in an Expedition (bought at a Checkpoint Shop or dropped) changes the unit's trait
  **for good**, outside Expeditions too. The player's Atom (Totality) went Primordial -> Bolt (a
  dropped Bolt Tome, 15:38) -> Unbound (a bought Unbound Tome, 18:32): one placement in the Soul
  Furnace instead of three, and every Furnace run after lost at wave 9-11 until its plan changed.
- So `shop.tomes_on_own` (Tasks: "Tomes on my own units (for good)") is off by default: tomes,
  bought or dropped, only go on units hired in the run. The Unbound/Investor rule still decides
  which hired unit gets which tome.
