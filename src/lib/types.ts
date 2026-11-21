export type Profile = { fullName: string; province: string; school: string; field: string; year: string; incomeRange: string; status: string };
export type FormField = { id: string; label: string; type: 'text' | 'textarea' | 'select'; required: boolean; options?: string[]; prefillKey: keyof Profile | null; maxChars?: number };
export type Category = 'grant' | 'scholarship' | 'bursary' | 'tax_credit' | 'other';
export type Program = { id: string; name: string; sourceSiteId: string; sourceSite: string; url: string; amountMax: number | null; amountLabel: string; deadline: string | null; deadlineLabel: string | null; category: Category; confidence: number; description: string; about: string; educationLevel: string[]; requirements: string[]; whyQualify: string; nextStep: string; formFields: FormField[]; fromCache: boolean; checkedAt: string; foundAt: string };
export type HuntEvent =
 | { type: 'site_started'; siteId: string; siteName: string; streamingUrl?: string }
 | { type: 'site_progress'; siteId: string; message: string }
 | { type: 'program_found'; program: Program }
 | { type: 'site_done'; siteId: string; count: number }
 | { type: 'site_failed'; siteId: string; usedCache: boolean }
 | { type: 'hunt_complete'; totalAmount: number; programCount: number };
