import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = { title: "CSV Insights", description: "CSV analysis workspace" };
const themeScript = `try{const t=localStorage.getItem('theme')||'system';document.documentElement.dataset.theme=t==='system'?(matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light'):t}catch(e){}`;

export default function Layout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en" suppressHydrationWarning><head><script dangerouslySetInnerHTML={{ __html: themeScript }} /></head><body>{children}</body></html>;
}
