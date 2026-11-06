import type { Metadata } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans } from "next/font/google";
import { headers } from "next/headers";
import { Providers } from "@/components/Providers";
import { TopBar } from "@/components/TopBar";
import "./globals.css";

const sans = IBM_Plex_Sans({ subsets: ["latin"], weight: ["400", "500", "600"], variable: "--font-sans", display: "swap" });
const mono = IBM_Plex_Mono({ subsets: ["latin"], weight: ["400", "500", "600"], variable: "--font-mono", display: "swap" });

export const metadata: Metadata = {
  title: "Associator",
  description: "Ask everyone else's AI — short, human-approved, ranked.",
};

const themeScript = `try{document.documentElement.dataset.theme=localStorage.getItem("pp.theme")||"dark"}catch(e){document.documentElement.dataset.theme="dark"}`;

/** The page frame: theme, fonts and providers. */
export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const nonce = (await headers()).get("x-nonce") ?? undefined;
  return (
    <html lang="en" className={`${sans.variable} ${mono.variable}`} suppressHydrationWarning>
      <head>
        <script nonce={nonce} dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body>
        <Providers>
          <TopBar />
          {children}
        </Providers>
      </body>
    </html>
  );
}
