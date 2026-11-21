// Sample data for mock mode only. The live hunt replaces it.
import type { FormField, Program, Profile } from './types';

export const sites = [
  { id: 'community', name: 'Community foundations', icon: 'Users' },
  { id: 'employer', name: 'Employer and industry awards', icon: 'Briefcase' },
  { id: 'university', name: 'University awards and bursaries', icon: 'GraduationCap' },
  { id: 'directory', name: 'National scholarship directory', icon: 'Search' },
  { id: 'municipal', name: 'Municipal youth programs', icon: 'Landmark' },
  { id: 'provincial', name: 'Provincial student aid', icon: 'MapPin' },
  { id: 'tax', name: 'Tax credits and filing', icon: 'Receipt' },
  { id: 'savings', name: 'Education savings grants', icon: 'PiggyBank' },
] as const;
export const provinces = ['Alberta','British Columbia','Manitoba','New Brunswick','Newfoundland and Labrador','Northwest Territories','Nova Scotia','Nunavut','Ontario','Prince Edward Island','Quebec','Saskatchewan','Yukon'];
export const incomeRanges = ['Under $30k','$30k–$60k','$60k–$100k','Over $100k','Prefer not to say'];
const profile: Profile = { fullName: '', province: 'Ontario', school: '', field: '', year: '', incomeRange: '', status: '' };
function fields(id: string, template: 'A'|'B'|'C'): FormField[] {
  const base: FormField[] = [
    { id: `${id}-name`, label: 'Full legal name', type: 'text', required: true, prefillKey: 'fullName' },
    { id: `${id}-school`, label: 'Current school', type: 'text', required: true, prefillKey: 'school' },
    { id: `${id}-field`, label: 'Program of study', type: 'text', required: true, prefillKey: 'field' },
    { id: `${id}-year`, label: 'Year of study', type: 'select', required: true, prefillKey: 'year', options: ['1st','2nd','3rd','4th','5th+','Graduate'] },
  ];
  if (template === 'B') base.push({ id: `${id}-province`, label: 'Province', type: 'select', required: true, prefillKey: 'province', options: [...provinces] }, { id: `${id}-income`, label: 'Household income range', type: 'select', required: true, prefillKey: 'incomeRange', options: [...incomeRanges] });
  if (template === 'C') base.push({ id: `${id}-why`, label: 'Tell us why you should receive this award', type: 'textarea', required: true, prefillKey: null, maxChars: 1200 });
  return base;
}
const today = new Date();
const due = (days: number) => { const d = new Date(today); d.setDate(d.getDate() + days); return d.toISOString().slice(0,10); };
type Seed = [string,string,string,number|null,string,string|null,string|null,'grant'|'scholarship'|'bursary'|'tax_credit'|'other',number,string,string,string[],string[],string,string,'A'|'B'|'C'|null,boolean?];
const seed: Seed[] = [
 ['northfield-leadership','Northfield Foundation Leadership Award','community',1000,'$1,000',due(6),null,'scholarship',.96,'The Northfield Foundation recognizes students who have led a team, club, or community project on campus or in their hometown.','You are a full-time Ontario undergraduate, and leadership roles are common in your program.',['Undergraduate','Full-time enrollment'],['Leadership experience','Ontario resident','Canadian citizen or permanent resident','Minimum B average'],'Submit the online form with a 250-word leadership summary. Takes about 20 minutes.','', 'C'],
 ['maple-ridge-bursary','Maple Ridge Community Bursary','community',500,'$500',due(13),null,'bursary',.91,'Helps students in financial need cover books and living costs during the winter term.','Your household income range and Ontario residency fit the stated criteria.',['Undergraduate','Part-time or full-time'],['Demonstrated financial need','Ontario resident'],'Complete the short online form. Income is self-reported.','', 'B'],
 ['tech-pathways-grant','Technology Pathways Grant','employer',600,'$600',due(3),null,'grant',.90,'An industry-funded grant for students in technology and engineering programs.','Your program is engineering and your status is eligible.',['Undergraduate'],['Enrolled in computer science, engineering, or a related program','Canadian citizen or permanent resident'],'Apply with a short statement of interest. Takes about 15 minutes.','', 'C'],
 ['first-gen-fund','First-Generation Scholars Fund','university',750,'$750',due(27),null,'scholarship',.74,'Supports students whose parents did not attend a post-secondary institution.','You meet the enrollment criteria. Confirm that you are the first in your family at university.',['Undergraduate','Full-time enrollment'],['First in your family to attend university','Full-time enrollment','Minimum 70% average'],'Submit through your university awards portal after confirming your eligibility.','', 'A'],
 ['great-lakes-engineering','Great Lakes Engineering Excellence Award','university',800,'$800',due(20),null,'scholarship',.83,'Awarded by the engineering faculty to continuing students with strong academic results.','You are a second-year engineering student. Check that your average meets the 80% minimum.',['Undergraduate','Full-time enrollment'],['Enrolled in an engineering program','Second year or above','Minimum 80% average'],'Apply through the faculty awards form.','', 'A'],
 ['digital-futures','Digital Futures Scholarship','directory',300,'$300',due(41),null,'scholarship',.68,'A small national award for students who show curiosity about how technology shapes everyday life.','Open to students at any Canadian institution. Selection depends on your essay.',['Undergraduate','College or university'],['Canadian student','Short essay required'],'Write a 200-word response and submit online. Takes about 25 minutes.','', 'C'],
 ['volunteer-recognition','Community Volunteer Recognition Award','municipal',250,'$250',null,'Rolling','other',.62,'A municipal award recognizing students who volunteer with local organizations.','Eligibility depends on your volunteer history, which we could not confirm.',['Undergraduate','College or university'],['Volunteer hours in the last 12 months','Resident of the municipality'],'Submit a volunteer hours letter with the short form.','', 'A'],
 ['emergency-study-aid','Emergency Study Aid Grant','provincial',400,'$400',null,'Rolling','grant',.79,'One-time help for students facing an unexpected expense that puts their studies at risk.','You are an Ontario student at a recognized institution. Eligibility depends on your circumstances.',['Undergraduate','Graduate'],['Unexpected financial hardship','Enrolled in a recognized institution','Ontario resident'],'Apply through your school\'s financial aid office.','', 'B',true],
 ['need-and-merit-bursary','Financial Need and Merit Bursary','provincial',600,'$600',due(34),null,'bursary',.86,'Combines financial need and academic standing to help full-time students with tuition.','Your income range, residency, and enrollment match.',['Undergraduate','Full-time enrollment'],['Demonstrated financial need','Minimum B average','Ontario resident'],'Complete the online application. Income is self-reported.','', 'B',true],
 ['tuition-tax-credit','Federal tuition tax credit','tax',null,'Varies',null,'At tax filing','tax_credit',.97,'Eligible tuition fees reduce the tax you owe, and unused amounts can be carried forward.','You are enrolled and pay tuition, which is what this credit is based on.',['Undergraduate','Graduate','College or university'],['Paid tuition to an eligible institution','File a Canadian tax return'],'Claim it on your tax return using the T2202 slip from your school.','', null],
 ['resp-check','Education savings plan check','savings',null,'Varies',null,'Anytime','grant',.70,'If a family member opened an RESP for you, federal grants may have been added to it. Many students never check.','Many students have a plan opened for them without knowing.',['Undergraduate','Graduate','College or university'],['A registered education savings plan (RESP) in your name'],'Ask your family or the plan provider whether an RESP exists, then request a withdrawal statement.','', null],
];
export function createPrograms(now = new Date()): Program[] {
  return seed.map(([id,name,site,amount,amountLabel,deadline,deadlineLabel,category,confidence,about,whyQualify,educationLevel,requirements,nextStep,unused,template,cached]) => {
    const siteInfo = sites.find(s => s.id === site)!;
    const fromCache = Boolean(cached);
    const foundAt = now.toISOString();
    const checked = new Date(now);
    if (fromCache) checked.setDate(checked.getDate() - 2);
    return { id, name, sourceSiteId: site, sourceSite: siteInfo.name, url: `/source/${id}`, amountMax: amount, amountLabel, deadline, deadlineLabel, category, confidence, about, description: about.split('. ')[0] + '.', whyQualify, nextStep, educationLevel, requirements, formFields: template ? fields(id, template) : [], fromCache, checkedAt: fromCache ? checked.toISOString() : foundAt, foundAt };
  });
}
export const mockPrograms = createPrograms();
export const emptyProfile = profile;
