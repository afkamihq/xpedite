# What the official wiki says (read 9 Nov 2026)

Source: wiki.animeexpeditions.com (MediaWiki; data lives in Lua modules
`Module:StageData/data`, `/modes`, `/raids`, `Module:UnitData/data`,
`Module:ModifierData/data`). The wiki lags the game: it has nothing on
Update 4.0/5.0 beyond event pages, and no Tower page. Treat this as a map to
check against the screen, not as truth.

## Match basics (every mode)

- Wave-based tower defense on a map. Enemies walk a path to your base, which
  has **stocks** (lives) and sometimes **shield stocks**. Lose all stocks = defeat.
- In-match money is **Yen**. Placing a unit costs its level-1 cost; each
  upgrade costs more (e.g. Stone Alchemist 550 / 1100 / 2200 / 4500).
  Every unit has a **placement limit** (usually 3–4) and a placement type
  (Ground, or Hill/Air for some).
- **Farm** is an element: farm units make Yen instead of (or as well as)
  attacking. Stone Alchemist is an Epic farm.
- Units have element (Neutral, Flame, Hydro, Terra, Gale, Storm, Light, Dark,
  Farm) and archetype (Physical, Magical, Psychic). Enemies can resist or be
  weak to elements (stage effects like "Dark (1.5x)").
- In-match systems that modifiers can switch off, so they exist somewhere:
  **Stat Anvils**, **Trait Tomes**, the **Repair Hammer**, the **Research
  Tree**, and **Blood Money / Bounty Hunter cards**. (Expeditions'
  checkpoint shop sells tomes, anvils and hammers.)
- Player count scaling: +50% enemy HP per extra player.
- Settings already on for us: Auto Vote Start, Auto Skip Waves, Auto
  Abilities, Auto-Upgrade Placed Units.

## Modes

### Story (Progressive) — up to 4 players
8 maps: School Grounds, Flower Forest, Rose Kingdom, Fairy King Forest,
King's Tomb, East Town, Crimson Shore, Flaming Monastery (the last has no
data on the wiki yet). Each map has:
- **Act 1–5**, each in **Normal** or **Hard**. Hard pays more.
  School Grounds rewards, for scale: Normal clear 75 gems / 75 gold / 500 unit
  EXP / 115 player EXP + 1 Cursed Boba; Hard 100 / 100 / 1000 / 145.
  First clears pay 300–400 gems.
- **Star Missions**: 3 per act per difficulty, one Trait Crystal each
  (e.g. "Win without losing any stocks", "Win with only 3 units placed",
  "Win with spending less than 100k yen", "Win with only 1 farm placed").
- **Act 5 Hard** drops a 5% equipment (Kunai, Katana, Magic Orb, Warrior's
  Axe, Magic Book, ...), pity 20.
- **Mastery** act: Hard, extra modifiers, 5% equipment drops (pity 20),
  5 Grey Sprites guaranteed, double trait crystals from stars.
- **Infinite**: endless, uncapped HP scaling. Rewards every 5 waves
  (50 gems, 50 gold, 200 unit EXP). Stars at waves 10/25/50. Infinite quests
  at waves 25/50/75 per map. Global Tournament ranks Infinite by wave.
- Each act has a fixed boss and stage effects, e.g. School Grounds:
  Sprinter + Tank (+ Summoner on Act 5). Flower Forest: Burrowing, Explosive
  (stuns units on death), Splitter. King's Tomb Mastery: Boss Waves.

### Raid (Progressive) — hard, 3 acts each, Hard only
- Spirit City (bosses Glam Reaper / Silver Serpent / Berserker; drops
  Reaper 5%, 8th Sword 1% pity 35) and Snowy Castle (drops Eclipse Hunter,
  Iron Wolf). Wiki mentions a third raid from 2.5 without data.
- Pays gems, Raid Tokens + map token (10/15/20 by act), gold, Bunny Candy.
- **Raid Totems** (bought in the raid shop with tokens) give +0.10x damage
  each in that raid, up to 10.

### Challenge — Story stages on Hard with extra stage effects
- **Regular**: 3 choices, one clear allowed every 30 min (global reset time).
  Rewards trait crystals / rerolls+locks / sprites.
- **Daily** (24 h) and **Weekly** (7 days): bigger rewards
  (weekly: 50 trait crystals, 5,000 gems, ...).
- Daily quest "Complete any regular Challenge 3 times"; weekly 10 times.

### Expeditions — unlocks at player level 20
- Payload escort with 1,000 HP across a path of **nodes**: Defense (5 waves,
  wave 5 = map's Act 5 boss), Checkpoint (hire units for Yen, shop with
  tomes / anvils / repair hammer, move units, or Extract), Assault (payload
  crawls, enemies front and back), Elite (5 boss waves; losing fails the whole
  run), Boss (Act 5 boss with new mechanics), Encounter (dialogue with a unit:
  Speak / Barter / Engage with dice rolls).
