import type { Metadata } from "next";
import "./styles.css";

export const metadata: Metadata = {
  title: "PICK — Buy better, regret less",
  description: "Independent purchase decisions, price protection, and rewards.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}

