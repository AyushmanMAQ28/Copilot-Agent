import type { SVGProps } from "react";
export function Icon({ children, ...props }: SVGProps<SVGSVGElement>) { return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden {...props}>{children}</svg>; }
export function DownloadIcon() { return <Icon><path d="M12 3v12m0 0 4-4m-4 4-4-4M4 21h16"/></Icon>; }
export function ExpandIcon() { return <Icon><path d="M15 3h6v6m0-6-7 7M9 21H3v-6m0 6 7-7"/></Icon>; }
export function SunIcon() { return <Icon><circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2m10-10h-2M4 12H2m17.1-7.1-1.4 1.4M6.3 17.7l-1.4 1.4m0-14.2 1.4 1.4m11.4 11.4 1.4 1.4"/></Icon>; }
