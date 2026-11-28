import type { Metadata } from "next";
import { Archivo } from "next/font/google";
import "./globals.css";
import { AccountProvider } from "../components/account-provider";

// Exposed as a CSS variable only; the landing page opts in via `.landing`,
// so other routes keep their existing typography.
const archivo = Archivo({
  subsets: ["latin"],
  weight: ["400", "600", "800"],
  variable: "--font-archivo",
  display: "swap",
});

export const metadata: Metadata = {
  title: "rapo. — Less repetition. More connection.",
  description: "Fresh, fair teams for communities that collaborate.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={archivo.variable}>
      <body>
        <AccountProvider>{children}</AccountProvider>
      </body>
    </html>
  );
}
