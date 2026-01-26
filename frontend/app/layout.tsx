import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Bangun - Build Smarter with AI-Powered Cost Estimates",
  description: "Know your construction costs before you build. AI-powered material pricing and contractor comparison for Indonesia.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased">
        {children}
      </body>
    </html>
  );
}
