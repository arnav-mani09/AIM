# Ready-made models for rebounds, assists, turnovers and more (survey, Nov 11, 2026)

Result: nothing pretrained works on AIM's film (one wide, panning high school camera). Every
basketball event model or dataset found is broadcast NBA/FIBA footage, labels pre-cut clips
instead of finding events in a full game, or has a non-commercial license.

## What we use instead
- Rules on our own tracks (ml/tools/possession.py): ball holder, then team possession, then
  rebounds, turnovers, steals and assists.
- Later, for short visual events (blocks, steals, shot release): fine-tune E2E-Spot
  (github.com/jhong93/spot, BSD-3, fine for a paid product) on events coaches confirm in the
  review screen. Plan on 200 to 500 examples per event.
- Possible detector classes to add: "player with ball" and "shot block" (idea from Roboflow's
  basketball model).
- Fouls: whistle sound (YAMNet or PANNs audio taggers, check that the class exists) plus play stopping.
- Play types (pick and roll, isolation): rules on court positions after court mapping. 2027.

## Licenses that rule things out for a paid product
- Non-commercial data: MultiSports, NSVA, SportsMOT, DeepSportradar (closest camera view, benchmark only).
- AGPL: OpenSportsLib and its VideoAnnotationTool (commercial license available from OpenSportsLab).
- GPL: T-DEED and the SoccerNet team spotting code (stronger than E2E-Spot, needs legal review).
- BARD's CC BY license covers its labels and code, not the NBA video.

## Worth watching
- BasketEvent (arXiv 2607.21267): 10 events tied to players, code "will be released".
- BasketballBench (arXiv 2608.23435): general vision-language models score only about 60 F1 on
  events even on clean NBA clips, so they're fine for a chatbot but not for box scores.
- SportsVisio (competitor) does this from one phone camera; their main errors are giving stats
  to the wrong player, which points at jersey numbers as the hard part.
