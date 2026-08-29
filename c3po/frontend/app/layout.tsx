import type { Metadata, Viewport } from "next";
import "./globals.css";

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: "#181713"
};

export const metadata: Metadata = {
  title: "C3PO | Chief of Staff Intelligence",
  description: "Private executive and financial intelligence workspace",
  manifest: "/manifest.webmanifest",
  appleWebApp: {
    capable: true,
    title: "C3PO",
    statusBarStyle: "black-translucent"
  },
  icons: {
    icon: [
      { url: "/c3po-icon-192-v2.png", sizes: "192x192", type: "image/png" },
      { url: "/c3po-icon-512-v2.png", sizes: "512x512", type: "image/png" }
    ],
    apple: "/c3po-apple-touch-icon-v2.png"
  },
  robots: {
    index: false,
    follow: false,
    nocache: true,
    googleBot: {
      index: false,
      follow: false,
      noimageindex: true,
      "max-image-preview": "none",
      "max-snippet": -1,
      "max-video-preview": -1
    }
  }
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="pt-BR">
      <body>{children}</body>
    </html>
  );
}
