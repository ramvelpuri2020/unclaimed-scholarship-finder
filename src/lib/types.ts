export type ResumeMeta = { name: string; size: number; dataUrl?: string };
export type Profile = { fullName: string; province: string; school: string; field: string; year: string; incomeRange: string; status: string; resume?: ResumeMeta | null };
export type Category =
  | 'scholarship'
  | 'bursary'
  | 'award'
  | 'fellowship'
  | 'research_award'
  | 'competition_prize';
export type Fit = 'strong' | 'good' | 'weak';
export type Verification = 'dated' | 'rolling' | 'cycle' | 'unconfirmed';
export type ResumePreview = {
  characters: number;
  strengths: string[];
  angles: string[];
  statedSchool: string | null;
  statedProgram: string | null;
  statedYear: string | null;
};
export type Program = {
  id: string;
  name: string;
  provider: string;
  sourceSiteId: string;
  sourceSite: string;
  url: string;
  applyUrl: string;
  applyUrlIsAggregator: boolean;
  amountMax: number | null;
  amountLabel: string;
  deadline: string | null;
  deadlineLabel: string | null;
  verification: Verification;
  tier: 'A' | 'B';
  fit: Fit;
  deadlineQuote: string | null;
  evidenceQuotes: string[];
  resumeEvidence: string[];
  category: Category;
  confidence: number;
  description: string;
  about: string;
  educationLevel: string[];
  requirements: string[];
  whyQualify: string;
  nextStep: string;
  matchedOn: string[];
  gaps: string[];
  weakReason?: string;
  modelId?: string;
  checkedAt: string;
  foundAt: string;
};
export type Timed = { t?: number };
export type HuntEvent = Timed &
  (
    | { type: 'site_started'; siteId: string; siteName: string; streamingUrl?: string }
    | { type: 'site_progress'; siteId: string; message: string; count?: number }
    | { type: 'program_found'; program: Program }
    | { type: 'site_done'; siteId: string; count: number }
    | { type: 'site_failed'; siteId: string; usedCache: boolean }
    | { type: 'hunt_error'; message: string }
    | {
        type: 'hunt_complete';
        totalAmount: number;
        programCount: number;
        verifiedCount: number;
        unconfirmedCount: number;
      }
  );
export type HuntMeta = {
  huntId: string;
  status: string;
  startedAt: string | null;
  elapsedSeconds: number | null;
};
