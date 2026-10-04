import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "MedyLink · Your health, connected",
  description: "One health identity. Your health records, connected to your care.",
  robots: { index: false, follow: false },
};
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
