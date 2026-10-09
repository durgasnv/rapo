import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "rapo. — Less repetition. More connection.",
  description: "Fresh, fair teams for communities that collaborate.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
