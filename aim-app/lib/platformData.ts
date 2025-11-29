import type {
  ExampleCard,
  FeaturePanel,
  FeatureSummary,
  HeroMetric,
  OverviewItem,
} from "./mockData";
import { exampleCards, featurePanels, featureSummary, heroMetrics, overviewItems } from "./mockData";

export type PlatformData = {
  heroMetrics: HeroMetric[];
  overviewItems: OverviewItem[];
  exampleCards: ExampleCard[];
  featureSummary: FeatureSummary[];
  featurePanels: FeaturePanel[];
};

const clone = <T>(items: T[]): T[] => structuredClone(items);

export async function getMockPlatformData(): Promise<PlatformData> {
  return {
    heroMetrics: clone(heroMetrics),
    overviewItems: clone(overviewItems),
    exampleCards: clone(exampleCards),
    featureSummary: clone(featureSummary),
    featurePanels: clone(featurePanels),
  };
}

export async function getPlatformData(): Promise<PlatformData> {
  const origin = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";
  const target = new URL("/api/data", origin);
  const res = await fetch(target);
  if (!res.ok) {
    throw new Error("Failed to load platform data");
  }
  return res.json();
}