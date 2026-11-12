# Insights plan: advanced stats, player tendencies, scouting reports

Status: Nov 11, 2026. Code: `ml/tools/insights.py` (tests in `ml/tools/test_insights.py`).
Local only for now. It reads the files the pipeline already writes and needs no film and no GPU.
All example numbers in this doc are made up.

## What it does today

```
ml/.venv/bin/python ml/tools/insights.py game <game> [<game> ...] --hudl
ml/.venv/bin/python ml/tools/insights.py scout --team Opponent --games <game> [<game> ...]
```

- `game` writes `ml/data/insights/<game>.insights.json` (both teams, all players) and, with
  `--hudl`, prints our team totals next to the Hudl box score.
- `scout` sums one team over one or more games and writes a JSON for the site plus a short
  plain-language report (`.scout.json`, `.scout.txt`).

Design rule: count first, compute rates last. A game is a set of counts per team and per
jersey number. A season rollup adds the counts and recomputes the rates, so 2 of 2 in one game and
0 of 8 in the next is 20%, not the 50% average of 100% and 0%.

Every stat in the JSON has `value`, `source` (which pipeline files it comes from) and `trust`:

| trust | meaning | stats |
|---|---|---|
| solid | close to Hudl in both test games | FGA, FGM, FTA, FTM, FG%, FT rate |
| fair | needs the 2 vs 3 call or a jersey number; mostly right | points, 3PA/3PM, eFG%, TS%, 3PA rate, corner vs above-the-break 3s, all player stats |
| rough | needs the feet's distance inside the arc or possession tracking | rim / paint / midrange split, possessions, pace, points per possession, OREB%, DREB%, TO%, second chance, transition and points off turnovers, shot timing |

## What each stat needs

| stat | formula | inputs |
|---|---|---|
| eFG% | (FGM + 0.5 x 3PM) / FGA | split.json, threes.json |
| TS% | PTS / (2 x (FGA + 0.44 x FTA)) | split.json, threes.json |
| FT rate | FTA / FGA | split.json |
| 3PA rate | 3PA / FGA | threes.json |
| shot mix and points by zone | zone from the shooter's feet | threes.json (feet, rim box, margin past the arc, arc ellipse) |
| possessions | changes of the team with the ball on the possession timeline; also FGA - OREB + TO + 0.44 x FTA | possession.json, split.json |
| pace | possessions per team per 32 minutes | possession.json |
| points per possession (off / def) | PTS / own possessions, opponent PTS / opponent possessions | threes.json, possession.json |
| OREB% / DREB% | OREB / (OREB + opponent DREB) and the reverse | possession.json |
| TO% | TO / possessions | possession.json |
| shot timing | seconds from the start of the possession to the shot: early under 8 s, late over 20 s | possession.json timeline |
| second chance points | points in a possession after that team's offensive rebound | possession.json events |
| transition points | first-chance field goal points within 6 s of getting the ball | possession.json timeline |
| points off turnovers | points in a possession that started with the other team's turnover | possession.json events |
| player FGA/FGM/3PA/FTA/PTS, share of team shots, zones, timing | shots grouped by jersey number | player_stats.json (only confidence 0.5 and up), players.json for time seen |

Zones. three_point.py already measures how far past the painted arc the feet were (in rough
feet), so shot distance is 19 ft 9 in plus that margin. 3s split into corner and above the break
by the feet's angle around the arc's own ellipse (the arc as the camera sees it). Inside the arc
the side-to-side direction is not reliable from one camera without a court model, so 2s split by
distance only: rim (4.5 ft), paint (free throw line distance, so a short wing jumper counts as
paint) and midrange. The feet are read at the gather, a step or two before a layup, so the rim
count runs low and paint runs high. Rim plus paint together is the useful number.

Players. A shot goes to a number only when player_stats.py is at least 0.5 confident; the rest
are listed as "unknown player" so the share is honest. Under 8 field goal attempts a player is
marked small sample and the text report skips the zone line under 4.

## Example output (made-up numbers)

