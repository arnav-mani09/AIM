export type HeroMetric = { title: string; copy: string };
export type OverviewItem = { title: string; value: string; detail: string };
export type ExampleCard = { label: string; title: string; copy: string };
export type FeatureSummary = { title: string; copy: string };
export type FeaturePanel = {
  label: string;
  title: string;
  body: string;
  bullets: string[];
};

export const heroMetrics: HeroMetric[] = [
  { title: "12 hrs", copy: "Average turnaround for labeled film" },
  { title: "2.1 TB", copy: "Secure film archived this season" },
  { title: "47 clips", copy: "Shared per game to staff & athletes" },
];

export const overviewItems: OverviewItem[] = [
  {
    title: "Live possession split",
    value: "62% vs 38%",
    detail: "Tracker updates right after each trip down the floor.",
  },
  {
    title: "Shot profile",
    value: "1.32 PPP",
    detail: "Zone tags highlight catch vs off-dribble efficiency.",
  },
  {
    title: "Share center",
    value: "184 clips delivered",
    detail: "Push curated reels to coaches, players, and recruiters.",
  },
];

export const exampleCards: ExampleCard[] = [
  {
    label: "Possession split",
    title: "Valley 64%",
    copy: "Central 36% • 52-possession sample",
  },
  {
    label: "Shooter spotlight",
    title: "#24 Lane",
    copy: "64% eFG last five games, best left-slot shooter.",
  },
  {
    label: "Handle watch",
    title: "#12 Brooks",
    copy: "18% turnover rate vs press, needs extra reps.",
  },
  {
    label: "Clip callout",
    title: "ATO slip finish",
    copy: "Shared with varsity staff and athlete in 30s.",
  },
];

export const featureSummary: FeatureSummary[] = [
  { title: "Live possession", copy: "clocks tempo and momentum." },
  { title: "Auto player ID", copy: "keeps stats tied to each jersey." },
  { title: "Insights feed", copy: "flags shooters, handlers, and matchups." },
];

export const featurePanels: FeaturePanel[] = [
  {
    label: "Stats intelligence",
    title: "Possession & efficiency",
    body: "See offensive rating, pace, and live possession split without digging.",
    bullets: ["Auto-updated ORtg and tempo", "Player usage + shot quality snapshot", "One-tap exports"],
  },
  {
    label: "Clip locker",
    title: "Share and organize film",
    body: "Upload, tag, and deliver film to any unit with built-in view tracking.",
    bullets: ["Drag-and-drop uploads", "Assign clips to players or groups", "Instant share links"],
  },
  {
    label: "AI chat",
    title: "AIM assistant",
    body: "Ask for shooter rankings, lineup combos, or tendencies mid-game.",
    bullets: ["Uses live + historical stats", "Suggests matchups and actions", "Copies answers into notes"],
  },
  {
    label: "Team spaces",
    title: "Secure collaboration",
    body: "Invite-only workrooms keep coaches, players, and recruiters aligned.",
    bullets: ["Unique codes per team", "Role-based permissions", "Shared calendars and clip sets"],
  },
];
