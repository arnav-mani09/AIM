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

// Read the data directly: fetching our own /api/data route over HTTP fails
// during `next build`, when no server is running yet.
export async function getPlatformData(): Promise<PlatformData> {
  return getMockPlatformData();
}