- Party leader picks the route on the **Expedition Map**.
- 1 placement per unit, 14 units max on the payload (10–13 hired cap).
- Payload levels up → choose an upgrade each level.
- Pays expedition materials (Cursed Timber, Lush Dirt, Aqua Shard,
  Mechanical Scrap), Expedition Coins, Fuel Cells, equipment scrap/rerolls.
- **Expedition Hub** buildings (Expedition Center, Research Lab, Armory,
  Gold Mine, Training Grounds, Resource Drill, Shop, Quest Board) are upgraded
  with those materials.
- This is the most decision-heavy mode; automate it last.

### Boss Rush (3.0) — District 7
- Final boss (Crimson Captain) protected by **gates**: portals to small
  stages. Enter a gate, survive the timer, clear the leftovers; each cleared
  gate gives a buff and weakens the boss. Clear 2 to be allowed to fight it.
- Reward tiers 1–6 (by how many gates?): Boss Rush Tokens 70, Infernal Dust
  210–700+, 2% Beacon Of Pride (pity 50).

### Trials
- **Unit Trials** (19, from the Quests menu → Unit tab): solo, **preset
  team**, one-time evolution material. **Quest Trials**: Prodigy's Trial,
  Perfection's Trial (own team). **Event Trials**: limited.
- Preset team means fixed units; a layout per trial is enough.

### Portals (2.0)
- Item that opens a scaling run; tiers, clearing one can drop a higher tier.
  Dropped by Infinite stages or bought in event shops. Can be augmented with
  Gold (extra modifiers) — that spends Gold, ask first.

### Tournament (Competitive, weekly)
- Rotating stage with heavy stage effects, scored by a condition (damage,
  kills). Brackets, Solo and Duo. Pays Crowns (Tournament Shop),
  unit Toy Maker, skins.

### Global Tournament (Competitive, per major update)
- Highest wave reached in a map's Infinite. Each map has its own board.

### Sandbox
- Testing playground: any map, set Yen, waves, game speed, spawn units and
  enemies. **Very useful for us**: record placement layouts and test the
  runner with unlimited Yen and no stakes.

### Tower
- In the Play menu, not on the wiki. Map it in game.

## Events running now (Hallows Eve 5.0, until Update 6)

- **Halloween Event → Soul Furnace**: endless waves, up to 4 players.
  Enemies drop **Souls**; spend them at the in-match **Soul Forge**
  (DMG/RNG/SPA +1% for 20, Random Unit 100, Pumpkin Armor 75, Unlock/Close
  Path 50, Final Boss 500 after 5 Heat Bars — ends the run with +20% Candy
  Corn + 100). **Heat Bars** fill with Souls: each raises enemy HP x1.12 and
  Candy Corn x1.16; breakthroughs every 2 bars up to 10 (minibosses, Forge
  tiers II/III, element then archetype resistances per path).
  Starts with 3 paths (3–6). Pays **Candy Corn** (Halloween Shop) and
  Halloween Battlepass EXP (25 levels, last = unit Atom).
  Quests: daily "finish 1 run" (+500 CC), waves 10/20/30/50 ×1/×5/×10.
  Forge also sells equipment (500–750 Souls) and mythic Trait Tomes in-match;
  those are in-match Souls, not real currency.
- **Demonic Rift** (hourly, permanent): opens in the lobby at the start of
  every hour, joinable for 15 min, 25 waves, up to 4 players, **two clears an
  hour**. Gates open extra paths. Pays Rift Coins + Demonic Rift Coins 45–75,
  100 gold, 100 gems, 4% unit Wolf, 10% Demonic Pistols.
- **The Ancient One** (world boss, until Update 6): no wiki page.
  Atom quest: kill it with Atom's nuke.
- **Creator Spotlight**: 60 hidden rubber ducks across Story/Raid/Boss
  Rush/Rift maps. Manual; skip.
- **Headliner Hunt**: obtain/evolve banner units. Not a play mode; skip.
- **Beginner's Path**: tutorial quest chain.
- Boost events at set times (Weekend Surge Fri–Sun, Banner Blitz, Forge
  Fever, Elemental Weather, Shiny Overflow). Weekend Surge is worth
  scheduling heavy farming into.
- Lobby "Trick or Treat" doors (Halloween): open one for a trick or treat.

## Idle and side systems

- **AFK Chamber**: auto-clears a beaten Story stage; reward every 175% of
  your fastest clear time. Starts after 20 min idle too. So a fast clear time
  directly raises AFK income — another reason to optimise Story clears.
- **Quests**: dailies (complete 10 stages, 3 regular challenges, defeat 20
  bosses, spend gold/gems, summon) and weeklies (50 stages, 10 challenges, 50
  bosses). We only chase the play ones; spending and summoning are off-limits.
- **Battlepass** (season + Halloween): claim free track rewards.
- **Codes**: redeemable text codes (level-gated). Safe to automate later.
- **Fishing**: lobby minigame, rods, ranks. Possible later.
- Spending systems we never touch: Summon, Store, Robux shop, trait/stat
  rerolls with gems, feeding, selling.
