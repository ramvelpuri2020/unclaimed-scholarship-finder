import type { Metadata } from 'next';
import { Plus_Jakarta_Sans } from 'next/font/google';
import './globals.css';
import { Providers } from './providers';
const jakarta=Plus_Jakarta_Sans({subsets:['latin'],weight:['500','600','700','800'],variable:'--font-jakarta',display:'swap'});
export const metadata:Metadata={title:'Unclaimed — Find the funding that fits you',description:'Discover scholarships, grants, bursaries, and tax credits made for Canadian students.'};
export default function RootLayout({children}:{children:React.ReactNode}){return <html lang="en"><body className={`${jakarta.variable} antialiased`}><Providers>{children}</Providers></body></html>;}
