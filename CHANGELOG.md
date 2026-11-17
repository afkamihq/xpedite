# Changelog

## 1.1.2

- **Setup stopped at the game's Settings on some PCs** ("lobby -> game_settings failed 3 times"):
  the open Settings window wasn't recognised where the game spaces its small text differently, so
  the gear was clicked again and closed it. It's now recognised by the window's frame and close button.
- **Setup → Quick start: choose the amounts.** *At least* sets how much of the map's material and
  how many Fuel Cells a route must promise before the Expedition is played (it rerolls until one does).
  Expedition and difficulty share one row.

## 1.1.1

- **Party room not recognised on some PCs** ("Select Stage didn't reach the party room; on unknown",
  then Roblox restarting over and over): some screens draw the game's text a few percent larger.
  A screen that matches nothing is now checked again at slightly larger and smaller text.
- **Smaller download**: about 27 MB of unused files left out of xpedite.exe's folder.

## 1.1.0

- **xpedite.exe**: a Windows download that needs no Python, and **updates itself** from the GitHub
  releases (your settings, team and placements are kept).
- **Expeditions**: Stat Anvil cards picked by stat and rarity (Bonus Match, then Critical Chance,
  then the rest; editable in Tasks), every card seen is listed in `data/expedition/anvil_cards.yaml`.
  At each checkpoint the rest of the route is checked against your minimums (scaled to what's left):
  it carries on when it's good and extracts for a reroll when it isn't.
- **Expeditions: tomes stay off your own units** unless you turn on *Tomes on my own units* in Tasks.
  A tome used in an Expedition changes the unit's trait for good (outside Expeditions too).
- **Setup → Quick start**: your private server link, and an Expedition task in three picks.
- **Fix**: the Unit Manager's *Auto Upgrading* switch is turned back on at the start of every Soul
  Furnace and Expedition run. The game remembers it between matches, and an Expedition that ended
  while saving Yen for the shop left it paused, so Soul Furnace runs lost early with nothing upgraded.

## 1.0.0

- First public version: Soul Furnace, Story, Challenges, Trick or Treat, Sandbox and Expeditions
  (reroll to minimums, payload placement, Auto Upgrade with farms first, anvils, tomes, hires,
  extract and reroll), with a Discord bot and webhook reports.
