import type { Metadata } from "next";
import { Poppins } from "next/font/google";
import "./globals.css";
import { AppShell } from "@/components/layout/AppShell";
import { ActingAdminProvider } from "@/lib/ActingAdminContext";
import { THEME_INIT_SCRIPT, ThemeProvider } from "@/lib/ThemeContext";

// next/font self-hosts the font files at build time (no runtime request to
// Google Fonts, no layout shift while it loads) and exposes them as a CSS
// variable, referenced from --font-sans in globals.css.
const poppins = Poppins({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-poppins",
  display: "swap",
});

export const metadata: Metadata = {
  title: "IT Helpdesk Admin",
  description: "IT Administrator Dashboard",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={poppins.variable}>
      <head>
        {/* Runs before React hydrates, so the correct theme is on <html>
            before the first paint -- without this there'd be a flash of
            the light theme every time a dark-mode user loads the page. */}
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
      </head>
      <body>
        <ThemeProvider>
          <ActingAdminProvider>
            <AppShell>{children}</AppShell>
          </ActingAdminProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
