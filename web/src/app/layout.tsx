import type { Metadata } from "next";
import { Outfit } from "next/font/google";
import "./globals.css";
import { TerminalProvider } from "../context/TerminalContext";

const outfit = Outfit({
  variable: "--font-sans",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "glyph | Evaluation-as-a-Service",
  description: "Developer-first LLM evaluation platform. Bring your code, we handle the execution and visualization.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${outfit.variable}`}>
      <body>
        <TerminalProvider>
          {children}
        </TerminalProvider>
      </body>
    </html>
  );
}
