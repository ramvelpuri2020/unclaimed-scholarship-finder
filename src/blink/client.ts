import { createClient } from '@blinkdotnew/sdk'

export const blink = createClient({
  projectId: process.env.NEXT_PUBLIC_BLINK_PROJECT_ID || 'unclaimed-finder-510lmbmu',
  publishableKey: process.env.NEXT_PUBLIC_BLINK_PUBLISHABLE_KEY || 'blnk_pk_6HbaZwtUe1jkUSEw2FPudHd1qq5KiOGt',
  authRequired: false,
  auth: { mode: 'managed' },
})
