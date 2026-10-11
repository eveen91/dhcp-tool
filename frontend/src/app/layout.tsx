import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Generator DHCP | Gaia',
  description: 'Generator konfiguracji DHCP dla Check Point Gaia',
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="pl">
      <body>{children}</body>
    </html>
  );
}