```
Scouting report: Opponent, 3 games

Team shooting over 3 games: 162 points, FG 61/150 (41%), 3PT 22/66, FT 18/27. Effective FG 48%, true shooting 50%.
44% of their shots are 3s. They get 0.18 free throw tries per field goal try.
Where they shoot from (share of shots, makes): above-the-break 3s 28% (12 of 42); in the paint 27% (24 of 40); corner 3s 16% (10 of 24); midrange 15% (8 of 23); at the rim 7% (5 of 11).
Rough, from possession tracking: about 58 possessions a game, 0.93 points per possession, turnovers on 19% of possessions, offensive rebound rate 27%.

Players (by jersey number, only where the number read was confident):
#23: 41 pts, takes 30% of the team's shots, FG 15 of 45, 3PT 9 of 27; mostly corner 3s (6 of 14), then above-the-break 3s (3 of 13).
#5: 22 pts, takes 14% of the team's shots, FG 10 of 21; most often in the paint (8 of 12), then midrange (2 of 7).
#12: 4 pts, takes 4% of the team's shots, FG 2 of 6. Small sample.
Unknown player (number not read confidently): 38 FGA, 6 FTA, 40 pts (25% of shots).
```

The JSON carries the same numbers with `source` and `trust` on every team stat, per-zone
attempts and makes per player, and the text itself under `text`.

## How it checks against Hudl (Nov 11, two test games)

- Shooting lines are within a few attempts: FGA off by 1 to 4 per team, points within 1 for
  Valley and within 8 for the opponent (the miss is mostly 2 vs 3 calls). eFG% and TS% land
  within 0.5 to 6 points.
- Rebounds and turnovers from possession.json are close in some team-games and far off in others
  (turnovers counted twice the real number in one game). That is why every possession stat is
  rough until possession.py's check improves.
- Rim plus paint points run under Hudl's paint points (Hudl counts generously and our feet are
  read before the last step).
- Opponent players: about 80 to 85% of the attempts we give a number land on a number Hudl
  credits with that many attempts. Valley's Hudl rows are mostly untagged, so they can't check
  Valley's numbers yet.
- Transition points are well under Hudl's: possession changes land when the other team first
  holds the ball, and a long outlet or a steal can start the clock late.

## Moving it into the site

1. Insights step after `make_events` in `worker/film_worker.py`: once the events JSON exists,
   run the same counting on the drafted events (plus possession events when they ship). Pure
   Python and fast, so it can run inside the same Modal call, no GPU.
2. Storage: a `game_insights` JSON column (or table keyed by game id) with the per-game counts,
   not the rates. Rates are computed on read, which makes season rollups a sum over rows. Recompute
   when the coach edits an event in the review screen, since a fixed 2 vs 3 or a fixed jersey
   number changes the counts.
3. Coach edits win. The insights step should read the reviewed events, not the raw draft, so
   a corrected shot moves the zone and player numbers too.
4. Pages: a Players page (Valley, season tendencies per number) and a Scouting page (pick an
   opponent, get the report built from every game against them). Show trust as a small label
   next to rough numbers rather than hiding them.
5. The coach chatbot can answer from the same JSON ("who shoots the most corner 3s?") with the
   trust level in the answer.

## What needs better tracking first

- Possession (turnovers, steals, assists, possession boundaries): everything rate-based leans on
  it. Turnovers are the weakest part today.
- Jersey numbers for Valley: too many Valley attempts end up as unknown player for a reliable
  Players page; a roster from the coach (numbers only) would let player_stats drop impossible
  numbers.
- Court position inside the arc: a real court model (homography from the painted lines) would
  make rim vs paint vs midrange and left vs right side trustworthy, and allow shot charts.
- Feet at the release, not the gather, for layups and drives.
- Free throws per player: free throw shooters are found by the nearest player to the ball, which
  is weaker than the gather rule used for field goals.
- Minutes: on-court time per number would allow per-minute rates and lineups; players.json only
  has "seen on film" seconds today, which is not playing time.
