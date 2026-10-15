import type { Metadata } from "next";
import { ResetPassword } from "../../components/password-reset";
export const metadata: Metadata = {
  referrer: "no-referrer",
  robots: { index: false, follow: false },
};
export default function Page() {
  return <ResetPassword />;
}
