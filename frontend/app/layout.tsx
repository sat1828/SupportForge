import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { Providers } from "@/components/Providers";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = {
  title: "SupportForge — AI-Powered Customer Support",
  description:
    "Production-grade multi-agent AI system that resolves 70–80% of support tickets automatically using LangGraph, RAG, and real-time SSE streaming.",
  keywords: ["AI customer support", "LangGraph", "multi-agent", "RAG", "automation"],
  openGraph: {
    title: "SupportForge",
    description: "AI-Powered Customer Support Automation",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={inter.variable}>
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
      </head>
      <body className="antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
