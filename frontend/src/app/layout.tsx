import type { Metadata } from "next";
import 'bootstrap/dist/css/bootstrap.min.css';

export async function generateMetadata(): Promise<Metadata> {
  return {
    title: 'Тестовое задание Fullstack',
    description: 'Тестовое задание Fullstack',
  };
}

export default async function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang='ru'>
      <head>
        <link rel="icon" href="/favicon.ico" sizes="any" />
      </head>
      <body>
        {children}
      </body>
    </html>
  );
}